# Technical report (SYNTHETIC data)

> **The data are simulated (SYNTHETIC).** The company, its three businesses and every figure below come from
> a simulation built for this project, because only a simulation reveals each channel's true effect and so
> lets the method be checked. The figures show what the method recommends and how; they are not facts
> about a real company.

## Summary for management

1. **Business question.** How should a fixed $2.0M paid-acquisition budget be split across three
   businesses and 12 channels to maximise long-term contribution, without excessive risk?
2. **Why it matters.** Steering by platform-reported returns would cost $794k a year by the model;
   a better split would add $437k.
3. **What this establishes.** A pipeline that cleans and checks the data, values customers, forecasts, runs and
   reads experiments, fits calibrated response curves and optimises the split under policy constraints and
   uncertainty, then reports each result with its evidence type. Each step is checked against a simulated truth
   (section 9).
4. **In business terms.** Tested moves are reliable; untested ones are directionally useful but optimistic, so
   the plan limits them and holds a reserve.
5. **Action to consider.** See the [executive memo](executive_memo.md) and [recommendations](recommendations.md).
6. **Assumptions and limits.** Section 10.

This report gathers the method and results in one place. Each phase report has the full detail.

## 1. Data

A simulation (`src/marketing_budget/synthetic/`, seed 20261031) produces weekly media, CRM, lead and customer
records for three businesses with 12 channel lines over 156 weeks, plus five years of inherited customers.
It injects realistic problems: platform over-claiming, an attribution change, tracking outages, duplicate leads
and cost restatements. Design: [docs/data_design.md](../docs/data_design.md).

**Lineage** (row counts at each layer; [docs/data_lineage.md](../docs/data_lineage.md)):

| table                       | layer   |   rows |
|:----------------------------|:--------|-------:|
| synthetic_weekly_media      | raw     |   1872 |
| synthetic_weekly_crm        | raw     |   2340 |
| synthetic_b2_leads          | raw     |  16903 |
| synthetic_customers         | raw     | 181748 |
| synthetic_customer_activity | raw     | 596240 |
| media_clean                 | clean   |   1872 |
| b2_leads_clean              | clean   |  16903 |
| crm_clean                   | clean   |   2340 |
| line_week                   | metric  |   1872 |
| business_week               | metric  |    468 |
| customer_lifetimes          | metric  | 146409 |
| repeat_orders_by_month      | metric  |    539 |
| business_week_pnl           | metric  |    468 |

**Quality.** 8 of 8 structural checks pass; 5 issues found and handled
(outage weeks excluded from platform metrics, duplicates removed, restated costs used, the attribution change
dated). [data_quality.md](data_quality.md)

| issue              | business   | channel              | first_week   | last_week   |   n_weeks | detail                                        |
|:-------------------|:-----------|:---------------------|:-------------|:------------|----------:|:----------------------------------------------|
| tracking_outage    | B1         | search_generic       | 2025-12-22   | 2025-12-22  |         1 | platform reports 0 conversions, CRM does not  |
| tracking_outage    | B3         | display_retargeting  | 2025-03-03   | 2025-03-10  |         2 | platform reports 0 conversions, CRM does not  |
| cost_restated      | B2         | programmatic_display | 2026-04-27   | 2026-04-27  |         1 | spend changed after first report              |
| duplicate_leads    | B2         | all                  | 2023-11-06   | 2026-10-19  |       149 | 491 duplicates, 2.9% of recorded leads        |
| attribution_change | B1         | social_prospecting   | 2025-07-21   | 2026-10-19  |        66 | platform/CRM ratio 1.35 -> 0.96 (p = 4.4e-30) |

## 2. Customer value

24-month discounted contribution per new customer (10% a year). Subscriptions (B1, B2):
survival with a separate first-month hazard, fitted with censoring. E-commerce (B3): a Poisson model of repeat
orders decaying by month. Intervals are from 2000 parameter draws. Fully observed
early cohorts check the model. [customer_value.md](customer_value.md)

| business   | 24-month value   | 95% interval   |
|:-----------|:-----------------|:---------------|
| B1         | $87              | $86-$88        |
| B2         | $5,117           | $5,002-$5,231  |
| B3         | $59              | $59-$59        |

## 3. Forecasting

Models: naive, seasonal_naive, ets, regression, gbm. The regression has trend, 3 Fourier seasonal pairs and log planned
spend; gradient boosting runs on detrended data. Validation is rolling-origin: train on at least
104 weeks, forecast 13 weeks, move the origin 4 weeks, repeat.
Metrics: MAE, RMSE, WAPE and bias. The simplest model within 5% of the best WAPE is chosen.
The regression is chosen for 21 of 24 business-metric forecasts. 80% intervals come from
back-test errors; leave-one-origin-out coverage of the chosen models is 72%-78%.
[forecasting.md](forecasting.md)

| business   | target              | selected   |   selected_wape |   selected_bias |   seasonal_naive_wape |
|:-----------|:--------------------|:-----------|----------------:|----------------:|----------------------:|
| B1         | contribution_profit | regression |           0.061 |           0.020 |                 0.111 |
| B1         | customers           | regression |           0.127 |          -0.034 |                 0.167 |
| B1         | revenue             | regression |           0.031 |           0.001 |                 0.057 |
| B2         | contribution_profit | regression |           0.046 |           0.008 |                 0.115 |
| B2         | customers           | regression |           0.373 |          -0.171 |                 0.441 |
| B2         | revenue             | regression |           0.030 |          -0.007 |                 0.106 |
| B3         | contribution_profit | regression |           0.095 |           0.029 |                 0.110 |
| B3         | customers           | regression |           0.120 |           0.024 |                 0.163 |
| B3         | revenue             | regression |           0.068 |           0.015 |                 0.091 |

Next quarter (pessimistic / baseline / optimistic):

| business   | target              |   baseline |   optimistic |   pessimistic |
|:-----------|:--------------------|-----------:|-------------:|--------------:|
| B1         | contribution_profit |    307,488 |      314,804 |       303,391 |
| B1         | customers           |      5,736 |        6,660 |         5,503 |
| B2         | contribution_profit |  1,374,660 |    1,405,680 |     1,352,280 |
| B2         | customers           |        126 |          145 |           101 |
| B3         | contribution_profit |    354,371 |      363,047 |       338,110 |
| B3         | customers           |      8,281 |        8,483 |         7,730 |

**Not causal.** The regression's spend coefficient falls to 46%-63% of its
spend-only size once trend and seasonality are controlled, because budgets followed demand. Forecasts are
used for planning, never to set budgets.

## 4. Experiments

7 randomised tests, each sized before launch. User-level tests use two-proportion tests (delta method
for click-through rates, Poisson for count rates). Region tests change budgets in randomly chosen regions and are
analysed by ANCOVA on the pre-period with HC2 errors and t critical values, checked by randomisation inference;
holdout share and duration come from an A/A rehearsal on the pre-period. 1 of 4 region tests
reach the targeted detectable effect: the businesses are too small for more. Decisions compare the interval with
the business's break-even threshold. A peeking simulation shows why tests are not stopped early; Holm correction
is applied across metrics. [experiments.md](experiments.md)

| experiment         | metric                                 |   relative_effect |   ci_low |   ci_high |   p_value | decision                                                                 |
|:-------------------|:---------------------------------------|------------------:|---------:|----------:|----------:|:-------------------------------------------------------------------------|
| landing_page       | conversion rate                        |             0.066 |    0.029 |     0.105 |     0.000 | adopt: the effect is real and large enough to matter                     |
| ad_creative        | click-through rate                     |             0.023 |   -0.011 |     0.057 |     0.188 | inconclusive: the test cannot tell; extend it or decide on other grounds |
| audience_targeting | leads per $                            |             0.125 |   -0.120 |     0.439 |     0.381 | inconclusive: the test cannot tell; extend it or decide on other grounds |
| audience_targeting | qualified leads per $                  |            -0.346 |   -0.576 |     0.007 |     0.066 | no worthwhile effect: even the best case is below the threshold          |
| audience_targeting | customers per $                        |            -0.714 |   -0.941 |     0.375 |     0.180 | inconclusive: the test cannot tell; extend it or decide on other grounds |
| bidding_tcpa       | total business customers (region test) |             0.028 |   -0.062 |     0.117 |     0.283 | nan                                                                      |
| retargeting_off    | total business customers (region test) |            -0.012 |   -0.099 |     0.075 |     0.882 | nan                                                                      |
| brand_search_off   | total business customers (region test) |            -0.093 |   -0.184 |    -0.002 |     0.085 | nan                                                                      |
| social_plus_50     | total business customers (region test) |             0.106 |   -0.007 |     0.220 |     0.345 | nan                                                                      |

## 5. Response curves (marketing-mix model)

One model per business: weekly customers = organic base exp(trend + Fourier) × (1 + Σ β·Hill(adstock(spend))).
Adstock is geometric (decay in [0.0, 0.8], prior mean 0.3); Hill shape 1.0, half-saturation
in [0.2, 5.0]× average spend. Quasi-Poisson weighting divides the history's weight by its over-dispersion, so
calibration to the 3 budget tests binds. The organic base is held near the CRM's organic-source
customers. Uncertainty: 200 weighted-likelihood bootstrap refits with test results redrawn within
their error. [optimisation.md](optimisation.md)

Calibration: 3 of 3 measured test effects fall inside the model's 10-90% range.

| experiment       |   measured |   measured_se |   model |   model_p10 |   model_p90 | business   |
|:-----------------|-----------:|--------------:|--------:|------------:|------------:|:-----------|
| brand_search_off |     -0.093 |         0.045 |  -0.107 |      -0.153 |      -0.045 | B1         |
| retargeting_off  |     -0.012 |         0.043 |  -0.018 |      -0.065 |      -0.000 | B3         |
| social_plus_50   |      0.106 |         0.056 |   0.083 |       0.052 |       0.109 | B3         |

## 6. Optimisation

SLSQP with analytic gradients maximises expected annual contribution across all draws: customers the business
can serve × 24-month value − spend. Constraints: the total budget; business and channel limits; concentration;
keeping at least 90% of each business's customer volume; payback caps on incremental CAC; B2 sales capacity as a
cap on usable leads; untested lines within ±25% of last year; and the average of the worst
10% of draws no worse than last year's split.

| allocation         |   expected_profit |   downside_profit |   p90_profit |   incremental_customers |
|:-------------------|------------------:|------------------:|-------------:|------------------------:|
| status_quo         |         1,993,500 |         1,478,880 |    2,140,900 |                  36,410 |
| platform_roas      |         1,199,530 |           595,162 |    1,456,380 |                  25,946 |
| uncalibrated_model |         2,342,190 |         1,822,170 |    2,519,810 |                  42,216 |
| calibrated_point   |         2,427,760 |         1,884,340 |    2,624,930 |                  43,548 |
| recommended        |         2,430,860 |         1,888,220 |    2,626,980 |                  43,430 |

| line                    |   status_quo |   recommended |      change | verdict                | evidence     |
|:------------------------|-------------:|--------------:|------------:|:-----------------------|:-------------|
| B1.affiliates           |    77,151.20 |     57,268.80 |  -19,882.40 | no-regret cut          | history only |
| B1.search_brand         |   163,195.00 |    183,238.00 |   20,043.00 | depends on assumptions | experiment   |
| B1.search_generic       |   310,665.00 |    384,341.00 |   73,676.00 | no-regret increase     | history only |
| B1.social_prospecting   |   340,895.00 |    314,854.00 |  -26,041.00 | mostly cut             | history only |
| B2.linkedin             |   137,806.00 |    111,176.00 |  -26,630.00 | mostly cut             | history only |
| B2.programmatic_display |   106,897.00 |     79,348.70 |  -27,548.30 | no-regret cut          | history only |
| B2.review_sites         |    79,220.70 |     58,805.00 |  -20,415.70 | mostly cut             | history only |
| B2.search_generic       |   178,019.00 |    137,934.00 |  -40,085.00 | mostly cut             | history only |
| B3.affiliates           |    38,593.80 |     28,648.00 |   -9,945.80 | mostly cut             | history only |
| B3.display_retargeting  |   173,068.00 |     42,822.40 | -130,245.60 | no-regret cut          | experiment   |
| B3.shopping             |   241,556.00 |    298,842.00 |   57,286.00 | no-regret increase     | history only |
| B3.social_prospecting   |   152,933.00 |    302,722.00 |  149,789.00 | no-regret increase     | experiment   |

**Cost of each policy** (gain if removed):

| policy_removed     | solved   |   expected_profit_gain |   downside_profit_change |
|:-------------------|:---------|-----------------------:|-------------------------:|
| untested_guardrail | True     |                268,452 |                  227,218 |
| brand_search_floor | True     |                      0 |                        0 |
| channel_limits     | True     |                 54,485 |                    8,343 |
| business_limits    | True     |                      0 |                        0 |
| concentration      | True     |                      0 |                        0 |
| min_acquisition    | True     |                      0 |                        0 |
| payback            | True     |                      0 |                        0 |
| sales_capacity     | True     |                408,947 |                  229,456 |
| downside           | True     |                      0 |                        0 |

## 7. Sensitivity

21 alternative scenarios change valuation, policy or the model itself (refits with 40
draws). Average share of the budget moved vs the plan: valuation 0.3%, policy 4.4%,
model 3.1%. Each line's direction is labelled no-regret (same in every scenario), mostly, or depends.
The smallest gain of any scenario's plan under base assumptions is $305k. Profit peaks at a total
budget of $1.8M. [sensitivity.md](sensitivity.md)

| line                    |   base_change |   lowest_change |   highest_change |   share_increase |   share_cut | verdict                | evidence     |
|:------------------------|--------------:|----------------:|-----------------:|-----------------:|------------:|:-----------------------|:-------------|
| B1.affiliates           |         -0.26 |           -0.75 |            -0.11 |             0.00 |        1.00 | no-regret cut          | history only |
| B1.search_brand         |          0.12 |           -0.51 |             0.54 |             0.64 |        0.18 | depends on assumptions | experiment   |
| B1.search_generic       |          0.24 |            0.09 |             0.61 |             1.00 |        0.00 | no-regret increase     | history only |
| B1.social_prospecting   |         -0.08 |           -0.48 |             0.17 |             0.09 |        0.86 | mostly cut             | history only |
| B2.linkedin             |         -0.19 |           -0.26 |             0.24 |             0.05 |        0.95 | mostly cut             | history only |
| B2.programmatic_display |         -0.26 |           -0.61 |            -0.11 |             0.00 |        1.00 | no-regret cut          | history only |
| B2.review_sites         |         -0.26 |           -0.29 |             0.14 |             0.05 |        0.95 | mostly cut             | history only |
| B2.search_generic       |         -0.23 |           -0.26 |             0.06 |             0.05 |        0.95 | mostly cut             | history only |
| B3.affiliates           |         -0.26 |           -0.75 |             0.24 |             0.14 |        0.86 | mostly cut             | history only |
| B3.display_retargeting  |         -0.75 |           -0.75 |            -0.72 |             0.00 |        1.00 | no-regret cut          | experiment   |
| B3.shopping             |          0.24 |            0.09 |             0.98 |             1.00 |        0.00 | no-regret increase     | history only |
| B3.social_prospecting   |          0.98 |            0.98 |             0.98 |             1.00 |        0.00 | no-regret increase     | experiment   |

## 8. Reporting and stakeholders

- Monthly KPI commentary is drafted from a 74-fact sheet built from the SQL layer. Code checks every
  sentence (citations, numbers, causal wording, metric names); a named reviewer signs off a hash of the exact
  draft. Claude is optional; the template is the default. [ai_reporting.md](ai_reporting.md)
- A simulated budget review reconciles four stakeholders on one metric framework.
  [stakeholder_simulation.md](stakeholder_simulation.md)

## 9. Validation against the simulation's truth

The data are simulated, so each result can be scored against the truth. Models never see it
(a test enforces this); scoring happens only in `src/marketing_budget/validation/`.

| Check | Result |
|---|---|
| Injected data problems found | 5 of 5 |
| Customer-value intervals containing the true value | 17 of 18 |
| Experiment intervals containing the true effect | 8 of 8 |
| Spend effect estimated from history, vs the true effect | overstated 2.6x-3.6x without controls, 1.2x-2.0x with trend and seasonality |
| Model's 80% next-dollar bands containing the truth | 7 of 12 lines (2 of 3 tested lines) |
| "No-regret" directions right | 6 of 6 |
| "Mostly" directions right | 3 of 5 (wrong: B1 social prospecting, B2 LinkedIn) |
| Plan's true gain vs last year's split | +$268k (model said +$437k); 58% of the achievable $463k |
| Same plan without the 25% guardrail | +$211k |
| Platform-ROAS split | -$804k |
| Budget at which the model's plan truly earns most | $1.8M (model: $1.8M) |

**What this says about the method.**
- Experiments, retention and data checks are well calibrated: their intervals behave as stated.
- The marketing-mix model is not. On untested lines its next-dollar estimate is 0.3x to
  2.2x the truth, and its bands are too narrow. It also overstates the level of
  profit (last year's split: model $1,994k, truth $1,056k), because it credits paid
  media with some organic demand. Gains between plans are more reliable than levels, but are still overstated.
- The safeguards earn their keep: the guardrail adds $57k of true gain, and
  directions that held under every scenario were all right.

### Plans in truth

| allocation                    |   model_expected_profit |   true_profit |   true_gain_vs_status_quo |   share_of_achievable_gain |
|:------------------------------|------------------------:|--------------:|--------------------------:|---------------------------:|
| status_quo                    |               1,993,500 |     1,055,810 |                         0 |                          0 |
| platform_roas                 |               1,199,530 |       251,948 |                   -803862 |                         -2 |
| uncalibrated_model            |               2,342,190 |     1,182,390 |                    126583 |                          0 |
| calibrated_point              |               2,427,760 |     1,334,640 |                    278835 |                          1 |
| recommended                   |               2,430,860 |     1,324,100 |                    268294 |                          1 |
| true_optimum                  |                     nan |     1,518,770 |                    462963 |                          1 |
| recommended_without_guardrail |               2,699,320 |     1,267,010 |                    211198 |                          0 |

### Next-dollar returns: model vs truth (new customers per $1,000)

| business   | channel              |   model_marginal_per_1000 |   model_p10 |   model_p90 |   true_marginal_per_1000 | true_in_80pct_band   |
|:-----------|:---------------------|--------------------------:|------------:|------------:|-------------------------:|:---------------------|
| B1         | affiliates           |                      1.79 |        0.00 |        7.47 |                     4.54 | True                 |
| B1         | search_brand         |                      9.05 |        3.54 |       14.76 |                     3.44 | False                |
| B1         | search_generic       |                     27.78 |       21.79 |       33.48 |                    12.61 | False                |
| B1         | social_prospecting   |                      7.94 |        4.59 |       11.18 |                    17.50 | False                |
| B2         | linkedin             |                      0.63 |        0.00 |        1.24 |                     0.47 | True                 |
| B2         | programmatic_display |                      0.13 |        0.00 |        0.64 |                     0.14 | True                 |
| B2         | review_sites         |                      0.36 |        0.00 |        1.30 |                     0.35 | True                 |
| B2         | search_generic       |                      0.34 |        0.00 |        0.91 |                     0.29 | True                 |
| B3         | affiliates           |                      2.17 |        0.00 |        0.00 |                     8.40 | False                |
| B3         | display_retargeting  |                      2.60 |        0.00 |        6.38 |                     2.95 | True                 |
| B3         | shopping             |                     29.49 |       22.78 |       35.73 |                    18.94 | False                |
| B3         | social_prospecting   |                     35.15 |       23.46 |       46.76 |                    28.52 | True                 |


## 10. Limitations

- **Synthetic data.** The simulation is built to be hard in known ways (over-claiming, demand-following budgets,
  saturation, capacity). A real market has effects it does not, such as competitors and cross-channel synergy.
- **History-only curves are optimistic and over-confident** (section 9). The guardrail, reserve and next tests
  exist because of this.
- **Switch-off tests identify average effects**, not the shape of the curve near today's spend.
- **Flat spend across the year.** The optimiser sets annual totals; seasonal timing is not optimised.
- **No channel interactions.** Each channel's lift is additive within its business.
- **Inputs from management.** Margins, payback targets, B2 capacity and the 24-month horizon are assumptions
  (`configs/config.yaml`); section 7 shows how much they matter.
- **Profit levels are overstated** by the model; compare plans by difference, not level.

## 11. Reproducibility

- Python 3.11; dependencies pinned in `uv.lock`; one seed (20261031) drives the simulation; every random step
  uses its own stream.
- `uv run mbo all` rebuilds everything from nothing in about 15 minutes. Money sums are rounded in SQL and every
  query that feeds an output is ordered, so rebuilds are byte-identical.
- `reports/manifest.csv` records a SHA-256 hash of every committed output. `uv run mbo verify` checks the files
  against it in seconds; `uv run mbo reproduce` rebuilds everything and then checks.
- CI runs ruff, mypy and the tests on a small simulated fixture.
