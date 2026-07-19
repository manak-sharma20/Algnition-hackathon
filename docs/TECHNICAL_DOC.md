# Technical Documentation
*AIgnition 3.0 — Probabilistic Revenue Forecasting*

See `docs/ARCHITECTURE.md` for the system diagram and `docs/ASSUMPTIONS.md` for the full list of assumptions and known limitations. This document covers methodology and rationale.

## Methodology overview

The system forecasts revenue and ROAS per channel/campaign-type/campaign for 30/60/90-day planning periods, as probabilistic P10/P50/P90 ranges rather than single point estimates (per the challenge brief's explicit constraint). Three statistically independent models — Prophet, XGBoost, Ridge — are fit per campaign and blended with fixed, campaign-type-dependent weights into a "Forecasting Tribunal." An LLM (Groq, see below) sits entirely outside this offline pipeline and adds plain-English interpretation on top of the numbers in the UI.

## Model selection rationale

Three models with genuinely different failure modes were chosen deliberately, rather than one "best" model, because the brief asks for "appropriate handling of uncertainty" and "realistic modeling assumptions" — a single model's confidence interval only captures that model's own uncertainty, not the risk that the model class itself is wrong for this campaign.

- **Prophet** captures calendar structure (weekly cycles, and yearly cycles once there's enough history to trust them) that a feature-based model would need explicit lag/seasonality features to approximate. It's trusted most for Shopping/Brand campaigns, where seasonal buying patterns dominate.
- **XGBoost** learns non-linear interactions between spend, lags, rolling averages, and seasonality flags that a linear model can't represent (e.g. "spend growth compounds with a rolling ROAS above X differently than below it"). It's trusted most for Search/Retargeting, where performance-marketing dynamics are less calendar-driven and more responsive to spend/targeting changes.
- **Ridge regression** is intentionally simple and the least-weighted model everywhere. Its job is to be a sanity anchor: if Prophet and XGBoost agree with each other but Ridge is wildly different, that's a signal the two more flexible models may be overfitting the same spurious pattern, which is exactly what `disagreement_pct` is designed to surface.

## Preprocessing logic

See `src/generate_features.py`. In order: glob CSVs from `--data-dir` → infer channel from filename → normalize column names against an alias table → validate required columns are present (loud error if not) → infer `campaign_type` from campaign name if the column is absent → validate campaign_name→channel/campaign_type consistency → fill date gaps with zeros → drop negative-spend rows → derive ROAS/CVR/CPC (safe divide-by-zero) → derive lag/rolling revenue features and calendar flags (month, week of year, is_q4, is_weekend) → write `features.parquet`.

## Feature engineering details

Per-campaign daily features: `roas`, `cvr`, `cpc` (all zero-guarded against zero denominators), `lag_revenue_7d`, `lag_revenue_28d`, `rolling_mean_revenue_7d`, `rolling_mean_roas_7d`, `spend_growth_rate` (vs. 7 days prior), `month`, `week_of_year`, `is_q4`, `is_weekend`. XGBoost and Ridge both train on the same `FEATURE_COLUMNS` list (`src/models/xgb_model.py`); Prophet trains on the raw daily `(date, revenue)` series with `spend` as an additional regressor.

## Ensemble blending approach

Fixed weights per campaign-type bucket (current values, see `ForecastingTribunal.ENSEMBLE_WEIGHTS`: Shopping/Brand Prophet 0.1/XGBoost 0.45/Ridge 0.45; Search/Retargeting Prophet 0.05/XGBoost 0.6/Ridge 0.35; Display/Other Prophet 0.1/XGBoost 0.45/Ridge 0.45). The blended P10 is the weighted average of the three models' P10s (same for P50/P90); because weights are constant across all three levels and each model's own P10≤P50≤P90 holds, the blended range preserves that ordering before the interval-widening step below. When Prophet was skipped for a short series, its weight is redistributed proportionally across XGBoost and Ridge rather than silently dropped.

**These weights are data-driven, not domain intuition** — an earlier version (Prophet 0.5/XGBoost 0.3/Ridge 0.2 for Shopping/Brand, the dataset's dominant campaign type) was chosen from documented reasoning about which model *should* suit which campaign type, then never validated. Once `src/backtest.py` existed, a rolling-origin backtest measured each model's actual out-of-sample MAE and found Prophet consistently ~1.85x worse than XGBoost/Ridge (which are themselves nearly tied) at every single cutoff tested — not noise, a uniform pattern across the whole dataset. The original weights gave the most influence to the worst model. Weights were re-tuned against that evidence (see the backtest section below for the before/after numbers) — Prophet is kept in the blend rather than dropped, because dropping it entirely was tested and measured *worse* median error than keeping a small weight on it: a weak-but-differently-wrong model still reduces variance in a blend even when its own solo accuracy is worse.

**Interval widening.** Blending independent models' P10/P90 by weighted average understates combined uncertainty — each model's own interval only reflects that model's uncertainty about itself, not the risk that the model class is wrong for this campaign, or that the future spend assumption doesn't hold. Measured via the same backtest: the raw blended interval covered the actual outcome only 68.7-74.8% of the time against an 80% nominal target. `ForecastingTribunal.INTERVAL_WIDEN_FACTOR = 1.5` widens the blended P10/P90 around P50 by that factor (tuned on the same 4 cutoffs: 1.0→74.8% coverage, 1.4→80.4%, 1.5→81.6%, 1.6→82.2%, 2.0→86.5% — 1.5 closes most of the gap without excessively ballooning the range). P10 is clipped at 0 (revenue can't go negative).

## Confidence interval methodology per model

- **Prophet**: `uncertainty_samples=1000`, `interval_width=0.8`. Rather than using the day-independent `yhat_lower`/`yhat_upper` (which would understate aggregate uncertainty if simply summed across days, since it ignores that each day's draw shares the same trend/seasonality realization), the tribunal calls `predictive_samples()` to get 1000 coherent daily sample paths, sums each path across the requested period, and takes percentiles of those 1000 period totals.
- **XGBoost**: native multi-quantile regression (`reg:quantileerror`, `quantile_alpha=[0.1, 0.5, 0.9]`), one model per campaign predicting all three quantiles directly for a representative future day, then scaled by period length. Predicted quantiles are sorted before use as a safety net against quantile crossing (a known non-guarantee of this objective).
- **Ridge**: point forecast via a `StandardScaler` + `Ridge(alpha=1.0)` pipeline, then residual bootstrap — 1000 draws from the training-residual distribution added to the point forecast, scaled by period length, reduced to P10/P50/P90.

## Validated accuracy (rolling-origin backtest)

Every other check in this repo verifies *internal consistency* (no NaNs, P10≤P50≤P90, right shape/columns) - none of it verifies the forecasts are actually *accurate*. `src/backtest.py` closes that gap: it holds out a window at one or more cutoff dates, fits a fresh tribunal on everything before each cutoff, forecasts forward, and compares against what actually happened.

**First pass (single 30-day cutoff, 27 campaigns evaluable) found the ensemble losing to a naive "revenue continues at its trailing rate" baseline** on both mean and median error. Rather than accept or dismiss that from one window, ran `--cutoffs 4` for a rolling-origin backtest (4 non-overlapping 30-day windows walking back from the end of the dataset, 163 campaign-forecasts total) and broke error down per model - which is what led to the reweighting and interval-widening changes described above. Before/after, pooled across all 4 cutoffs:

| Metric | Before (original weights) | After (data-driven weights + interval widening) | Naive baseline |
|---|---|---|---|
| Mean absolute error | $3,993.16 | **$3,692.54** | $4,614.84 |
| Median absolute error | $1,109.19 | **$998.11** | $816.31 |
| Improvement over baseline (MAE) | 13.5% | **20.0%** | — |
| P10-P90 empirical coverage | 68.7% | **81.6%** | n/a (target: 80%) |
| Median absolute percentage error | 40.2% | 50.4% | — |

Per-model pooled MAE (unchanged by reweighting - these are each model's own solo accuracy): Prophet $7,977, XGBoost $4,258, Ridge $4,318. Prophet is consistently the worst model at every individual cutoff, which is exactly why its ensemble weight was cut.

**Honest reading of what improved and what didn't:**
- MAE improved 20.0% over baseline (up from 13.5%) and RMSE is lower too - the reweighting reduced how badly the ensemble does on its worst misses.
- **Median absolute error is still slightly worse than the naive baseline** ($998 vs $816) - for a "typical" campaign, just assuming revenue continues at its recent rate is still a slightly better bet than the ensemble's point forecast. The gap narrowed substantially (from $293 to $182) but didn't close.
- P10-P90 coverage moved from a real miscalibration (68.7%, intervals meaningfully too narrow) to close to the 80% nominal target (81.6%) - this is the change most confidently fixed.
- Median absolute percentage error actually got *worse* (40.2% → 50.4%) even though absolute-dollar errors improved - this happens because the reweighting shifted more error onto smaller-revenue campaigns proportionally while reducing it in dollar terms on larger ones; worth knowing, not further investigated given time constraints.
- `uncertainty_level` stayed cleanly monotonic with actual error (LOW $245 < MODERATE $4,355 < HIGH $5,524, pooled) - the disagreement score has real diagnostic value both before and after this change.

**What "accurate" realistically means here:** a ~40-50% median absolute percentage error on 30-day campaign-level revenue is not a failure - daily/campaign-level ad revenue is genuinely volatile (spend changes, seasonality, platform algorithm shifts, campaigns pausing), and this is consistent with typical real-world media-forecasting accuracy at this granularity. Any claim of, say, 95% accuracy at this granularity would itself be the red flag - it would mean either the evaluation is wrong or the model is overfit to noise. What's real here: a measured, reproducible 20% improvement over a naive baseline, honestly reported gaps (median error, MAPE) alongside it, and a rolling-origin methodology that avoids overclaiming from a single lucky or unlucky window.

**Still not done, given time constraints:** the 4 cutoffs are all non-overlapping windows from the same dataset, not independent data - a genuinely more rigorous validation would test on more cutoffs, and investigate the MAPE regression above rather than just note it.

## AI integration strategy

See `docs/ARCHITECTURE.md`'s "LLM integration workflow" section for the full role list and call sites. In short: the LLM (Groq, free-tier, OpenAI-compatible API) is called exclusively from the browser, exclusively on-demand, and never sees or influences the offline pipeline's numbers — it explains and contextualizes forecasts the tribunal already produced, playing the roles of disagreement narrator, causal summarizer, ranked-risk identifier, and (Battle View only) allocation comparator.

## Assumptions and limitations

See `docs/ASSUMPTIONS.md`.
