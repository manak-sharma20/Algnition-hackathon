"""Held-out backtest: how accurate are the tribunal's forecasts, really?

Everything verified elsewhere in this pipeline (no NaNs, P10<=P50<=P90,
right shape) is internal consistency, not accuracy. This holds out data
after one or more cutoff dates, trains a fresh tribunal on everything
before each cutoff, forecasts holdout-days ahead, and compares against
what actually happened - real MAE/RMSE, median absolute percentage error,
P10-P90 empirical coverage, and a comparison against a naive "revenue
stays at its trailing rate" baseline.

--cutoffs N runs a rolling-origin evaluation across N non-overlapping
windows walking backwards from the end of the data (cutoff_i = max_date -
i * holdout_days), which is far more trustworthy than any single window: a
single cutoff can't distinguish real miscalibration from one unlucky
period.

Not called from run.sh - a one-time (or occasional) evaluation tool, not
part of the scored pipeline.

CLI: python src/backtest.py --data-dir ./data --holdout-days 30 --cutoffs 4 --output backtest_results.csv
"""
import argparse

import numpy as np
import pandas as pd

from generate_features import build_features
from models.tribunal import ForecastingTribunal


def evaluate_cutoff(df, cutoff, holdout_days):
    """Train a fresh tribunal on data through `cutoff`, forecast
    holdout_days ahead, and score against the actuals in that window.
    Returns a per-campaign result DataFrame (possibly empty).
    """
    train_df = df[df["date"] <= cutoff].copy()
    test_df = df[(df["date"] > cutoff) & (df["date"] <= cutoff + pd.Timedelta(days=holdout_days))].copy()
    if train_df.empty or test_df.empty:
        return pd.DataFrame()

    tribunal = ForecastingTribunal().fit(train_df)
    predictions = tribunal.predict(train_df, periods=(holdout_days,))

    actual_revenue = test_df.groupby(["channel", "campaign_name"])["revenue"].sum()

    # Naive baseline: "revenue stays at its trailing 28-day rate" - what the
    # tribunal should be beating, not just a well-formed number.
    def _trailing_daily_rate(group):
        return group.sort_values("date")["revenue"].tail(28).mean()

    baseline_daily = train_df.groupby(["channel", "campaign_name"]).apply(_trailing_daily_rate, include_groups=False)

    rows = []
    for key, campaign_periods in predictions.items():
        if key not in actual_revenue.index:
            continue  # campaign has no data in the held-out window - can't evaluate it
        channel, campaign_name = key
        actual = actual_revenue.loc[key]
        pred = campaign_periods[holdout_days]
        baseline_pred = (
            baseline_daily.loc[key] * holdout_days if key in baseline_daily.index else np.nan
        )

        rows.append({
            "cutoff": cutoff.date(),
            "channel": channel,
            "campaign_name": campaign_name,
            "actual_revenue": actual,
            "predicted_p10": pred["revenue_p10"],
            "predicted_p50": pred["revenue_p50"],
            "predicted_p90": pred["revenue_p90"],
            "naive_baseline": baseline_pred,
            "abs_error": abs(actual - pred["revenue_p50"]),
            "baseline_abs_error": abs(actual - baseline_pred) if pd.notna(baseline_pred) else np.nan,
            "ape_pct": abs(actual - pred["revenue_p50"]) / actual * 100 if actual > 0 else np.nan,
            "within_p10_p90": pred["revenue_p10"] <= actual <= pred["revenue_p90"],
            "uncertainty_level": pred["uncertainty_level"],
            "prophet_abs_error": abs(actual - pred["prophet_p50"]) if pred["prophet_p50"] is not None else np.nan,
            "xgb_abs_error": abs(actual - pred["xgb_p50"]) if pred["xgb_p50"] is not None else np.nan,
            "ridge_abs_error": abs(actual - pred["ridge_p50"]) if pred["ridge_p50"] is not None else np.nan,
        })

    return pd.DataFrame(rows)


def summarize(result_df, label):
    mae = result_df["abs_error"].mean()
    med_ae = result_df["abs_error"].median()
    rmse = np.sqrt((result_df["abs_error"] ** 2).mean())
    med_ape = result_df["ape_pct"].median()
    coverage = result_df["within_p10_p90"].mean() * 100
    baseline_mae = result_df["baseline_abs_error"].mean()
    baseline_med_ae = result_df["baseline_abs_error"].median()
    improvement = (1 - mae / baseline_mae) * 100 if baseline_mae > 0 else float("nan")

    print(f"--- {label} ({len(result_df)} campaign-windows) ---")
    print(f"Tribunal MAE:    ${mae:,.2f}   median AE: ${med_ae:,.2f}   RMSE: ${rmse:,.2f}")
    print(f"Baseline MAE:    ${baseline_mae:,.2f}   median AE: ${baseline_med_ae:,.2f}")
    print(f"Improvement over naive baseline (MAE): {improvement:.1f}%")
    print(f"Median absolute percentage error: {med_ape:.1f}%")
    print(f"P10-P90 empirical coverage: {coverage:.1f}% (nominal target: 80%)")
    for model in ("prophet", "xgb", "ridge"):
        col = f"{model}_abs_error"
        n = result_df[col].notna().sum()
        if n:
            print(f"  {model:8s} MAE (n={n}): ${result_df[col].mean():,.2f}")


def main():
    parser = argparse.ArgumentParser(description="Backtest the tribunal against real held-out data")
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--holdout-days", type=int, default=30)
    parser.add_argument(
        "--cutoffs", type=int, default=1,
        help="Number of rolling-origin cutoffs (non-overlapping windows walking back from the end of the data)",
    )
    parser.add_argument("--output", default=None, help="Optional CSV path for per-campaign backtest results")
    args = parser.parse_args()

    df = build_features(args.data_dir)
    max_date = df["date"].max()
    print(f"Full data: {df['date'].min().date()} to {max_date.date()}\n")

    all_results = []
    for i in range(1, args.cutoffs + 1):
        cutoff = max_date - pd.Timedelta(days=args.holdout_days * i)
        result_df = evaluate_cutoff(df, cutoff, args.holdout_days)
        if result_df.empty:
            print(f"Cutoff {cutoff.date()}: no campaigns evaluable, skipping")
            continue
        summarize(result_df, f"Cutoff {cutoff.date()}")
        print()
        all_results.append(result_df)

    if not all_results:
        print("No evaluable windows - nothing to report.")
        return

    pooled = pd.concat(all_results, ignore_index=True)
    if len(all_results) > 1:
        summarize(pooled, "POOLED across all cutoffs")

    by_uncertainty = pooled.groupby("uncertainty_level")["abs_error"].mean().sort_values()
    print(
        "\nMean absolute error by uncertainty_level (should increase LOW -> MODERATE -> HIGH "
        "if the disagreement score is well-calibrated):"
    )
    print(by_uncertainty.to_string())

    if args.output:
        pooled.to_csv(args.output, index=False)
        print(f"\nPer-campaign results written to {args.output}")


if __name__ == "__main__":
    main()
