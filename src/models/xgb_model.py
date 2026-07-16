"""XGBoost wrapper - the tribunal's feature learner.

Uses XGBoost's native multi-quantile objective (reg:quantileerror,
xgboost>=2.0) to predict P10/P50/P90 directly from a single model, rather
than bootstrapping 100 separate point-estimate models. A 100-model
per-campaign bootstrap was tried first and worked, but pickled to ~190MB
for just 7 campaigns (each bootstrap model duplicates 200 full trees) -
that doesn't scale to a real campaign catalog and blows past GitHub's
100MB file limit. The quantile objective gets the same P10/P50/P90 output
from one model per campaign at <1MB each.
"""
import numpy as np
import xgboost as xgb

FEATURE_COLUMNS = [
    "spend",
    "lag_revenue_7d",
    "lag_revenue_28d",
    "rolling_mean_revenue_7d",
    "rolling_mean_roas_7d",
    "spend_growth_rate",
    "month",
    "week_of_year",
    "is_q4",
    "is_weekend",
]

QUANTILE_ALPHAS = [0.1, 0.5, 0.9]


class XGBModel:
    def __init__(self):
        self.model = None

    def fit(self, X, y):
        model = xgb.XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=QUANTILE_ALPHAS,
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X[FEATURE_COLUMNS], np.asarray(y))
        self.model = model
        return self

    def predict(self, future_row, periods=(30, 60, 90)):
        """future_row: single-row DataFrame with FEATURE_COLUMNS."""
        daily_p10, daily_p50, daily_p90 = self.model.predict(future_row[FEATURE_COLUMNS])[0]
        # reg:quantileerror doesn't strictly guarantee non-crossing quantiles - sort as a safety net.
        daily_p10, daily_p50, daily_p90 = sorted(
            max(v, 0.0) for v in (daily_p10, daily_p50, daily_p90)
        )

        results = {}
        for period_days in periods:
            results[period_days] = {
                "p10": daily_p10 * period_days,
                "p50": daily_p50 * period_days,
                "p90": daily_p90 * period_days,
            }
        return results
