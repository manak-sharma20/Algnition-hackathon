"""Ridge regression wrapper - the tribunal's sanity anchor.

A simple, stable, interpretable linear baseline. Its job is not to be the
most accurate model - it's to catch cases where Prophet and XGBoost agree
with each other but are both wrong in the same way (e.g. an overfit
feature). Confidence intervals come from residual bootstrapping: sample
training residuals and add them to the point forecast.
"""
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .xgb_model import FEATURE_COLUMNS


class RidgeModel:
    def __init__(self, n_bootstrap=1000):
        self.pipeline = None
        self.residuals = None
        self.n_bootstrap = n_bootstrap

    def fit(self, X, y):
        X = X[FEATURE_COLUMNS]
        y = np.asarray(y)

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=1.0, random_state=42)),
        ])
        pipeline.fit(X, y)

        self.pipeline = pipeline
        self.residuals = y - pipeline.predict(X)
        return self

    def predict(self, future_row, periods=(30, 60, 90)):
        """future_row: single-row DataFrame with FEATURE_COLUMNS."""
        point = self.pipeline.predict(future_row[FEATURE_COLUMNS])[0]

        rng = np.random.RandomState(42)
        noise = rng.choice(self.residuals, size=self.n_bootstrap, replace=True)
        daily_samples = np.clip(point + noise, a_min=0, a_max=None)

        results = {}
        for period_days in periods:
            totals = daily_samples * period_days
            p10, p50, p90 = np.percentile(totals, [10, 50, 90])
            results[period_days] = {"p10": float(p10), "p50": float(p50), "p90": float(p90)}
        return results
