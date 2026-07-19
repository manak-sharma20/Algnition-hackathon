# Architecture Overview
*AIgnition 3.0 — Probabilistic Revenue Forecasting*

## Stack

**Backend / forecasting pipeline:** Python 3.11, pandas, PyArrow, Prophet, XGBoost, scikit-learn (Ridge), scipy, joblib, holidays. No web framework — the pipeline is a sequence of CLI scripts, not a server.

**Frontend:** React 18 + Vite, Tailwind CSS, Recharts-adjacent plain HTML/SVG charts (see `docs/ASSUMPTIONS.md` for why), PapaParse for CSV parsing.

**LLM:** Groq's free, OpenAI-compatible chat completions API, called directly from the browser via `fetch` — no backend proxy, no SDK dependency. The challenge brief explicitly allows any LLM provider ("OpenAI, Gemini, Anthropic or similar"); Groq was chosen for its free tier.

## Forecasting pipeline (offline, no network access)

```
data/*.csv                        (any filename containing google/meta/facebook/bing/microsoft/ms)
     │
     ▼
src/generate_features.py          glob → normalize columns → validate → clean → derive features
     │
     ▼
features.parquet
     │
     ├──────────────────────────────┐
     ▼                               ▼
src/train.py                    src/predict.py          (predict.py is what run.sh calls)
(fits ForecastingTribunal)       (loads pickle, runs
     │                            tribunal.predict())
     ▼                               │
pickle/model.pkl ──────────────────┘
                                      ▼
                              output/predictions.csv
```

`run.sh` only calls `generate_features.py` and `predict.py` — `train.py` is a separate, manually-invoked step (re-run only when the training data changes), and nothing in this path makes a network call.

### The Forecasting Tribunal (`src/models/`)

Three independent models, one instance per campaign, each producing a P10/P50/P90 revenue range for a requested aggregate period (30/60/90 days):

- **Prophet** (`prophet_model.py`) — seasonality expert. Sums daily `predictive_samples` across the period rather than the day-independent `yhat_lower/upper`, so aggregate uncertainty correctly reflects correlated trend/seasonality draws. Skipped for campaigns with under 60 days of history; yearly seasonality is itself skipped/auto under ~2 years of history (see `ASSUMPTIONS.md`).
- **XGBoost** (`xgb_model.py`) — feature learner. Uses `reg:quantileerror` (xgboost≥2.0) to predict P10/P50/P90 directly from one model, rather than the ~100-model bootstrap originally planned (see `ASSUMPTIONS.md` for why that was abandoned).
- **Ridge** (`ridge_model.py`) — sanity anchor. Residual-bootstrap confidence intervals around a scaled linear point forecast.

`tribunal.py`'s `ForecastingTribunal` class wraps all three, blends their P10/P50/P90 with fixed campaign-type ensemble weights, computes a disagreement score from the spread of the three models' P50s, and classifies uncertainty as LOW/MODERATE/HIGH. It's the single object pickled to `pickle/model.pkl`.

### Output format

`predictions.csv` carries the required columns (`channel,campaign_type,campaign_name,period_days,revenue_p10,revenue_p50,revenue_p90,roas_p10,roas_p50,roas_p90,disagreement_pct,uncertainty_level`) plus three appended columns (`prophet_p50,xgb_p50,ridge_p50`) the War Room UI uses for its per-model agreement badges. The required columns' names, order, and casing are untouched — nothing appends before them.

## LLM integration workflow

Two parallel, functionally-identical implementations of the same three narrative roles:

- `src/llm_narrator.py` — standalone Python reference implementation (stdlib `urllib`, no SDK), useful for local testing / the demo walkthrough. **Not imported by any pipeline script.**
- `frontend/src/utils/llmApi.js` — the real UI integration, called from the browser via `fetch`.

Roles:
1. **Disagreement narrator** — 2-3 sentences explaining why the three models disagree on a flagged campaign (Tribunal Verdict Panel, on demand).
2. **Causal summarizer** — three-paragraph past/forecast/risk summary per channel (available via `getCausalSummary`, wired for future use in the Channel Command Center).
3. **Risk identifier** — top-3 ranked operational risks across all channels, returned as JSON.
4. **Allocation comparator** (`compareAllocations`, Battle View only) — one-sentence tradeoff verdict between two budget allocations. Not one of the three report roles above; added because Battle View specifically needs a one-liner, not a report.

All four are called on-demand (button click), never auto-fired on page load or on every RiskDial toggle, to stay within Groq's free-tier rate limits during a live demo.

## War Room UI — four views

- **Channel Command Center** — per-channel cards: editable budget, ROAS health bar, P10/P50/P90 revenue range, confidence badge.
- **Tribunal Verdict Panel** — every channel × campaign row, per-model P50 badges, agreement indicator, on-demand disagreement narrative for flagged rows.
- **Battle View** — two editable budget allocations side by side, winner badge on higher blended ROAS, one-sentence AI comparison.
- **Risk Dial** — persistent P10/P50/P90 toggle in the header (not a separate tab — it's a global control that reshuffles all three views at once, per its own description in the original brief).

`App.jsx` owns the shared state (loaded rows, risk level, period, per-campaign budget overrides) and passes derived aggregates down; the four components stay presentational.
