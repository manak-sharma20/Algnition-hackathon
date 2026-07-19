# AIgnition 3.0 — Probabilistic Revenue Forecasting

**Three models. One verdict.** Honest uncertainty, not a guess dressed up as a number.

**Team:** Manak · Jain · Ipshita
**Hackathon:** AIgnition 3.0 by NetElixir
**Python version:** 3.11

---

## The problem

Agencies plan media budgets on single-point revenue forecasts with no signal of how much to trust them. Worse, the raw data lives in three genuinely incompatible export formats — Google Ads, Meta Ads, and Microsoft (Bing) Ads each ship different column names, units, and quirks that must be reconciled before any forecasting can happen.

## What this does

Forecasts e-commerce revenue and ROAS per campaign across **Google Ads, Meta Ads, and Microsoft Ads** using a three-model ensemble — **Prophet + XGBoost + Ridge Regression** (the "Forecasting Tribunal"). Every forecast is a **P10 / P50 / P90 probability range** over 30/60/90-day planning windows:

- **P10 — worst case:** a conservative floor for risk-aware planning
- **P50 — expected:** the blended ensemble median
- **P90 — best case:** the upside scenario for stretch targets

The spread between the three models' independent P50 predictions becomes a **disagreement score**, classified LOW / MODERATE / HIGH — the forecast's built-in confidence signal, not a bolted-on afterthought. An LLM layer (Groq free tier, called on demand from the UI) turns disagreements and risks into plain-English narration.

## Architecture at a glance

```
Raw CSVs ──► Feature Generation ──► Train (Tribunal) ──► Predict
(3 schemas)   (features.parquet)     (pickle/model.pkl)   (predictions.csv)
```

1. **`src/generate_features.py`** — detects each platform's raw export schema explicitly (Google's cost-in-micros, Meta's `conversion` column actually being revenue, Bing's PascalCase report format), canonicalizes campaign types (including the `_TM_`/`_NTM_` brand-term signal), gap-fills missing dates, and derives lags, rolling means, and calendar features.
2. **`src/train.py`** — fits one Prophet + XGBoost (native multi-quantile regression) + Ridge (residual-bootstrap intervals) per campaign, keyed by `(channel, campaign_name)` because the same campaign name legitimately exists on more than one platform. Campaigns with under 10 rows are skipped (naive fallback at predict time); Prophet additionally requires 60+ days of history. Persists a single gzip-compressed pickle.
3. **`src/predict.py`** — blends the three models' P10/P50/P90 with data-driven ensemble weights, widens the blended interval to honest empirical coverage, computes the disagreement score, and writes the scored CSV. Campaigns unseen at training time get a trailing-average naive fallback flagged HIGH uncertainty instead of silently vanishing.

The pipeline is **fully offline** — no network calls anywhere in `run.sh`. Only the UI's on-demand narration touches the network.

## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run (one command)

```bash
./run.sh [DATA_DIR] [MODEL_PATH] [OUTPUT_PATH]
```

Defaults: `DATA_DIR=./data`, `MODEL_PATH=./pickle/model.pkl`, `OUTPUT_PATH=./output/predictions.csv`

```bash
./run.sh                                              # everything default
./run.sh ./my_data ./pickle/model.pkl ./out/pred.csv  # custom paths
```

Produces 408 prediction rows across 136 real campaigns. No network calls. No manual steps.

## Output

`run.sh` writes two files next to `OUTPUT_PATH`:

- **`predictions.csv`** — the scored output, exactly these columns in exactly this order (nothing appended, per the submission guide's strict format requirement):
  ```
  channel, campaign_type, campaign_name, period_days,
  revenue_p10, revenue_p50, revenue_p90,
  roas_p10, roas_p50, roas_p90,
  disagreement_pct, uncertainty_level
  ```
- **`predictions_detail.csv`** — the same rows plus `prophet_p50, xgb_p50, ridge_p50` (blank when that model was skipped for a campaign), used by the War Room UI's per-model agreement badges. Not scored.

### Future budget inputs

`src/predict.py` accepts an optional `--budgets path/to/budgets.csv` (columns: `channel,campaign_name,daily_budget`) to forecast against a specified future media budget per campaign instead of assuming trailing spend continues. This satisfies the brief's "accepting future media budget inputs" from the CLI side; the War Room UI's budget simulator is the interactive side of the same capability.

## Input CSV format

`data/` ships the real challenge dataset (`google_ads_campaign_stats.csv`, `bing_campaign_stats.csv`, `meta_ads_campaign_stats.csv`) — the pipeline is built against these actual raw exports, not a guessed clean schema. Place CSVs in `DATA_DIR` with filenames containing a channel keyword — `google`, `meta`/`facebook`, or `bing`/`microsoft`/`ms` — anywhere in the name.

Each platform's schema is detected and mapped explicitly; a generic alias-based fallback handles any other reasonable CSV shape. Full column-by-column mapping and every quirk found in the real data: `docs/SCHEMA_ANALYSIS.md`.

## Train (one-time)

```bash
python src/train.py --data-dir ./data --out ./pickle/model.pkl
```

## Validated accuracy (rolling-origin backtest)

```bash
python src/backtest.py --data-dir ./data --holdout-days 30 --cutoffs 4 --output backtest_results.csv
```

Every other check in this repo verifies internal consistency; the backtest measures real accuracy — it holds out data after one or more cutoff dates, trains fresh on everything before each cutoff, forecasts forward, and scores against what actually happened. Pooled across 4 non-overlapping 30-day windows (163 campaign-forecasts):

| Metric | Result |
|---|---|
| MAE improvement over naive trailing-rate baseline | **20.0%** |
| P10–P90 empirical coverage (nominal target 80%) | **81.6%** |
| Uncertainty labels vs. actual error | Cleanly monotonic (LOW $245 < MODERATE $4.4k < HIGH $5.5k) |

The ensemble weights and interval width are **data-driven** — tuned from this backtest's per-model error breakdown, not from intuition. Honest remaining gaps (median absolute error, MAPE) are documented in `docs/TECHNICAL_DOC.md` rather than hidden.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

58 automated tests covering the highest-risk logic: per-platform schema mapping and campaign-type canonicalization (including the `_TM_`/`_NTM_` brand signal), P10≤P50≤P90 monotonicity for all three models, composite `(channel, campaign_name)` keying (the fix for real cross-channel name collisions), the naive-fallback path for sparse/unseen campaigns, and the backtest harness itself.

## Frontend — the War Room UI

Four views, one risk dial:

- **Command** — per-channel budget, ROAS health bar (green >4x / amber 2–4x / red <2x), revenue ranges
- **Tribunal** — campaign rows with per-model agreement badges, disagreement flagged
- **Battle** — compare budget allocations side by side with live recompute
- **P10/P50/P90 Risk Dial** — persistent dock that reshuffles every view between worst/expected/best case, with AI narration on click

```bash
cd frontend
npm install
cp .env.example .env   # add your free Groq key: https://console.groq.com/keys
npm run dev            # local dev server
npm run build          # production build (static, deployable anywhere)
```

The UI is a fully static Vite + React app — it reads `predictions.csv` at load and needs no backend. Its AI features (disagreement explanations, risk list, allocation comparison) call Groq's API directly from the browser on button click only, using the key in `frontend/.env` (gitignored, never committed). The offline pipeline needs no key at all.

## Repository layout

```
run.sh                    # the one-command scored pipeline
src/
  generate_features.py    # Layer 1: raw CSVs -> features.parquet
  train.py                # Layer 2: fit the tribunal -> pickle/model.pkl
  predict.py              # Layer 3: pickle + features -> predictions.csv
  backtest.py             # rolling-origin accuracy validation (not in run.sh)
  models/
    tribunal.py           # ensemble blend, disagreement score, fallbacks
    prophet_model.py      # coherent sample-path intervals
    xgb_model.py          # native multi-quantile regression
    ridge_model.py        # residual-bootstrap intervals
data/                     # the real challenge dataset (3 raw exports)
pickle/model.pkl          # trained tribunal (gzip-compressed)
output/                   # predictions.csv + predictions_detail.csv
frontend/                 # War Room UI (Vite + React, static)
tests/                    # 58 automated tests
docs/                     # architecture, assumptions, schema analysis, technical doc
```

## Documentation

- `docs/ARCHITECTURE.md` — full pipeline and UI architecture
- `docs/ASSUMPTIONS.md` — every modeling and product tradeoff, stated plainly
- `docs/SCHEMA_ANALYSIS.md` — column-by-column mapping of all three raw exports
- `docs/TECHNICAL_DOC.md` — models, intervals, backtest methodology and results, honest gaps
