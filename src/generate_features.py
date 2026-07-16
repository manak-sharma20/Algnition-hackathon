"""Layer 1: CSV -> features.parquet.

CLI: python src/generate_features.py --data-dir ./data --out features.parquet
"""
import argparse
import glob
import os
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

# Real ad-platform exports don't share one column-naming convention, so incoming
# headers are normalized (case/whitespace-insensitive) against this alias table
# before the required-column check runs.
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

# Used only when a file has no campaign_type column at all.
CAMPAIGN_TYPE_KEYWORDS = [
    ("shopping", "shopping"),
    ("pmax", "shopping"),
    ("performance_max", "shopping"),
    ("brand", "brand"),
    ("retarget", "retargeting"),
    ("prospecting", "display"),
    ("search", "search"),
    ("display", "display"),
]


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


def normalize_columns(df):
    rename_map = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[key]
    return df.rename(columns=rename_map)


def load_channel_csv(path):
    df = pd.read_csv(path)
    df = normalize_columns(df)

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
    """Each campaign_name must map to exactly one channel and one campaign_type."""
    grouped = df.groupby("campaign_name").agg(
        channels=("channel", "nunique"),
        campaign_types=("campaign_type", "nunique"),
    )
    bad = grouped[(grouped["channels"] > 1) | (grouped["campaign_types"] > 1)]
    if not bad.empty:
        raise ValueError(
            "Inconsistent campaign_name -> channel/campaign_type mapping found for: "
            f"{list(bad.index)}. A campaign_name must belong to a single channel and campaign_type."
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
