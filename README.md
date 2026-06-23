# AIgnition 3.0 — Probabilistic Revenue Forecasting

**Team:** Manak · Jain · Ipshita  
**Python version:** 3.11  
**Hackathon:** AIgnition 3.0 by NetElixir

## What this does

Forecasts e-commerce revenue across Google Ads, Meta Ads, and Microsoft Ads using a three-model ensemble (Prophet + XGBoost + Ridge Regression). Each forecast produces a P10/P50/P90 probability range. Claude provides plain-English explanations of model disagreements and risks via the War Room UI.

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
disagreement_pct, uncertainty_level
```

## Input CSV format

Place CSVs in `DATA_DIR` with filenames prefixed by channel:
- `google_ads_*.csv`
- `meta_ads_*.csv`
- `ms_ads_*.csv`

Required columns: `date`, `campaign_name`, `campaign_type`, `spend`, `revenue`, `impressions`, `clicks`, `conversions`

## Train (one-time)

```bash
python src/train.py --data-dir ./data --out ./pickle/model.pkl
```

## Frontend (War Room UI)

```bash
cd frontend
npm install
npm run dev
```
