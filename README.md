# AIgnition 3.0 — Probabilistic Revenue Forecasting

**Team:** Manak · Jain · Ipshita  
**Python version:** 3.11  
**Hackathon:** AIgnition 3.0 by NetElixir

## What this does

Forecasts e-commerce revenue across Google Ads, Meta Ads, and Microsoft Ads using a three-model ensemble (Prophet + XGBoost + Ridge Regression). Each forecast produces a P10/P50/P90 probability range for 30/60/90-day planning periods. An LLM (Groq, free tier) provides plain-English explanations of model disagreements and operational risks via the War Room UI — see `docs/ARCHITECTURE.md` for the full pipeline and `docs/ASSUMPTIONS.md` for the modeling and product tradeoffs made along the way.

## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
./run.sh [DATA_DIR] [MODEL_PATH] [OUTPUT_PATH]
```

Defaults:
- `DATA_DIR` = `./data`
- `MODEL_PATH` = `./pickle/model.pkl`
- `OUTPUT_PATH` = `./output/predictions.csv`

Example with defaults:
```bash
./run.sh
```

Example with custom paths:
```bash
./run.sh ./my_data ./pickle/model.pkl ./output/predictions.csv
```

## Output

`run.sh` writes two files next to `OUTPUT_PATH`:

- **`predictions.csv`** — the scored output, exactly these columns in exactly this order (nothing appended, per the submission guide's strict format requirement):
  ```
  channel, campaign_type, campaign_name, period_days,
  revenue_p10, revenue_p50, revenue_p90,
  roas_p10, roas_p50, roas_p90,
  disagreement_pct, uncertainty_level
  ```
- **`predictions_detail.csv`** — the same rows plus `prophet_p50, xgb_p50, ridge_p50` (blank when that model was skipped for a campaign), used by the War Room UI's per-model agreement badges. Not scored; see `docs/ARCHITECTURE.md`.

`src/predict.py` also accepts an optional `--budgets path/to/budgets.csv` (columns: `channel,campaign_name,daily_budget`) to forecast against a specified future media budget per campaign instead of assuming trailing spend continues — this is what satisfies the brief's "accepting future media budget inputs" from the CLI/`run.sh` side (the War Room UI's budget simulator is the other, interactive side of this).

## Input CSV format

`data/` ships the real challenge dataset (`google_ads_campaign_stats.csv`, `bing_campaign_stats.csv`, `meta_ads_campaign_stats.csv`) — the pipeline is built against these actual raw exports, not a guessed clean schema. Place CSVs in `DATA_DIR` with filenames containing a channel keyword — `google`, `meta`/`facebook`, or `bing`/`microsoft`/`ms` — anywhere in the name (not a fixed prefix).

Google, Bing, and Meta each export a genuinely different raw schema (different column names, Google's spend in micros, Meta's `conversion` column actually being revenue) — `generate_features.py` detects and maps each one explicitly. A generic alias-based fallback also exists for any other CSV shape. Full column-by-column mapping and every quirk found in the real data: `docs/SCHEMA_ANALYSIS.md`. Modeling/product tradeoffs made along the way: `docs/ASSUMPTIONS.md`.

## Train (one-time)

```bash
python src/train.py --data-dir ./data --out ./pickle/model.pkl
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Covers the highest-risk logic: per-platform schema mapping and campaign-type canonicalization (including the `_TM_`/`_NTM_` brand signal), P10≤P50≤P90 monotonicity for all three models, composite `(channel, campaign_name)` keying (the fix for real cross-channel name collisions), and the naive-fallback path for sparse/unseen campaigns. Not part of `run.sh` or the scored pipeline.

## Frontend (War Room UI)

```bash
cd frontend
npm install
cp .env.example .env   # add your free Groq key: https://console.groq.com/keys
npm run dev
```

The UI's AI features (disagreement explanations, risk list, allocation comparison) need a Groq API key in `frontend/.env` (gitignored, never commit it). The offline pipeline above needs no key at all.
