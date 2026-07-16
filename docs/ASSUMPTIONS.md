# Assumptions
*AIgnition 3.0 — Probabilistic Revenue Forecasting*

## Data assumptions

- Channel is inferred from the CSV filename by keyword match (`google`, `meta`/`facebook`, `bing`/`microsoft`/`ms`), not a hardcoded filename — this also covers the real challenge dataset's filenames (`google_ads_campaign_stats.csv`, `meta_ads_campaign_stats.csv`, `bing_campaign_stats.csv`), which differ from our own sample CSVs (`google_ads_sample.csv`, etc.).
- Column names are normalized against a small alias table (e.g. `Cost`/`Amount Spent` → `spend`, `Campaign`/`Campaign name` → `campaign_name`) before the required-column check, since real ad-platform exports don't share one naming convention with our sample schema.
- If a file has no `campaign_type` column at all, it's inferred from keywords in `campaign_name` (`shopping`, `brand`, `retarget`→retargeting, `search`, `display`, `prospecting`→display, `pmax`/`performance_max`→shopping), falling back to `other`. This only fires when the column is fully absent — an existing column is trusted as-is (lowercased/stripped).
- All monetary values are USD. Revenue is last-click attribution as provided by each platform (per the brief: "existing attribution should be treated as the source of truth" — no custom attribution modeling).
- Missing dates within a campaign's date range are filled with zero spend/revenue/impressions/clicks/conversions, not dropped.
- Rows with negative spend are dropped as data-entry errors (logged to stderr, not silently discarded).
- Each `campaign_name` must map to exactly one `channel` and one `campaign_type` across all rows — `generate_features.py` raises a loud error listing offenders if not, per the brief's "validating campaign consistency" requirement.

## Model assumptions

- **Aggregate-period, not daily, forecasting** (per the brief's explicit constraint): XGBoost and Ridge predict one representative future daily revenue rate from the latest known feature row and scale it by the period length (30/60/90 days) — they do not iterate day-by-day. Prophet forecasts daily internally (its actual strength) and sums those days per period, which is more accurate but doesn't contradict the "aggregate-period" framing since the output is still one number per period.
- **Prophet is skipped below 60 days of campaign history** and relies on XGBoost + Ridge alone (with ensemble weights renormalized across the remaining two).
- **Prophet's yearly seasonality is conditional on history length**, not always on: full `yearly_seasonality=True` requires ≥730 days of history, `'auto'` for ≥365 days, and it's disabled entirely below a year. This was not a planned simplification — it was found by testing: forcing `yearly_seasonality=True` on the 90-day sample data made Prophet extrapolate wildly past the training window (day-30 forecast of +$4k/day swinging to day-60 at -$90k/day for the same campaign), because fitting annual Fourier terms with under a year of evidence has nothing real to anchor on.
- **XGBoost quantile regression, not bootstrap ensembling.** A 100-model-per-campaign bootstrap (each a full 200-tree model) was implemented first and worked, but pickled to ~190MB for just 7 campaigns — that fails GitHub's 100MB file limit and wouldn't scale to a larger real campaign catalog. Switched to `xgboost`'s native `reg:quantileerror` objective (xgboost≥2.0), which predicts P10/P50/P90 directly from one ~1MB model per campaign. `random_state=42` throughout, consistent with the "seed everything" rule, instead of varying 0-99 across bootstrap resamples.
- **Ensemble weights fall back to the Display/Other bucket** for any `campaign_type` value not in the fixed weight table, rather than erroring.
- **Disagreement score uses only the models that actually ran** for a campaign (e.g. just XGBoost + Ridge if Prophet was skipped for a short series) — not a fixed three-model formula.
- **Projected spend for ROAS** is the trailing 28-day average daily spend × period length, unless a caller passes `future_spend_overrides` to `ForecastingTribunal.predict()` (which the UI's budget simulator effectively does at a higher level — see below). This is a "continue current spend rate" baseline scenario, not a spend forecast in its own right.

## Business / product assumptions

- **`predictions.csv` has no explicit spend/budget column.** It's algebraically recoverable as `revenue_p50 / roas_p50` (since ROAS is defined as revenue/spend), which the UI uses as each campaign's "current" budget shown pre-filled in editable inputs.
- **The UI's budget simulator holds ROAS constant and scales revenue linearly with the budget input** (`revenue = budget × ROAS`). It does not model diminishing returns from heavier spend — a full media-mix model is explicitly out of scope per the brief ("building a custom attribution engine or a full-scale MMM is outside the scope of this challenge"). This is the same simplification most agency planning spreadsheets already make.
- **Battle View compares allocations at the P50 (expected) level only** — it doesn't have its own P10/P90 toggle; it defers to being a decision-support tool for the "expected case" plan, with the global RiskDial covering the worst/best-case framing elsewhere.
- **The disagreement narrative's "historical ROAS" input is the forecast's own blended P50 ROAS**, not a separate trailing-30-day actuals figure — `predictions.csv` only carries forecasts, not historical actuals, so there's nothing else to pass. This is disclosed to the LLM only as "historical blended ROAS" context for its explanation, not presented to the user as a distinct historical metric anywhere in the UI.
- **LLM calls are on-demand (button click), never auto-fired** on page load or on every RiskDial/period toggle — both to keep the UI responsive and to stay within Groq's free-tier rate limits during a live demo.
- **`frontend/.env` (with the real API key) is gitignored**; only `frontend/.env.example` is committed. Anyone cloning the repo needs their own free Groq key for the UI's AI features — the offline pipeline (`run.sh`) needs no key at all.

## Known limitations

- The API key is exposed in the browser bundle (`VITE_`-prefixed env vars are inlined at build time) — acceptable for a judged hackathon prototype calling a free-tier API directly from the client, not for a production multi-tenant deployment (that would need a thin backend proxy holding the key server-side).
- Ensemble weights and campaign-type buckets are fixed constants, not learned or cross-validated against held-out data — chosen to match documented domain intuition (Prophet favored for seasonal/brand/shopping, XGBoost for performance/search/retargeting) rather than tuned.
- The clean-clone test (fresh Python 3.11 venv, `pip install -r requirements.txt`, `./run.sh`) has only been run against the bundled sample CSVs, not the full real challenge dataset linked from the project brief (multi-hundred-KB files not fetched during development) — column-alias handling was designed defensively for that dataset's likely shape but not verified against it directly.
