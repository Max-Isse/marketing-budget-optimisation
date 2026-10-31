# Simulated world at last year's spend (SYNTHETIC ground truth)

> **This is a design check, not a finding.** It describes the simulated company that later phases analyse.
> The models never see these numbers. They have to recover them from the generated data, and phase 4 scores
> them against this table.

## Summary for management

1. **Business question.** Does the simulated company look like a real multi-business advertiser? In
   particular, are its dashboard numbers misleading in the ways real ones are?
2. **Why it matters.** If the simulation were too easy, every method would look good and the project would
   prove nothing. The test only works if some channels look better on the dashboard than they really are.
3. **What this establishes.** Last year's planned spend of $1,999,400 generates about
   $981,181 a year of contribution after paying for the advertising. That total hides large
   differences between channels: 4 channels look strong on platform-reported return but earn
   less than 60 cents per extra dollar, and 5 channels earn more than $1.20 per extra dollar
   and are under-funded.
4. **In business terms.** Moving money by dashboard ROAS would move it the wrong way. The analysis has to
   measure what each extra dollar actually buys.
5. **Action to consider.** None yet. This table sets the benchmark the analysis must hit.
6. **Assumptions and limits.** All values are simulation inputs chosen to be plausible (see
   `docs/data_design.md`). The figures assume average demand: no seasonality, trend or noise.

## How to read the returns

All returns are 24-month discounted contribution per advertising dollar. Above 1.0 the spend pays for itself;
below 1.0 it loses money.

- **Attributed return** is what an ad platform or last-click dashboard reports. It includes customers who
  would have bought anyway.
- **Incremental return** counts only the customers the advertising caused, averaged over all spend on the line.
- **Marginal return** is what the *next* dollar earns. This is the number a budget decision needs. Because
  returns diminish as spend grows, it is usually lower than the average.

## Businesses

| business   | name          | model        |   annual_spend |   customer_value_24m |   incremental_cac |   payback_months |   qualified_leads_per_week |   annual_net_contribution |
|:-----------|:--------------|:-------------|---------------:|---------------------:|------------------:|-----------------:|---------------------------:|--------------------------:|
| B1         | Hearth Box    | subscription |     878,800.00 |                87.50 |             51.93 |             7.00 |                     775.73 |                588,679.90 |
| B2         | Ledgerline    | subscription |     520,000.00 |             5,162.12 |          3,211.67 |            14.00 |                      30.57 |                306,777.02 |
| B3         | Atlas Outdoor | ecommerce    |     600,600.00 |                58.95 |             51.24 |            13.00 |                     636.28 |                 85,723.85 |

## Business-channel lines (weekly spend, average demand)

| business   | channel              |   weekly_spend |   cost_per_lead |   incremental_cac |   marginal_cac |   attributed_return |   incremental_return |   marginal_return |
|:-----------|:---------------------|---------------:|----------------:|------------------:|---------------:|--------------------:|---------------------:|------------------:|
| B1         | search_brand         |       3,000.00 |           23.08 |             69.93 |         244.76 |                2.11 |                 1.25 |              0.36 |
| B1         | search_generic       |       6,000.00 |           13.50 |             50.02 |          71.45 |                1.81 |                 1.75 |              1.22 |
| B1         | social_prospecting   |       6,500.00 |            9.22 |             43.89 |          51.14 |                2.02 |                 1.99 |              1.71 |
| B1         | affiliates           |       1,400.00 |           29.00 |             96.67 |         186.89 |                1.21 |                 0.72 |              0.37 |
| B2         | search_generic       |       3,500.00 |          197.92 |          3,298.61 |       5,222.80 |                1.87 |                 1.56 |              0.99 |
| B2         | linkedin             |       3,000.00 |          221.23 |          2,633.67 |       3,336.99 |                2.22 |                 1.96 |              1.55 |
| B2         | review_sites         |       1,500.00 |          181.82 |          2,597.40 |       4,155.84 |                4.57 |                 1.99 |              1.24 |
| B2         | programmatic_display |       2,000.00 |          107.14 |          5,952.38 |      10,714.29 |                0.99 |                 0.78 |              0.43 |
| B3         | shopping             |       4,500.00 |           13.26 |             37.87 |          59.18 |                1.69 |                 1.56 |              1.00 |
| B3         | social_prospecting   |       3,000.00 |            9.11 |             43.37 |          40.34 |                1.42 |                 1.36 |              1.46 |
| B3         | display_retargeting  |       3,300.00 |           50.53 |            120.30 |         384.96 |                1.28 |                 0.49 |              0.15 |
| B3         | affiliates           |         750.00 |           28.95 |             75.19 |         137.84 |                1.47 |                 0.67 |              0.36 |

### Dashboard traps (attributed return above 1.2, marginal return below 0.6)

| business   | channel             |   attributed_return |   marginal_return |
|:-----------|:--------------------|--------------------:|------------------:|
| B1         | search_brand        |                2.11 |              0.36 |
| B1         | affiliates          |                1.21 |              0.37 |
| B3         | display_retargeting |                1.28 |              0.15 |
| B3         | affiliates          |                1.47 |              0.36 |

### Under-funded lines (marginal return above 1.2)

| business   | channel            |   incremental_return |   marginal_return |
|:-----------|:-------------------|---------------------:|------------------:|
| B1         | search_generic     |                 1.75 |              1.22 |
| B1         | social_prospecting |                 1.99 |              1.71 |
| B2         | linkedin           |                 1.96 |              1.55 |
| B2         | review_sites       |                 1.99 |              1.24 |
| B3         | social_prospecting |                 1.36 |              1.46 |

### Cheapest leads in each business that lose money at the margin

| business   | channel              |   cost_per_lead |   lead_to_customer |   marginal_return |
|:-----------|:---------------------|----------------:|-------------------:|------------------:|
| B2         | programmatic_display |          107.14 |               0.02 |              0.43 |

## Budget policy feasibility at last year's spend

All budget policies can be met at the same time.

| business   |     min |       max |
|:-----------|--------:|----------:|
| B1         | 600,000 | 1,000,000 |
| B2         | 350,000 |   800,000 |
| B3         | 400,000 |   900,000 |
