"""Layer 1: CSV -> features.parquet.

CLI: python src/generate_features.py --data-dir ./data --out features.parquet
"""
import argparse
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["date", "campaign_name", "spend", "revenue", "impressions", "clicks", "conversions"]

# Channel is inferred from filename, never hardcoded to a specific file.
CHANNEL_KEYWORDS = [
    ("google", "google"),
    ("facebook", "meta"),
    ("meta", "meta"),
    ("microsoft", "ms"),
    ("bing", "ms"),
    ("ms", "ms"),
]

# The real challenge dataset ships three genuinely different raw export
# schemas (Google Ads API report, Bing Ads report, Meta Ads report) - not
# variations on one naming convention. Each is mapped explicitly rather than
# through a shared alias table. `conversions`/`campaign_type` of None means
# that field isn't in this platform's export at all (Meta has neither).
GOOGLE_SCHEMA = {
    "date": "segments_date",
    "campaign_name": "campaign_name",
    "campaign_type": "campaign_advertising_channel_type",
    "spend": "metrics_cost_micros",  # Google reports cost in micros - divide by 1e6
    "revenue": "metrics_conversions_value",
    "impressions": "metrics_impressions",
    "clicks": "metrics_clicks",
    "conversions": "metrics_conversions",
}
BING_SCHEMA = {
    "date": "TimePeriod",
    "campaign_name": "CampaignName",
    "campaign_type": "CampaignType",
    "spend": "Spend",
    "revenue": "Revenue",
    "impressions": "Impressions",
    "clicks": "Clicks",
    "conversions": "Conversions",
}
META_SCHEMA = {
    "date": "date_start",
    "campaign_name": "campaign_name",
    "campaign_type": None,  # not present - inferred from campaign name
    "spend": "spend",
    # Meta's "conversion" column is conversion VALUE (revenue), not a count -
    # verified against the real export: values are fractional currency
    # amounts (e.g. 163.20, 286.77) that frequently exceed the click count,
    # and there is no separate conversion-count column in this export at all.
    "revenue": "conversion",
    "impressions": "impressions",
    "clicks": "clicks",
    "conversions": None,  # not available in this export - filled with 0
}

SCHEMA_DETECTORS = [
    ("google", "segments_date", GOOGLE_SCHEMA),
    ("bing", "TimePeriod", BING_SCHEMA),
    ("meta", "date_start", META_SCHEMA),
]

# Real platform "advertising channel type" enums, normalized (lowercased,
# whitespace/underscores stripped) to our canonical vocabulary. Anything not
# listed here falls back to "other". `search` is refined to `brand` below
# when the campaign name carries a `_TM_` (trademark/brand-term) marker -
# `_NTM_` (non-trademark) safely does NOT match that substring.
RAW_CAMPAIGN_TYPE_MAP = {
    "performancemax": "shopping",
    "search": "search",
    "shopping": "shopping",
    "display": "display",
    "video": "display",
    "demandgen": "display",
    "audience": "display",
}

# Used only when a file has no campaign_type column at all (Meta), or for our
# own clean sample schema if it omits the column. Checked in order - first
# match wins - so more specific intent signals (remarketing/prospecting) are
# checked before generic keywords like "brand"/"search".
CAMPAIGN_TYPE_KEYWORDS = [
    ("remarketing", "retargeting"),
    ("retarget", "retargeting"),
    ("prospecting", "display"),
    ("shopping", "shopping"),
    ("pmax", "shopping"),
    ("performance_max", "shopping"),
    ("brand", "brand"),
    ("search", "search"),
    ("display", "display"),
    ("generic", "search"),
]

# Generic alias table for our own clean sample CSV schema (date, spend,
# revenue, ... with obvious column names) - kept as a fallback for any file
# that doesn't match one of the three real schemas above.
COLUMN_ALIASES = {
    "date": "date",
    "campaign": "campaign_name",
    "campaign name": "campaign_name",
    "campaign_name": "campaign_name",
    "campaign type": "campaign_type",
    "campaign_type": "campaign_type",
    "cost": "spend",
    "spend": "spend",
    "amount spent": "spend",
    "amount spent (usd)": "spend",
    "revenue": "revenue",
    "conv. value": "revenue",
    "conversion value": "revenue",
    "purchase conversion value": "revenue",
    "impressions": "impressions",
    "clicks": "clicks",
    "conversions": "conversions",
    "purchases": "conversions",
}


def infer_channel(path):
    lower = os.path.basename(path).lower()
    for keyword, channel in CHANNEL_KEYWORDS:
        if keyword in lower:
            return channel
    raise ValueError(
        f"Cannot infer channel from filename '{path}'. Expected the filename to "
        "contain one of: google, meta/facebook, bing/microsoft/ms."
    )


def infer_campaign_type(campaign_name):
    lower = str(campaign_name).lower()
    for keyword, campaign_type in CAMPAIGN_TYPE_KEYWORDS:
        if keyword in lower:
            return campaign_type
    return "other"


def _normalize_type_key(raw_type):
    return re.sub(r"[\s_]+", "", str(raw_type).strip().lower())


def canonicalize_campaign_type(raw_type, campaign_name):
    canonical = RAW_CAMPAIGN_TYPE_MAP.get(_normalize_type_key(raw_type), "other")
    if canonical == "search" and "_tm_" in str(campaign_name).lower():
        canonical = "brand"
    return canonical


def detect_schema(columns):
    cols = set(columns)
    for schema_name, marker_column, schema in SCHEMA_DETECTORS:
        if marker_column in cols:
            return schema_name, schema
    return "generic", None


def normalize_columns(df):
    rename_map = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[key]
    return df.rename(columns=rename_map)


def _load_known_schema(raw, path, schema_name, schema):
    out = pd.DataFrame(index=raw.index)
    for field in ["date", "campaign_name", "spend", "revenue", "impressions", "clicks"]:
        source_column = schema[field]
        if source_column not in raw.columns:
            raise ValueError(
                f"{path} looks like a {schema_name} export but is missing expected column "
                f"'{source_column}'. Columns found: {list(raw.columns)}"
            )
        out[field] = raw[source_column]

    if schema_name == "google":
        out["spend"] = out["spend"] / 1_000_000  # micros -> currency units

    out["conversions"] = raw[schema["conversions"]] if schema["conversions"] else 0

    if schema["campaign_type"]:
        raw_types = raw[schema["campaign_type"]]
        out["campaign_type"] = [
            canonicalize_campaign_type(t, name) for t, name in zip(raw_types, out["campaign_name"])
        ]
    else:
        out["campaign_type"] = out["campaign_name"].apply(infer_campaign_type)

    return out


def _load_generic_schema(raw, path):
    df = normalize_columns(raw)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path} is missing required column(s): {missing}. "
            f"Columns found after normalization: {list(df.columns)}"
        )

    if "campaign_type" in df.columns:
        df["campaign_type"] = df["campaign_type"].astype(str).str.strip().str.lower()
    else:
        df["campaign_type"] = df["campaign_name"].apply(infer_campaign_type)

    return df


def load_channel_csv(path):
    raw = pd.read_csv(path)
    schema_name, schema = detect_schema(raw.columns)

    if schema is not None:
        df = _load_known_schema(raw, path, schema_name, schema)
    else:
        df = _load_generic_schema(raw, path)

    df["channel"] = infer_channel(path)
    df["date"] = pd.to_datetime(df["date"])
    return df[
        ["date", "channel", "campaign_name", "campaign_type", "spend", "revenue", "impressions", "clicks", "conversions"]
    ]


def load_all(data_dir):
    paths = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if not paths:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")
    return pd.concat((load_channel_csv(p) for p in paths), ignore_index=True)


def validate_campaign_consistency(df):
    """Each (channel, campaign_name) pair must map to exactly one campaign_type.

    Campaign names are NOT required to be unique across channels - the same
    name (e.g. "Pmax_NTM_Campaign_01") legitimately exists as different,
    unrelated campaigns in both the Google and Bing exports.
    """
    grouped = df.groupby(["channel", "campaign_name"]).agg(campaign_types=("campaign_type", "nunique"))
    bad = grouped[grouped["campaign_types"] > 1]
    if not bad.empty:
        raise ValueError(
            "Inconsistent campaign_type for the same (channel, campaign_name): "
            f"{list(bad.index)}. Each campaign must have a single campaign_type within its channel."
        )


def clean(df):
    before = len(df)
    df = df[df["spend"] >= 0].copy()
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped} row(s) with negative spend", file=sys.stderr)

    filled_groups = []
    for (channel, campaign_name, campaign_type), group in df.groupby(
        ["channel", "campaign_name", "campaign_type"], sort=False
    ):
        group = group.sort_values("date").set_index("date")
        full_range = pd.date_range(group.index.min(), group.index.max(), freq="D")
        group = group.reindex(full_range)
        group["channel"] = channel
        group["campaign_name"] = campaign_name
        group["campaign_type"] = campaign_type
        for col in ["spend", "revenue", "impressions", "clicks", "conversions"]:
            group[col] = group[col].fillna(0)
        group.index.name = "date"
        filled_groups.append(group.reset_index())

    return pd.concat(filled_groups, ignore_index=True)


def add_derived(df):
    df = df.sort_values(["channel", "campaign_name", "date"]).reset_index(drop=True)

    df["roas"] = np.where(df["spend"] > 0, df["revenue"] / df["spend"], 0.0)
    df["cvr"] = np.where(df["clicks"] > 0, df["conversions"] / df["clicks"], 0.0)
    df["cpc"] = np.where(df["clicks"] > 0, df["spend"] / df["clicks"], 0.0)

    df["month"] = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_q4"] = df["month"].isin([10, 11, 12])
    df["is_weekend"] = df["date"].dt.dayofweek >= 5

    grp = df.groupby(["channel", "campaign_name"], group_keys=False)
    df["lag_revenue_7d"] = grp["revenue"].shift(7).fillna(0)
    df["lag_revenue_28d"] = grp["revenue"].shift(28).fillna(0)
    df["rolling_mean_revenue_7d"] = grp["revenue"].transform(lambda s: s.rolling(7, min_periods=1).mean())
    df["rolling_mean_roas_7d"] = grp["roas"].transform(lambda s: s.rolling(7, min_periods=1).mean())

    spend_7d_ago = grp["spend"].shift(7)
    df["spend_growth_rate"] = np.where(
        spend_7d_ago > 0, (df["spend"] - spend_7d_ago) / spend_7d_ago, 0.0
    )

    return df


def build_features(data_dir):
    df = load_all(data_dir)
    validate_campaign_consistency(df)
    df = clean(df)
    df = add_derived(df)
    return df


def main():
    parser = argparse.ArgumentParser(description="Build features.parquet from raw channel CSVs")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    df = build_features(args.data_dir)
    df.to_parquet(args.out, index=False)
    print(f"Wrote {len(df)} rows x {len(df.columns)} cols to {args.out}")


if __name__ == "__main__":
    main()
