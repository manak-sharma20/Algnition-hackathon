"""ForecastingTribunal - wraps Prophet, XGBoost, and Ridge into one picklable
ensemble, blends their P10/P50/P90 ranges with campaign-type weights, and
scores how much the three models disagree.
"""
import sys

import numpy as np

from .prophet_model import ProphetModel
from .ridge_model import RidgeModel
from .xgb_model import FEATURE_COLUMNS, XGBModel

# Below this many daily rows, Prophet has too little signal to fit reliably
# and is dropped for that campaign - the other two models still cover it.
MIN_PROPHET_ROWS = 60

# Below this many daily rows, even XGBoost/Ridge aren't fit at all - there
# isn't enough data to estimate three quantiles or a stable linear
# coefficient from (verified against the real dataset: 9 campaigns have
# under 10 rows, two of them exactly 1). These campaigns are skipped
# entirely in fit() and picked up by predict()'s naive-fallback path
# instead, the same path used for campaigns unseen at training time.
MIN_TRAINING_ROWS = 10

# Data-driven, not just domain intuition: a rolling-origin backtest across
# 4 cutoffs (src/backtest.py --cutoffs 4) measured each model's OWN
# out-of-sample MAE and found Prophet consistently ~1.85x worse than
# XGBoost/Ridge (which are themselves nearly tied) at every single cutoff -
# not noise, a uniform pattern. The original weights below (Prophet 0.5 for
# Shopping/Brand, the dataset's dominant campaign type) gave the most
# weight to the worst model. Weights here reflect that evidence: Prophet
# is kept in the blend (dropping it entirely was tested and measured
# WORSE median error - a weak-but-different model still reduces variance
# in a blend even when its solo accuracy is worse) but sharply reduced.
# Comparison, pooled across the same 4 cutoffs (163 campaign-forecasts):
#   original weights: MAE $3,993  median AE $1,109  coverage 68.7%
#   these weights:    MAE $3,693  median AE $998    coverage 74.8%
# See docs/TECHNICAL_DOC.md for the full experiment writeup.
ENSEMBLE_WEIGHTS = {
    "shopping": {"prophet": 0.1, "xgb": 0.45, "ridge": 0.45},
    "brand": {"prophet": 0.1, "xgb": 0.45, "ridge": 0.45},
    "search": {"prophet": 0.05, "xgb": 0.6, "ridge": 0.35},
    "retargeting": {"prophet": 0.05, "xgb": 0.6, "ridge": 0.35},
    "display": {"prophet": 0.1, "xgb": 0.45, "ridge": 0.45},
    "other": {"prophet": 0.1, "xgb": 0.45, "ridge": 0.45},
}
DEFAULT_WEIGHTS = ENSEMBLE_WEIGHTS["other"]

# Blending independent models' P10/P90 by weighted average understates
# combined uncertainty (each model's interval only captures its own
# uncertainty, not the risk the model class itself is wrong) - measured via
# the same backtest: raw blended intervals covered the actual outcome only
# 68.7-74.8% of the time against an 80% nominal target. Widening the
# blended interval around P50 by this factor (tuned on the same 4 cutoffs:
# 1.0->74.8%, 1.4->80.4%, 1.5->81.6%, 1.6->82.2%, 2.0->86.5%) closes most
# of that gap without excessively ballooning the range.
INTERVAL_WIDEN_FACTOR = 1.5


def _weights_for(campaign_type):
    return ENSEMBLE_WEIGHTS.get(campaign_type, DEFAULT_WEIGHTS)


def _uncertainty_level(disagreement_pct):
    if disagreement_pct < 5:
        return "LOW"
    if disagreement_pct < 15:
        return "MODERATE"
    return "HIGH"


# Placeholder disagreement_pct for fallback rows (see _naive_fallback below) -
# there's no model agreement to measure since no model was trained on this
# campaign, so this is a fixed "treat with caution" value, not a computed one.
FALLBACK_DISAGREEMENT_PCT = 25.0


def _naive_fallback(group, channel, campaign_name, campaign_type, periods, daily_spend):
    """Used for a (channel, campaign_name) with no fitted models to call:
    either it wasn't present in the training data at all (e.g. a new
    campaign launched after the pickle was trained - the tribunal never
    retrains at predict time, per the submission guide), or it was too
    sparse to fit meaningfully (under MIN_TRAINING_ROWS rows). Produces a
    same-shape output row instead of silently dropping the campaign from
    predictions.csv, or dressing up a fit on a handful of rows as a real
    model, using a simple trailing 28-day average daily revenue rate scaled
    by period length with a wide +/-30% band and HIGH uncertainty to flag
    it as not model-based.
    """
    daily_revenue = group["revenue"].tail(28).mean()

    campaign_results = {}
    for period_days in periods:
        base = daily_revenue * period_days
        revenue = {"p10": base * 0.7, "p50": base, "p90": base * 1.3}

        projected_spend = daily_spend * period_days
        roas = {
            level: (revenue[level] / projected_spend if projected_spend > 0 else 0.0)
            for level in ("p10", "p50", "p90")
        }

        campaign_results[period_days] = {
            "channel": channel,
            "campaign_type": campaign_type,
            "campaign_name": campaign_name,
            "period_days": period_days,
            "revenue_p10": revenue["p10"],
            "revenue_p50": revenue["p50"],
            "revenue_p90": revenue["p90"],
            "roas_p10": roas["p10"],
            "roas_p50": roas["p50"],
            "roas_p90": roas["p90"],
            "disagreement_pct": FALLBACK_DISAGREEMENT_PCT,
            "uncertainty_level": "HIGH",
            "prophet_p50": None,
            "xgb_p50": None,
            "ridge_p50": None,
        }
    return campaign_results


class ForecastingTribunal:
    def __init__(self):
        self.prophet_models = {}
        self.xgb_models = {}
        self.ridge_models = {}
        # Keyed by (channel, campaign_name), NOT campaign_name alone - the
        # same campaign name can legitimately exist in more than one channel
        # (verified against the real dataset: 27 names like
        # "Pmax_NTM_Campaign_01" collide between Google and Bing as
        # unrelated campaigns).
        self.campaign_info = {}  # (channel, campaign_name) -> {"channel", "campaign_type"}
        self.feature_columns = FEATURE_COLUMNS
        self.ensemble_weights = ENSEMBLE_WEIGHTS

    def fit(self, df):
        skipped = []
        for (channel, campaign_name), group in df.groupby(["channel", "campaign_name"], sort=False):
            group = group.sort_values("date")
            key = (channel, campaign_name)

            if len(group) < MIN_TRAINING_ROWS:
                # Not enough rows to fit a meaningful quantile regression or
                # linear model - leave it out of campaign_info entirely so
                # predict()'s naive-fallback path (below) picks it up.
                skipped.append(key)
                continue

            self.campaign_info[key] = {
                "channel": channel,
                "campaign_type": group["campaign_type"].iloc[0],
            }

            X = group[FEATURE_COLUMNS]
            y = group["revenue"]
            self.xgb_models[key] = XGBModel().fit(X, y)
            self.ridge_models[key] = RidgeModel().fit(X, y)

            if len(group) >= MIN_PROPHET_ROWS:
                series = group.rename(columns={"date": "ds", "revenue": "y"})[["ds", "y", "spend"]]
                self.prophet_models[key] = ProphetModel().fit(series)

        if skipped:
            print(
                f"Skipped {len(skipped)} campaign(s) with fewer than {MIN_TRAINING_ROWS} rows "
                f"(will use the naive fallback at predict time): {skipped}",
                file=sys.stderr,
            )
        return self

    def predict(self, df, periods=(30, 60, 90), future_spend_overrides=None):
        """Returns {(channel, campaign_name): {period_days: {...predictions.csv row fields...}}}.

        future_spend_overrides: optional {(channel, campaign_name): daily_spend}
        to simulate a different future budget instead of the trailing 28-day
        average daily spend.
        """
        future_spend_overrides = future_spend_overrides or {}
        results = {}

        for key, info in self.campaign_info.items():
            channel, campaign_name = key
            group = df[(df["channel"] == channel) & (df["campaign_name"] == campaign_name)].sort_values("date")
            if group.empty:
                continue

            override = future_spend_overrides.get(key)
            daily_spend = override if override is not None else group["spend"].tail(28).mean()

            future_row = group[FEATURE_COLUMNS].tail(1).copy()
            future_row["spend"] = daily_spend

            model_predictions = {
                "xgb": self.xgb_models[key].predict(future_row, periods=periods),
                "ridge": self.ridge_models[key].predict(future_row, periods=periods),
            }
            if key in self.prophet_models:
                model_predictions["prophet"] = self.prophet_models[key].predict(
                    periods=periods, future_spend=daily_spend
                )

            weights = _weights_for(info["campaign_type"])
            active_weights = {name: weights[name] for name in model_predictions}
            weight_total = sum(active_weights.values())
            active_weights = {name: w / weight_total for name, w in active_weights.items()}

            campaign_results = {}
            for period_days in periods:
                blended = {
                    level: sum(
                        active_weights[m] * model_predictions[m][period_days][level] for m in model_predictions
                    )
                    for level in ("p10", "p50", "p90")
                }

                # Widen the blended interval around P50 - see
                # INTERVAL_WIDEN_FACTOR's docstring for why and how this was
                # tuned. Clip P10 at 0 since revenue can't go negative.
                blended["p10"] = max(0.0, blended["p50"] - INTERVAL_WIDEN_FACTOR * (blended["p50"] - blended["p10"]))
                blended["p90"] = blended["p50"] + INTERVAL_WIDEN_FACTOR * (blended["p90"] - blended["p50"])

                p50_by_model = [model_predictions[m][period_days]["p50"] for m in model_predictions]
                mean_p50 = np.mean(p50_by_model)
                disagreement_pct = (np.std(p50_by_model) / mean_p50) * 100 if mean_p50 > 0 else 0.0

                projected_spend = daily_spend * period_days
                roas = {
                    level: (blended[level] / projected_spend if projected_spend > 0 else 0.0)
                    for level in ("p10", "p50", "p90")
                }

                campaign_results[period_days] = {
                    "channel": info["channel"],
                    "campaign_type": info["campaign_type"],
                    "campaign_name": campaign_name,
                    "period_days": period_days,
                    "revenue_p10": blended["p10"],
                    "revenue_p50": blended["p50"],
                    "revenue_p90": blended["p90"],
                    "roas_p10": roas["p10"],
                    "roas_p50": roas["p50"],
                    "roas_p90": roas["p90"],
                    "disagreement_pct": disagreement_pct,
                    "uncertainty_level": _uncertainty_level(disagreement_pct),
                    # Per-model P50s for the Tribunal Verdict Panel's agreement badges.
                    # Not part of the required predictions.csv columns - appended after them.
                    "prophet_p50": model_predictions["prophet"][period_days]["p50"] if "prophet" in model_predictions else None,
                    "xgb_p50": model_predictions["xgb"][period_days]["p50"],
                    "ridge_p50": model_predictions["ridge"][period_days]["p50"],
                }
            results[key] = campaign_results

        # Campaigns present in the predict-time data but never seen during
        # training (e.g. a new campaign in held-out test data) still get a
        # row - via the naive fallback above - instead of silently vanishing
        # from predictions.csv.
        seen_keys = set(zip(df["channel"], df["campaign_name"]))
        for key in seen_keys - set(self.campaign_info.keys()):
            channel, campaign_name = key
            group = df[(df["channel"] == channel) & (df["campaign_name"] == campaign_name)].sort_values("date")
            campaign_type = group["campaign_type"].iloc[0]
            override = future_spend_overrides.get(key)
            daily_spend = override if override is not None else group["spend"].tail(28).mean()

            print(
                f"WARNING: {key} was not in the trained model - using naive fallback prediction",
                file=sys.stderr,
            )
            results[key] = _naive_fallback(group, channel, campaign_name, campaign_type, periods, daily_spend)

        return results

    @staticmethod
    def save(tribunal, path):
        # gzip'd transparently - a full 136-campaign tribunal (200-tree
        # XGBoost quantile model per campaign) pickles to ~108MB raw, over
        # GitHub's 100MB file limit; gzip cuts that to ~22MB with zero
        # model-quality tradeoff (same n_estimators). Still just a normal
        # file at `path` (e.g. pickle/model.pkl) - gzip.open handles the
        # compression invisibly to callers.
        import gzip
        import os
        import pickle

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with gzip.open(path, "wb") as f:
            pickle.dump(tribunal, f)

    @staticmethod
    def load(path):
        import gzip
        import pickle

        with gzip.open(path, "rb") as f:
            return pickle.load(f)
