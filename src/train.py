"""Fits the ForecastingTribunal on the raw channel CSVs and pickles it.

Not called from run.sh - this is the one-time (or re-run-when-data-changes)
training step. run.sh only calls generate_features.py and predict.py.

CLI: python src/train.py --data-dir ./data --out ./pickle/model.pkl
"""
import argparse

from generate_features import build_features
from models.tribunal import ForecastingTribunal


def main():
    parser = argparse.ArgumentParser(description="Train the ForecastingTribunal and save it as a pickle")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    df = build_features(args.data_dir)
    tribunal = ForecastingTribunal().fit(df)
    ForecastingTribunal.save(tribunal, args.out)

    # Never leave the pickle untested - confirm it loads back cleanly before reporting success.
    ForecastingTribunal.load(args.out)

    print(
        f"Trained on {len(df)} rows across {df['campaign_name'].nunique()} campaigns. "
        f"Saved and verified pickle at {args.out}"
    )


if __name__ == "__main__":
    main()
