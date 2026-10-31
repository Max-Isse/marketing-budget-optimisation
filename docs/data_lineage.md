# Data lineage

Row counts at each step are produced by `uv run mbo quality` and stored in `reports/tables/lineage.csv`
(and shown in `reports/data_quality.md`). Everything is rebuilt from the seed in `configs/config.yaml`.

```
configs/ground_truth_SYNTHETIC.yaml
        │  mbo generate (src/marketing_budget/synthetic/generate.py, seeded)
        ▼
data/raw/synthetic_*.parquet                      observable: what a real company would have
data/raw/truth/synthetic_truth_*.parquet          truth: read only by src/marketing_budget/validation/
        │  mbo build (src/marketing_budget/data/build.py)
        ▼
data/processed/marketing_SYNTHETIC.duckdb
  01_load_raw.sql        synthetic_* tables, unchanged
  02_clean.sql           media_clean (cost_restated)          b2_leads_clean (is_duplicate)
                         crm_clean (B2 lead counts rebuilt on unique leads)
  03_line_week_base.sql  line_week_base: platform report joined to CRM last-click counts (tracking_outage)
  [python]               dq_attribution_shift: change point in platform/CRM ratio per line
  04_line_week.sql       line_week: validated metrics + all flags     business_week: totals incl. organic
  05_cohorts.sql         customer_lifetimes (observable months, censoring)   repeat_orders_by_month
  06_pnl.sql             business_week_pnl: revenue and contribution of all active customers, acquisition
                         costs, spend, contribution profit
  07_experiments.sql     synthetic_exp_* (loaded by `mbo experiments` after the designs are fixed),
                         exp_geo_region_period
        │  mbo quality, mbo retention, later phases
        ▼
reports/*.md, reports/tables/*.csv
```

## Keys and grain

| Table | Grain | Key |
|---|---|---|
| `media_clean`, `line_week` | business × channel × week | (week_start, business, channel) |
| `crm_clean` | business × last-click source × week (source includes `organic`) | (week_start, business, source) |
| `business_week` | business × week | (week_start, business) |
| `b2_leads_clean` | one B2 demo request | lead_id |
| `customer_lifetimes` | one new customer | customer_id |
| `repeat_orders_by_month` | business × source × month since acquisition | (business, source, month_index) |
| `business_week_pnl` | business × week (P&L, inherited customers included) | (week_start, business) |

Weeks start on Monday. Month *k* of a customer starts *k* × 30.44 days after acquisition. A month is
observable only if it starts before the end of the data (`synthetic_data_meta.data_end_date`).

## Reconciliations checked on every build (`reports/data_quality.md`)

- 12 lines × 156 weeks, none missing.
- New customers in `synthetic_customers` = the sum of CRM customers, per business.
- Every customer is active in month 0, and no activity falls after the end of the data.
- B2 won leads in the lead table = CRM customers, per source and week.
- Funnel order (customers ≤ qualified ≤ leads) and clicks ≤ impressions.
