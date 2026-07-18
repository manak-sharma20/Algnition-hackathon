"""Tests for ForecastingTribunal: composite (channel, campaign_name) keying
(the fix for real cross-channel name collisions), the naive-fallback path
for sparse/unseen campaigns, and ensemble weight renormalization when
Prophet is skipped.

Uses campaigns with under 60 rows almost everywhere to keep the suite fast
(Prophet is skipped below MIN_PROPHET_ROWS, so most of these never invoke
the slow cmdstan fit).
"""
import numpy as np
import pandas as pd
import pytest

from models.tribunal import MIN_PROPHET_ROWS, MIN_TRAINING_ROWS, ForecastingTribunal, _uncertainty_level
from models.xgb_model import FEATURE_COLUMNS


def _campaign_df(channel, campaign_name, campaign_type, n_days, seed, daily_revenue=100.0):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    spend = rng.uniform(20, 30, n_days)
    revenue = np.clip(daily_revenue + rng.normal(0, 5, n_days), 0, None)

    df = pd.DataFrame({
        "date": dates,
        "channel": channel,
        "campaign_name": campaign_name,
        "campaign_type": campaign_type,
        "spend": spend,
        "revenue": revenue,
    })
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


# ---- _uncertainty_level ----------------------------------------------------

@pytest.mark.parametrize(
    "pct,expected",
    [(0, "LOW"), (4.9, "LOW"), (5, "MODERATE"), (14.9, "MODERATE"), (15, "HIGH"), (50, "HIGH")],
)
def test_uncertainty_level_thresholds(pct, expected):
    assert _uncertainty_level(pct) == expected


# ---- composite (channel, campaign_name) keying ----------------------------

def test_same_campaign_name_across_channels_does_not_collide():
    # Real bug: "Search_TM_Campaign_02" exists in both Google and Bing as
    # unrelated campaigns with very different revenue levels. Keying by
    # campaign_name alone would let the second channel's fit overwrite the
    # first's model for the same name.
    google_df = _campaign_df("google", "Shared_Name", "brand", 40, seed=1, daily_revenue=500.0)
    ms_df = _campaign_df("ms", "Shared_Name", "brand", 40, seed=2, daily_revenue=50.0)
    df = pd.concat([google_df, ms_df], ignore_index=True)

    tribunal = ForecastingTribunal().fit(df)

    assert ("google", "Shared_Name") in tribunal.campaign_info
    assert ("ms", "Shared_Name") in tribunal.campaign_info
    assert tribunal.xgb_models[("google", "Shared_Name")] is not tribunal.xgb_models[("ms", "Shared_Name")]

    predictions = tribunal.predict(df, periods=(30,))
    google_revenue = predictions[("google", "Shared_Name")][30]["revenue_p50"]
    ms_revenue = predictions[("ms", "Shared_Name")][30]["revenue_p50"]

    # Google's campaign has ~10x the daily revenue - predictions must reflect
    # each channel's own data, not a blend or an overwrite.
    assert google_revenue > ms_revenue * 3


# ---- sparse-campaign fallback routing --------------------------------------

def test_campaign_below_min_training_rows_is_not_fitted():
    df = _campaign_df("google", "Tiny_Campaign", "search", MIN_TRAINING_ROWS - 1, seed=3)
    tribunal = ForecastingTribunal().fit(df)

    assert ("google", "Tiny_Campaign") not in tribunal.campaign_info
    assert ("google", "Tiny_Campaign") not in tribunal.xgb_models
    assert ("google", "Tiny_Campaign") not in tribunal.ridge_models


def test_campaign_below_min_training_rows_still_gets_a_fallback_prediction():
    df = _campaign_df("google", "Tiny_Campaign", "search", MIN_TRAINING_ROWS - 1, seed=4, daily_revenue=80.0)
    tribunal = ForecastingTribunal().fit(df)

    predictions = tribunal.predict(df, periods=(30,))

    assert ("google", "Tiny_Campaign") in predictions
    row = predictions[("google", "Tiny_Campaign")][30]
    assert row["uncertainty_level"] == "HIGH"
    assert row["prophet_p50"] is None
    assert row["xgb_p50"] is None
    assert row["ridge_p50"] is None
    assert row["revenue_p10"] <= row["revenue_p50"] <= row["revenue_p90"]
    # ~80/day * 30 days, +/-30% band
    assert row["revenue_p50"] == pytest.approx(80 * 30, rel=0.2)


def test_campaign_at_or_above_min_training_rows_is_fitted():
    df = _campaign_df("google", "Just_Enough", "search", MIN_TRAINING_ROWS, seed=5)
    tribunal = ForecastingTribunal().fit(df)
    assert ("google", "Just_Enough") in tribunal.campaign_info


# ---- unseen-at-predict-time fallback ---------------------------------------

def test_campaign_unseen_at_training_time_uses_fallback_at_predict_time():
    train_df = _campaign_df("google", "Known_Campaign", "search", 40, seed=6)
    tribunal = ForecastingTribunal().fit(train_df)

    new_campaign = _campaign_df("google", "Brand_New_Campaign", "search", 40, seed=7, daily_revenue=60.0)
    predict_df = pd.concat([train_df, new_campaign], ignore_index=True)

    predictions = tribunal.predict(predict_df, periods=(30,))

    assert ("google", "Brand_New_Campaign") in predictions
    row = predictions[("google", "Brand_New_Campaign")][30]
    assert row["uncertainty_level"] == "HIGH"
    assert row["xgb_p50"] is None


# ---- ensemble weight renormalization when Prophet is skipped --------------

def test_prophet_skipped_for_series_between_min_training_and_min_prophet_rows():
    n_days = MIN_PROPHET_ROWS - 10  # enough for XGB/Ridge, not for Prophet
    df = _campaign_df("google", "Medium_Campaign", "shopping", n_days, seed=8)
    tribunal = ForecastingTribunal().fit(df)

    assert ("google", "Medium_Campaign") not in tribunal.prophet_models
    assert ("google", "Medium_Campaign") in tribunal.xgb_models

    predictions = tribunal.predict(df, periods=(30,))
    row = predictions[("google", "Medium_Campaign")][30]

    assert row["prophet_p50"] is None
    assert row["xgb_p50"] is not None
    assert row["ridge_p50"] is not None
    assert row["revenue_p10"] <= row["revenue_p50"] <= row["revenue_p90"]


# ---- save/load pickle roundtrip -------------------------------------------

def test_save_load_roundtrip_produces_identical_predictions(tmp_path):
    df = _campaign_df("google", "Roundtrip_Campaign", "search", 40, seed=9)
    tribunal = ForecastingTribunal().fit(df)

    path = str(tmp_path / "model.pkl")
    ForecastingTribunal.save(tribunal, path)
    loaded = ForecastingTribunal.load(path)

    original = tribunal.predict(df, periods=(30,))
    reloaded = loaded.predict(df, periods=(30,))

    assert original[("google", "Roundtrip_Campaign")][30] == reloaded[("google", "Roundtrip_Campaign")][30]
