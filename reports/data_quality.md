# Data quality and lineage (SYNTHETIC data)

## Summary for management

1. **Business question.** Can the marketing numbers be trusted for budget decisions, and if not, which ones
   are wrong, where and since when?
2. **Why it matters.** Budgets follow the numbers. A broken tracking tag looks exactly like a channel losing
   performance, and duplicate leads look like growth. If the inputs are wrong, every later analysis is
   precisely wrong.
3. **What this establishes.** 8 of 8 structural checks pass (completeness, funnel order,
   reconciliation between tables). The issue scan found 5 problems: attribution change, cost restated, duplicate leads, tracking outage.
4. **In business terms.** From the week of 21 Jul 2025, the ad platform for B1 social prospecting reports 29% fewer conversions per customer the CRM credits to it. On platform numbers its cost per customer rose from $34 to $49 (+46%). On the CRM's own last-click numbers it moved from $45 to $47 (+4%). Most of the apparent decline is the tracking, not the channel. Separately, ad platforms routinely claim more conversions than the
   company's own CRM credits to them: between 1.00x and 1.65x across channels, highest
   for display and social, where platforms count people who only saw an ad.
5. **Action to consider.** Judge channels on the CRM's numbers, not the platforms'. Repair the
   B1 social prospecting conversion tag.
   De-duplicate B2 demo requests at the point of entry. Close each week's media costs only after
   restatements have arrived.
6. **Assumptions and limits.** The checks only find problems they have a rule for. A problem inside the CRM
   itself would not be found here. CRM last-click credit is more honest than platform credit but still not
   causal: it includes customers who would have bought anyway. That gap is measured in phases 3 and 4.

## Lineage (row counts at each layer)

Raw tables are the generated Parquet files. Clean tables remove duplicates and add flags; metric tables are
what forecasts, the optimiser, the dashboard and the AI commentary read (D-007).

| table                       | layer   |   rows |
|:----------------------------|:--------|-------:|
| synthetic_weekly_media      | raw     |   1872 |
| synthetic_weekly_crm        | raw     |   2340 |
| synthetic_b2_leads          | raw     |  16940 |
| synthetic_customers         | raw     | 145791 |
| synthetic_customer_activity | raw     | 457154 |
| media_clean                 | clean   |   1872 |
| b2_leads_clean              | clean   |  16940 |
| crm_clean                   | clean   |   2340 |
| line_week                   | metric  |   1872 |
| business_week               | metric  |    468 |
| customer_lifetimes          | metric  | 145791 |
| repeat_orders_by_month      | metric  |    540 |

## Structural checks

| check                                               | passed   |   failing_rows | detail                                              |
|:----------------------------------------------------|:---------|---------------:|:----------------------------------------------------|
| every line has every week                           | True     |              0 | 12 lines x 156 weeks                                |
| no negative spend or counts                         | True     |              0 | media and CRM                                       |
| funnel order: customers <= qualified <= leads       | True     |              0 | CRM, by source and week (B2 on de-duplicated leads) |
| clicks <= impressions                               | True     |              0 | platform reports                                    |
| customer table reconciles to CRM counts             | True     |              0 | new customers per business                          |
| every customer is active in their acquisition month | True     |              0 | activity month 0                                    |
| no activity after the end of the data               | True     |              0 | right-censoring respected                           |
| B2 won leads reconcile to CRM customers             | True     |              0 | lead-level vs weekly                                |

## Issues found

| issue              | business   | channel              | first_week   | last_week   |   n_weeks | detail                                        |
|:-------------------|:-----------|:---------------------|:-------------|:------------|----------:|:----------------------------------------------|
| tracking_outage    | B1         | search_generic       | 2025-12-22   | 2025-12-22  |         1 | platform reports 0 conversions, CRM does not  |
| tracking_outage    | B3         | display_retargeting  | 2025-03-03   | 2025-03-10  |         2 | platform reports 0 conversions, CRM does not  |
| cost_restated      | B2         | programmatic_display | 2026-04-27   | 2026-04-27  |         1 | spend changed after first report              |
| duplicate_leads    | B2         | all                  | 2023-11-06   | 2026-10-19  |       147 | 491 duplicates, 2.9% of recorded leads        |
| attribution_change | B1         | social_prospecting   | 2025-07-21   | 2026-10-19  |        66 | platform/CRM ratio 1.35 -> 0.96 (p = 4.4e-30) |

Flagged weeks stay in the data. `line_week.any_dq_flag` lets each later step decide whether to exclude them.

## Platform-reported vs CRM last-click conversions

Platform-to-CRM ratio outside the flagged weeks. A ratio above 1 means the platform claims customers the CRM
credits to another source, or to none.

| business   | channel              |   platform_to_crm_ratio |   last_click_cac |   platform_cac |
|:-----------|:---------------------|------------------------:|-----------------:|---------------:|
| B1         | affiliates           |                    1.09 |            58.71 |          53.66 |
| B1         | search_brand         |                    1.00 |            42.52 |          42.52 |
| B1         | search_generic       |                    1.05 |            49.10 |          47.02 |
| B1         | social_prospecting   |                    1.35 |            45.93 |          38.41 |
| B2         | linkedin             |                    1.31 |         1,931.87 |       1,477.31 |
| B2         | programmatic_display |                    1.65 |         3,830.64 |       2,315.53 |
| B2         | review_sites         |                    1.15 |           887.43 |         772.44 |
| B2         | search_generic       |                    1.04 |         2,154.01 |       2,064.26 |
| B3         | affiliates           |                    1.11 |            31.69 |          28.65 |
| B3         | display_retargeting  |                    1.60 |            45.05 |          28.55 |
| B3         | shopping             |                    1.05 |            34.11 |          32.54 |
| B3         | social_prospecting   |                    1.35 |            38.32 |          28.42 |

## Attribution change test (all lines)

Change point in log(platform / CRM) on 4-week sums, refined to the week. Bonferroni-adjusted significance
across 12 lines, plus a minimum size of change. Only lines meeting both are flagged.

| business   | channel              | shift_week_start    |   ratio_before |   ratio_after |   change |   p_value | detected   |
|:-----------|:---------------------|:--------------------|---------------:|--------------:|---------:|----------:|:-----------|
| B1         | affiliates           | 2024-05-20 00:00:00 |          1.080 |         1.098 |    0.017 |     0.216 | False      |
| B1         | search_brand         | 2023-11-27 00:00:00 |          1.000 |         1.000 |    0.000 |     1.000 | False      |
| B1         | search_generic       | 2026-06-15 00:00:00 |          1.050 |         1.061 |    0.010 |     0.095 | False      |
| B1         | social_prospecting   | 2025-07-21 00:00:00 |          1.348 |         0.959 |   -0.289 |     0.000 | True       |
| B2         | linkedin             | 2026-03-23 00:00:00 |          1.251 |         1.500 |    0.199 |     0.015 | False      |
| B2         | programmatic_display | 2026-08-03 00:00:00 |          1.613 |         2.167 |    0.343 |     0.168 | False      |
| B2         | review_sites         | 2026-08-03 00:00:00 |          1.129 |         1.381 |    0.224 |     0.220 | False      |
| B2         | search_generic       | 2025-12-01 00:00:00 |          1.062 |         1.000 |   -0.059 |     0.009 | False      |
| B3         | affiliates           | 2025-08-25 00:00:00 |          1.115 |         1.091 |   -0.022 |     0.028 | False      |
| B3         | display_retargeting  | 2025-09-15 00:00:00 |          1.587 |         1.611 |    0.015 |     0.067 | False      |
| B3         | shopping             | 2026-09-14 00:00:00 |          1.047 |         1.075 |    0.026 |     0.385 | False      |
| B3         | social_prospecting   | 2024-07-15 00:00:00 |          1.330 |         1.354 |    0.018 |     0.093 | False      |

## Validation against the SYNTHETIC ground truth

The checks above use observable data only. Scoring them against the issues deliberately injected into the
simulation: **5 of 5 injected issues detected**, 0
flags raised where nothing was injected.

| issue              | business   | channel              | injected_from   | injected_to   | detected   | detected_from   | detected_to   |   start_error_weeks |
|:-------------------|:-----------|:---------------------|:----------------|:--------------|:-----------|:----------------|:--------------|--------------------:|
| tracking_outage    | B3         | display_retargeting  | 2025-03-03      | 2025-03-10    | True       | 2025-03-03      | 2025-03-10    |                   0 |
| tracking_outage    | B1         | search_generic       | 2025-12-22      | 2025-12-22    | True       | 2025-12-22      | 2025-12-22    |                   0 |
| attribution_change | B1         | social_prospecting   | 2025-07-21      | 2026-10-19    | True       | 2025-07-21      | 2026-10-19    |                   0 |
| duplicate_leads    | B2         | all                  | 2023-10-30      | 2026-10-19    | True       | 2023-11-06      | 2026-10-19    |                   1 |
| cost_restated      | B2         | programmatic_display | 2026-04-27      | 2026-04-27    | True       | 2026-04-27      | 2026-04-27    |                   0 |
