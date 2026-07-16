"""ForecastingTribunal - wraps Prophet, XGBoost, and Ridge into one picklable
ensemble, blends their P10/P50/P90 ranges with campaign-type weights, and
scores how much the three models disagree.
"""
import numpy as np

from .prophet_model import ProphetModel
from .ridge_model import RidgeModel
from .xgb_model import FEATURE_COLUMNS, XGBModel

# Below this many daily rows, Prophet has too little signal to fit reliably
# and is dropped for that campaign - the other two models still cover it.
MIN_PROPHET_ROWS = 60

ENSEMBLE_WEIGHTS = {
    "shopping": {"prophet": 0.5, "xgb": 0.3, "ridge": 0.2},
    "brand": {"prophet": 0.5, "xgb": 0.3, "ridge": 0.2},
    "search": {"prophet": 0.2, "xgb": 0.6, "ridge": 0.2},
    "retargeting": {"prophet": 0.2, "xgb": 0.6, "ridge": 0.2},
    "display": {"prophet": 0.3, "xgb": 0.4, "ridge": 0.3},
    "other": {"prophet": 0.3, "xgb": 0.4, "ridge": 0.3},
}
DEFAULT_WEIGHTS = ENSEMBLE_WEIGHTS["other"]


def _weights_for(campaign_type):
    return ENSEMBLE_WEIGHTS.get(campaign_type, DEFAULT_WEIGHTS)


def _uncertainty_level(disagreement_pct):
    if disagreement_pct < 5:
        return "LOW"
    if disagreement_pct < 15:
        return "MODERATE"
    return "HIGH"


class ForecastingTribunal:
    def __init__(self):
        self.prophet_models = {}
        self.xgb_models = {}
        self.ridge_models = {}
        self.campaign_info = {}  # campaign_name -> {"channel", "campaign_type"}
        self.feature_columns = FEATURE_COLUMNS
        self.ensemble_weights = ENSEMBLE_WEIGHTS

    def fit(self, df):
        for campaign_name, group in df.groupby("campaign_name", sort=False):
            group = group.sort_values("date")
            self.campaign_info[campaign_name] = {
                "channel": group["channel"].iloc[0],
                "campaign_type": group["campaign_type"].iloc[0],
            }

            X = group[FEATURE_COLUMNS]
            y = group["revenue"]
            self.xgb_models[campaign_name] = XGBModel().fit(X, y)
            self.ridge_models[campaign_name] = RidgeModel().fit(X, y)

            if len(group) >= MIN_PROPHET_ROWS:
                series = group.rename(columns={"date": "ds", "revenue": "y"})[["ds", "y", "spend"]]
                self.prophet_models[campaign_name] = ProphetModel().fit(series)
        return self

    def predict(self, df, periods=(30, 60, 90), future_spend_overrides=None):
        """Returns {campaign_name: {period_days: {...predictions.csv row fields...}}}.

        future_spend_overrides: optional {campaign_name: daily_spend} to
        simulate a different future budget instead of the trailing 28-day
        average daily spend.
        """
        future_spend_overrides = future_spend_overrides or {}
        results = {}

        for campaign_name, info in self.campaign_info.items():
            group = df[df["campaign_name"] == campaign_name].sort_values("date")
            if group.empty:
                continue

            override = future_spend_overrides.get(campaign_name)
            daily_spend = override if override is not None else group["spend"].tail(28).mean()

            future_row = group[FEATURE_COLUMNS].tail(1).copy()
            future_row["spend"] = daily_spend

            model_predictions = {
                "xgb": self.xgb_models[campaign_name].predict(future_row, periods=periods),
                "ridge": self.ridge_models[campaign_name].predict(future_row, periods=periods),
            }
            if campaign_name in self.prophet_models:
                model_predictions["prophet"] = self.prophet_models[campaign_name].predict(
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
            results[campaign_name] = campaign_results

        return results

    @staticmethod
    def save(tribunal, path):
        import os
        import pickle

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(tribunal, f)

    @staticmethod
    def load(path):
        import pickle

        with open(path, "rb") as f:
            return pickle.load(f)
