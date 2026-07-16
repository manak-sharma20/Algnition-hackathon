"""Prophet wrapper - the tribunal's seasonality expert.

Produces P10/P50/P90 revenue ranges for each requested aggregate period
(e.g. 30/60/90 days) by summing daily predictive samples across the period,
which correctly propagates Prophet's trend/seasonality uncertainty into the
aggregate rather than treating each day as independent.
"""
import numpy as np
import pandas as pd
from prophet import Prophet


class ProphetModel:
    def __init__(self):
        self.model = None
        self.default_future_spend = 0.0

    def fit(self, series):
        """series: DataFrame with columns ds, y, spend (daily granularity)."""
        history_days = (series["ds"].max() - series["ds"].min()).days

        # Fitting yearly Fourier terms on well under a year of history has no real
        # annual signal to anchor on and causes Prophet to extrapolate wildly past
        # the training window (verified: swings from +$4k/day to -$90k/day on a
        # 90-day sample series). Only trust yearly seasonality once there's at
        # least a couple of cycles of evidence for it.
        if history_days >= 730:
            yearly_seasonality = True
        elif history_days >= 365:
            yearly_seasonality = "auto"
        else:
            yearly_seasonality = False

        model = Prophet(
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10,
            uncertainty_samples=1000,
            yearly_seasonality=yearly_seasonality,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.8,
        )
        model.add_regressor("spend")
        model.fit(series[["ds", "y", "spend"]])

        self.model = model
        self.last_date = series["ds"].max()
        self.default_future_spend = series["spend"].tail(28).mean()
        return self

    def predict(self, periods=(30, 60, 90), future_spend=None):
        """Returns {period_days: {p10, p50, p90}} revenue totals for each period."""
        max_period = max(periods)
        spend_value = self.default_future_spend if future_spend is None else future_spend

        future = pd.DataFrame({
            "ds": pd.date_range(self.last_date + pd.Timedelta(days=1), periods=max_period, freq="D"),
        })
        future["spend"] = spend_value

        # predictive_samples() draws from numpy's global RNG with no seed
        # argument of its own - unseeded, it produces a different result on
        # every call even for the same fitted model (verified: two
        # back-to-back calls differed by ~$400 on a ~$138k P50). Seed it
        # explicitly so predict() is reproducible, per "random_state=42
        # everywhere."
        np.random.seed(42)
        samples = self.model.predictive_samples(future)["yhat"]  # shape (max_period, uncertainty_samples)
        samples = np.clip(samples, a_min=0, a_max=None)

        results = {}
        for period_days in periods:
            totals = samples[:period_days, :].sum(axis=0)
            p10, p50, p90 = np.percentile(totals, [10, 50, 90])
            results[period_days] = {"p10": float(p10), "p50": float(p50), "p90": float(p90)}
        return results
