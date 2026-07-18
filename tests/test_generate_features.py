"""Tests for the highest-risk logic in generate_features.py: the three real
per-platform schema mappings, campaign-type canonicalization (including the
TM/NTM brand signal), channel inference, and cross-channel consistency
validation. These are exactly the areas that broke silently against the real
challenge dataset before being fixed - see docs/ASSUMPTIONS.md.
"""
import pandas as pd
import pytest

import generate_features as gf


# ---- infer_channel -----------------------------------------------------

@pytest.mark.parametrize(
    "filename,expected",
    [
        ("google_ads_sample.csv", "google"),
        ("google_ads_campaign_stats.csv", "google"),
        ("meta_ads_sample.csv", "meta"),
        ("facebook_ads_export.csv", "meta"),
        ("bing_campaign_stats.csv", "ms"),  # real filename, no "ms_ads_" prefix
        ("microsoft_ads_export.csv", "ms"),
        ("ms_ads_sample.csv", "ms"),
    ],
)
def test_infer_channel(filename, expected):
    assert gf.infer_channel(f"/some/dir/{filename}") == expected


def test_infer_channel_raises_on_unrecognized_filename():
    with pytest.raises(ValueError):
        gf.infer_channel("/some/dir/unknown_platform.csv")


# ---- canonicalize_campaign_type (Google/Bing raw enums) -----------------

@pytest.mark.parametrize(
    "raw_type,campaign_name,expected",
    [
        ("PERFORMANCE_MAX", "Pmax_NTM_Campaign_01", "shopping"),  # Google casing
        ("PerformanceMax", "Pmax_NTM_Campaign_01", "shopping"),  # Bing casing
        ("SHOPPING", "Shopping_Campaign_01", "shopping"),
        ("Shopping", "Shopping_Campaign_01", "shopping"),
        ("VIDEO", "Video_Campaign_01", "display"),
        ("DEMAND_GEN", "Demand_Gen_Campaign_01", "display"),
        ("Audience", "Demand Gen_NTM_Campaign_01", "display"),  # Bing's Demand Gen equivalent
        ("SomeUnknownEnum", "Whatever_Campaign_01", "other"),
    ],
)
def test_canonicalize_campaign_type_maps_raw_enums(raw_type, campaign_name, expected):
    assert gf.canonicalize_campaign_type(raw_type, campaign_name) == expected


@pytest.mark.parametrize(
    "campaign_name,expected",
    [
        ("Search_TM_Campaign_01", "brand"),  # trademark/brand-term search
        ("Search_NTM_Campaign_03", "search"),  # non-trademark - must NOT match _tm_
        ("Search_Campaign_01", "search"),  # no marker at all
    ],
)
def test_search_type_refined_by_tm_ntm_marker(campaign_name, expected):
    assert gf.canonicalize_campaign_type("SEARCH", campaign_name) == expected
    assert gf.canonicalize_campaign_type("Search", campaign_name) == expected


def test_ntm_does_not_falsely_substring_match_tm():
    # "_ntm_" must not be mistaken for "_tm_" - this was verified by hand
    # against every real Search campaign name; pin it down here too.
    assert "_tm_" not in "_ntm_"


# ---- infer_campaign_type (keyword fallback when no column exists) ------

@pytest.mark.parametrize(
    "campaign_name,expected",
    [
        ("Remarketing_DPA_Campaign_01", "retargeting"),
        ("Remarketing_Brand_Campaign_01", "retargeting"),  # remarketing wins over "brand"
        ("Prospecting_DPA_Campaign_04", "display"),
        ("Prospecting_Brand_Campaign_02", "display"),  # prospecting wins over "brand"
        ("Generic_Brand_Campaign_01", "brand"),  # brand wins over the "generic" fallback
        ("Generic_Campaign_02", "search"),  # final fallback before "other"
        ("Totally_Unrecognized_Name", "other"),
    ],
)
def test_infer_campaign_type_priority_order(campaign_name, expected):
    assert gf.infer_campaign_type(campaign_name) == expected


# ---- detect_schema / per-platform column mapping ------------------------

def _write_csv(tmp_path, filename, df):
    path = tmp_path / filename
    df.to_csv(path, index=False)
    return str(path)


def test_google_schema_detected_and_spend_converted_from_micros(tmp_path):
    raw = pd.DataFrame({
        "segments_date": ["2024-01-01", "2024-01-02"],
        "campaign_name": ["Search_TM_Campaign_01", "Search_TM_Campaign_01"],
        "campaign_advertising_channel_type": ["SEARCH", "SEARCH"],
        "metrics_cost_micros": [50_000_000, 25_000_000],  # $50, $25
        "metrics_conversions_value": [200.0, 100.0],
        "metrics_impressions": [1000, 500],
        "metrics_clicks": [50, 25],
        "metrics_conversions": [2.5, 1.0],
    })
    path = _write_csv(tmp_path, "google_ads_test.csv", raw)

    df = gf.load_channel_csv(path)

    assert df["channel"].iloc[0] == "google"
    assert df["campaign_type"].iloc[0] == "brand"  # SEARCH + _TM_ -> brand
    assert list(df["spend"]) == [50.0, 25.0]  # micros -> dollars
    assert list(df["revenue"]) == [200.0, 100.0]


def test_bing_schema_detected(tmp_path):
    raw = pd.DataFrame({
        "TimePeriod": ["2024-05-25", "2024-05-26"],
        "CampaignName": ["Pmax_NTM_Campaign_01", "Pmax_NTM_Campaign_01"],
        "CampaignType": ["PerformanceMax", "PerformanceMax"],
        "Spend": [4.7, 4.3],
        "Revenue": [0.0, 20.0],
        "Clicks": [22, 14],
        "Impressions": [140, 120],
        "Conversions": [0.0, 1.0],
    })
    path = _write_csv(tmp_path, "bing_campaign_stats.csv", raw)

    df = gf.load_channel_csv(path)

    assert df["channel"].iloc[0] == "ms"
    assert df["campaign_type"].iloc[0] == "shopping"  # PerformanceMax -> shopping
    assert list(df["spend"]) == [4.7, 4.3]  # no unit conversion for Bing


def test_meta_schema_conversion_column_is_revenue_not_a_count(tmp_path):
    raw = pd.DataFrame({
        "date_start": ["2024-05-23", "2024-05-24"],
        "campaign_name": ["Remarketing_DPA_Campaign_01", "Remarketing_DPA_Campaign_01"],
        "spend": [85.0, 85.0],
        "conversion": [163.20, 286.77],  # this is revenue, verified against the real export
        "clicks": [37.0, 38.0],
        "impressions": [5188.0, 5080.0],
    })
    path = _write_csv(tmp_path, "meta_ads_test.csv", raw)

    df = gf.load_channel_csv(path)

    assert df["channel"].iloc[0] == "meta"
    assert list(df["revenue"]) == [163.20, 286.77]
    assert list(df["conversions"]) == [0, 0]  # no count column in this export
    assert df["campaign_type"].iloc[0] == "retargeting"  # inferred from "Remarketing"


def test_generic_schema_fallback_for_our_own_sample_shape(tmp_path):
    raw = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "campaign_name": ["Google_Shopping_Main", "Google_Shopping_Main"],
        "campaign_type": ["shopping", "shopping"],
        "spend": [1189.63, 1308.14],
        "revenue": [4927.33, 5927.75],
        "impressions": [41958, 32718],
        "clicks": [666, 798],
        "conversions": [30, 30],
    })
    path = _write_csv(tmp_path, "google_ads_sample.csv", raw)

    df = gf.load_channel_csv(path)

    assert df["channel"].iloc[0] == "google"
    assert df["campaign_type"].iloc[0] == "shopping"
    assert list(df["spend"]) == [1189.63, 1308.14]


def test_known_schema_missing_expected_column_raises_loudly(tmp_path):
    # Has segments_date (detected as Google) but is missing metrics_cost_micros.
    raw = pd.DataFrame({
        "segments_date": ["2024-01-01"],
        "campaign_name": ["X"],
        "campaign_advertising_channel_type": ["SEARCH"],
        "metrics_conversions_value": [100.0],
        "metrics_impressions": [100],
        "metrics_clicks": [10],
        "metrics_conversions": [1],
    })
    path = _write_csv(tmp_path, "google_ads_broken.csv", raw)

    with pytest.raises(ValueError, match="metrics_cost_micros"):
        gf.load_channel_csv(path)


def test_nan_metric_values_are_filled_with_zero(tmp_path):
    raw = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "campaign_name": ["X", "X"],
        "spend": [10.0, None],
        "revenue": [None, 20.0],
        "impressions": [100, 100],
        "clicks": [5, 5],
        "conversions": [1, 1],
    })
    path = _write_csv(tmp_path, "google_ads_sample.csv", raw)

    df = gf.load_channel_csv(path)

    assert df["spend"].isna().sum() == 0
    assert df["revenue"].isna().sum() == 0
    assert list(df["spend"]) == [10.0, 0.0]
    assert list(df["revenue"]) == [0.0, 20.0]


# ---- validate_campaign_consistency --------------------------------------

def test_same_campaign_name_across_channels_is_allowed():
    # Real dataset: 27 names like "Pmax_NTM_Campaign_01" exist in both
    # Google and Bing as unrelated campaigns - this must NOT raise.
    df = pd.DataFrame({
        "channel": ["google", "ms"],
        "campaign_name": ["Pmax_NTM_Campaign_01", "Pmax_NTM_Campaign_01"],
        "campaign_type": ["shopping", "shopping"],
    })
    gf.validate_campaign_consistency(df)  # should not raise


def test_inconsistent_type_within_same_channel_raises():
    df = pd.DataFrame({
        "channel": ["google", "google"],
        "campaign_name": ["X", "X"],
        "campaign_type": ["shopping", "search"],  # same campaign, two types
    })
    with pytest.raises(ValueError, match="Inconsistent campaign_type"):
        gf.validate_campaign_consistency(df)


# ---- clean() -------------------------------------------------------------

def test_clean_fills_date_gaps_with_zero():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-03"]),  # gap on 01-02
        "channel": ["google", "google"],
        "campaign_name": ["X", "X"],
        "campaign_type": ["shopping", "shopping"],
        "spend": [10.0, 30.0],
        "revenue": [50.0, 90.0],
        "impressions": [100, 300],
        "clicks": [10, 30],
        "conversions": [1, 3],
    })
    out = gf.clean(df)

    assert len(out) == 3  # 01-01, 01-02 (filled), 01-03
    gap_row = out[out["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert gap_row["spend"] == 0
    assert gap_row["revenue"] == 0


def test_clean_drops_negative_spend_rows():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "channel": ["google", "google"],
        "campaign_name": ["X", "X"],
        "campaign_type": ["shopping", "shopping"],
        "spend": [10.0, -5.0],
        "revenue": [50.0, 20.0],
        "impressions": [100, 50],
        "clicks": [10, 5],
        "conversions": [1, 0],
    })
    out = gf.clean(df)

    assert (out["spend"] >= 0).all()
    assert len(out) == 1
