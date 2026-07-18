"""Tests for the three model wrappers: each must return P10<=P50<=P90 for
every requested period, since the tribunal's ensemble blend and roas
calculations both depend on that ordering holding.
"""
import numpy as np
import pandas as pd
import pytest

from models.prophet_model import ProphetModel
from models.ridge_model import RidgeModel
from models.xgb_model import FEATURE_COLUMNS, XGBModel


def _synthetic_series(n_days, seed=0, with_trend=True):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    spend = rng.uniform(80, 120, n_days)
    trend = np.linspace(0, 20, n_days) if with_trend else 0
    revenue = spend * 4 + trend + rng.normal(0, 10, n_days)
    revenue = np.clip(revenue, 0, None)
    return dates, spend, revenue


def _feature_frame(n_days, seed=0):
    """A minimal but complete FEATURE_COLUMNS frame + revenue target,
    shaped like what generate_features.py's add_derived() would produce.
    """
    dates, spend, revenue = _synthetic_series(n_days, seed)
    df = pd.DataFrame({"date": dates, "spend": spend, "revenue": revenue})
    df["lag_revenue_7d"] = df["revenue"].shift(7).fillna(0)
    df["lag_revenue_28d"] = df["revenue"].shift(28).fillna(0)
    df["rolling_mean_revenue_7d"] = df["revenue"].rolling(7, min_periods=1).mean()
    df["rolling_mean_roas_7d"] = (df["revenue"] / df["spend"]).rolling(7, min_periods=1).mean()
    df["spend_growth_rate"] = 0.0
    df["month"] = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_q4"] = df["month"].isin([10, 11, 12])
    df["is_weekend"] = df["date"].dt.dayofweek >= 5
    return df


def _assert_monotonic_periods(predictions, periods):
    for period_days in periods:
        row = predictions[period_days]
        assert row["p10"] <= row["p50"] <= row["p90"], f"period {period_days}: {row}"


# ---- XGBModel ------------------------------------------------------------

def test_xgb_model_predictions_are_monotonic_across_periods():
    df = _feature_frame(120, seed=1)
    model = XGBModel().fit(df[FEATURE_COLUMNS], df["revenue"])

    future_row = df[FEATURE_COLUMNS].tail(1)
    predictions = model.predict(future_row, periods=(30, 60, 90))

    _assert_monotonic_periods(predictions, (30, 60, 90))
    # aggregate-period scaling: 60d should be ~2x 30d (same daily rate assumption)
    assert predictions[60]["p50"] == pytest.approx(predictions[30]["p50"] * 2, rel=0.01)


def test_xgb_model_predictions_are_non_negative():
    df = _feature_frame(120, seed=2)
    model = XGBModel().fit(df[FEATURE_COLUMNS], df["revenue"])
    predictions = model.predict(df[FEATURE_COLUMNS].tail(1), periods=(30,))
    assert predictions[30]["p10"] >= 0


# ---- RidgeModel ------------------------------------------------------------

def test_ridge_model_predictions_are_monotonic_across_periods():
    df = _feature_frame(120, seed=3)
    model = RidgeModel().fit(df[FEATURE_COLUMNS], df["revenue"])

    future_row = df[FEATURE_COLUMNS].tail(1)
    predictions = model.predict(future_row, periods=(30, 60, 90))

    _assert_monotonic_periods(predictions, (30, 60, 90))


def test_ridge_model_is_deterministic():
    df = _feature_frame(120, seed=4)
    future_row = df[FEATURE_COLUMNS].tail(1)

    predictions_a = RidgeModel().fit(df[FEATURE_COLUMNS], df["revenue"]).predict(future_row, periods=(30,))
    predictions_b = RidgeModel().fit(df[FEATURE_COLUMNS], df["revenue"]).predict(future_row, periods=(30,))

    assert predictions_a[30] == predictions_b[30]


# ---- ProphetModel ----------------------------------------------------------
# Slower (real cmdstan fit) - kept to a small number of cases.

def test_prophet_model_predictions_are_monotonic_across_periods():
    dates, spend, revenue = _synthetic_series(120, seed=5)
    series = pd.DataFrame({"ds": dates, "y": revenue, "spend": spend})

    model = ProphetModel().fit(series)
    predictions = model.predict(periods=(30, 60, 90))

    _assert_monotonic_periods(predictions, (30, 60, 90))


def test_prophet_model_is_deterministic_across_repeated_predict_calls():
    # Regression test: predictive_samples() draws from numpy's global RNG
    # with no seed of its own - verified this produced different P10/P50/P90
    # on every call before ProphetModel.predict() started seeding explicitly.
    dates, spend, revenue = _synthetic_series(120, seed=6)
    series = pd.DataFrame({"ds": dates, "y": revenue, "spend": spend})
    model = ProphetModel().fit(series)

    first = model.predict(periods=(30,))
    second = model.predict(periods=(30,))

    assert first[30] == second[30]


def test_prophet_disables_yearly_seasonality_on_short_history():
    # Forcing yearly_seasonality on with well under a year of data was
    # verified to make Prophet extrapolate wildly past the training window.
    dates, spend, revenue = _synthetic_series(90, seed=7)
    series = pd.DataFrame({"ds": dates, "y": revenue, "spend": spend})

    model = ProphetModel().fit(series)

    assert model.model.yearly_seasonality is False
