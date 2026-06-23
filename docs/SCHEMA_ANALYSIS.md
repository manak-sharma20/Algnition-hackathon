# Input CSV Schema Analysis
*Ipshita — Day 1 deliverable*

## Overview

Three channel CSV files. All share identical column structure. No nulls in any file.

| File | Rows | Date Range | Campaigns | Campaign Types |
|---|---|---|---|---|
| `google_ads_sample.csv` | 270 | 2024-01-01 → 2024-03-30 | Google_Shopping_Main, Google_Brand_Search, Google_Performance_Max | shopping, brand, search |
| `meta_ads_sample.csv` | 180 | 2024-01-01 → 2024-03-30 | Meta_Retargeting_Core, Meta_Prospecting_Broad | retargeting, display |
| `ms_ads_sample.csv` | 180 | 2024-01-01 → 2024-03-30 | MS_Brand_Search, MS_Shopping_Feed | brand, shopping |

---

## Column Definitions

| Column | Type | Required | Description |
|---|---|---|---|
| `date` | string (YYYY-MM-DD) | Yes | Calendar date of the row |
| `campaign_name` | string | Yes | Unique campaign identifier |
| `campaign_type` | string | Yes | One of: `shopping`, `brand`, `search`, `retargeting`, `display`, `other` |
| `spend` | float | Yes | Ad spend in USD for that day |
| `revenue` | float | Yes | Attributed revenue in USD for that day |
| `impressions` | integer | Yes | Total ad impressions |
| `clicks` | integer | Yes | Total clicks |
| `conversions` | integer | Yes | Total conversions (purchases) |

Channel is inferred from filename prefix (`google_ads_`, `meta_ads_`, `ms_ads_`).

---

## Spend & Revenue by Channel (sample data)

| Channel | Avg Daily Spend | Avg Daily Revenue | Implied ROAS |
|---|---|---|---|
| Google | $1,239 | $5,202 | ~4.2x |
| Meta | $916 | $3,206 | ~3.5x |
| Microsoft | $359 | $1,351 | ~3.8x |

---

## Null Analysis

Zero nulls across all columns in all three files.

---

## Anomalies to Watch

- **Spend = 0 rows**: possible on non-active days; preprocessor must handle divide-by-zero in ROAS/CVR/CPC
- **Negative spend**: not present in sample but validator must reject these rows loudly
- **Date gaps**: sample has no gaps, but real data may; preprocessor fills gaps with spend=0, revenue=0
- **conversions = 0 with clicks > 0**: valid (low CVR days), not an error

---

## Notes for Model Team (Jain)

- Minimum series length for Prophet: 60 rows. All campaigns in sample data have 90 rows — Prophet safe for all.
- XGBoost feature columns derived from this schema: `spend`, plus lag/rolling features computed by `generate_features.py`
- Ridge regression target: `revenue`; features must be scaled (StandardScaler already in pipeline)
