"""Loads the trained pickle + features.parquet, runs the tribunal, and
writes predictions.csv in the exact required column order.

CLI: python src/predict.py --features features.parquet --model ./pickle/model.pkl --output ./output/predictions.csv
"""
import argparse
import os

import pandas as pd

from models.tribunal import ForecastingTribunal

OUTPUT_COLUMNS = [
    "channel",
    "campaign_type",
    "campaign_name",
    "period_days",
    "revenue_p10",
    "revenue_p50",
    "revenue_p90",
    "roas_p10",
    "roas_p50",
    "roas_p90",
    "disagreement_pct",
    "uncertainty_level",
]


def main():
    parser = argparse.ArgumentParser(description="Run the tribunal and write predictions.csv")
    parser.add_argument("--features", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_parquet(args.features)
    tribunal = ForecastingTribunal.load(args.model)

    predictions = tribunal.predict(df, periods=(30, 60, 90))

    rows = []
    for campaign_periods in predictions.values():
        for row in campaign_periods.values():
            rows.append(row)

    out_df = pd.DataFrame(rows)[OUTPUT_COLUMNS]
    out_df = out_df.sort_values(["channel", "campaign_type", "campaign_name", "period_days"]).reset_index(drop=True)

    for col in ["revenue_p10", "revenue_p50", "revenue_p90", "roas_p10", "roas_p50", "roas_p90"]:
        out_df[col] = out_df[col].round(2)
    out_df["disagreement_pct"] = out_df["disagreement_pct"].round(1)

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    out_df.to_csv(args.output, index=False)
    print(f"Wrote {len(out_df)} rows to {args.output}")


if __name__ == "__main__":
    main()
