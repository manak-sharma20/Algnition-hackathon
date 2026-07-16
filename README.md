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

`predictions.csv` with columns:
```
channel, campaign_type, campaign_name, period_days,
revenue_p10, revenue_p50, revenue_p90,
roas_p10, roas_p50, roas_p90,
disagreement_pct, uncertainty_level,
prophet_p50, xgb_p50, ridge_p50   (appended - used by the War Room UI, see docs/ARCHITECTURE.md)
```

## Input CSV format

Place CSVs in `DATA_DIR` with filenames containing a channel keyword — `google`, `meta`/`facebook`, or `bing`/`microsoft`/`ms` — anywhere in the name (not a fixed prefix; this covers both the bundled samples and the real challenge dataset's filenames).

Required columns: `date`, `campaign_name`, `spend`, `revenue`, `impressions`, `clicks`, `conversions`. `campaign_type` is optional — inferred from the campaign name if absent. Common alternate column names (e.g. `Cost` for `spend`) are normalized automatically; see `docs/ASSUMPTIONS.md`.

## Train (one-time)

```bash
python src/train.py --data-dir ./data --out ./pickle/model.pkl
```

## Frontend (War Room UI)

```bash
cd frontend
npm install
cp .env.example .env   # add your free Groq key: https://console.groq.com/keys
npm run dev
```

The UI's AI features (disagreement explanations, risk list, allocation comparison) need a Groq API key in `frontend/.env` (gitignored, never commit it). The offline pipeline above needs no key at all.
