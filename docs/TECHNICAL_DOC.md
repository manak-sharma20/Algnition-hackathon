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

Fixed weights per campaign-type bucket (Shopping/Brand: Prophet 0.5/XGBoost 0.3/Ridge 0.2; Search/Retargeting: 0.2/0.6/0.2; Display/Other: 0.3/0.4/0.3 — see `ForecastingTribunal.ENSEMBLE_WEIGHTS`). The blended P10 is the weighted average of the three models' P10s (same for P50/P90); because weights are constant across all three levels and each model's own P10≤P50≤P90 holds, the blended range preserves that ordering. When Prophet was skipped for a short series, its weight is redistributed proportionally across XGBoost and Ridge rather than silently dropped.

## Confidence interval methodology per model

- **Prophet**: `uncertainty_samples=1000`, `interval_width=0.8`. Rather than using the day-independent `yhat_lower`/`yhat_upper` (which would understate aggregate uncertainty if simply summed across days, since it ignores that each day's draw shares the same trend/seasonality realization), the tribunal calls `predictive_samples()` to get 1000 coherent daily sample paths, sums each path across the requested period, and takes percentiles of those 1000 period totals.
- **XGBoost**: native multi-quantile regression (`reg:quantileerror`, `quantile_alpha=[0.1, 0.5, 0.9]`), one model per campaign predicting all three quantiles directly for a representative future day, then scaled by period length. Predicted quantiles are sorted before use as a safety net against quantile crossing (a known non-guarantee of this objective).
- **Ridge**: point forecast via a `StandardScaler` + `Ridge(alpha=1.0)` pipeline, then residual bootstrap — 1000 draws from the training-residual distribution added to the point forecast, scaled by period length, reduced to P10/P50/P90.

## AI integration strategy

See `docs/ARCHITECTURE.md`'s "LLM integration workflow" section for the full role list and call sites. In short: the LLM (Groq, free-tier, OpenAI-compatible API) is called exclusively from the browser, exclusively on-demand, and never sees or influences the offline pipeline's numbers — it explains and contextualizes forecasts the tribunal already produced, playing the roles of disagreement narrator, causal summarizer, ranked-risk identifier, and (Battle View only) allocation comparator.

## Assumptions and limitations

See `docs/ASSUMPTIONS.md`.
