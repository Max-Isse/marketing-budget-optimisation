# Customer value (SYNTHETIC data)

## Summary for management

1. **Business question.** What is a new customer worth to each business over 24 months, and does
   it depend on where the customer came from?
2. **Why it matters.** Customer value is the most a business can pay to acquire a customer and still profit.
   Every return figure in later phases is customers × this value ÷ spend, so an error here scales every
   recommendation.
3. **What this establishes.** Discounted contribution per new customer, after one-off acquisition costs:
   **B1 $86.98** (95% interval $85.97–$88.02),
   **B2 $5,124** ($5,011–$5,235),
   **B3 $59.08** ($58.84–$59.32).
   Customers acquired long enough ago to be watched for the full 24 months confirm these
   figures (table below).
4. **In business terms.** B1 loses 45% of new subscribers after the first
   box; the customers who stay drive the value. B2 keeps 84% of customers a year, so one
   customer is worth as much as about 59 B1 customers.
   For B3, 46% of a customer's value comes from repeat orders after the first. B1 customers
   credited to affiliates are worth 12% less than average. Because the CRM also
   credits affiliates with organic buyers who clicked a coupon link last, the customers affiliates actually
   bring are probably worth less still.
5. **Action to consider.** Use these values as the ceiling on what each business pays for a customer *the
   advertising actually caused*. Don't compare them with platform-reported CAC: that would set a lower bar
   for channels that claim customers who would have come anyway.
6. **Assumptions and limits.** Contribution per box, licence and order is a finance input (assumption);
   retention is estimated from the data. Monthly churn after the first period is assumed constant; the
   full-horizon check supports this for the early cohorts. Values by acquisition source use the CRM's
   last-click source, which mixes in organic customers.

## How the estimates handle customers who have not finished their lifetime

Customers acquired recently are still active, and their future is unknown (right-censored). Each customer
counts only for the months actually observed: survival is estimated from observed month-to-month
transitions, and repeat orders from observed customer-months. Ignoring censoring would understate
retention, because only the early, already-ended lifetimes would count.

## Subscriptions (B1, B2): survival after the first month and monthly thereafter

| business   | source               |   n_customers |   survival_first_month |   survival_monthly |   customer_value |   value_ci_low |   value_ci_high |
|:-----------|:---------------------|--------------:|-----------------------:|-------------------:|-----------------:|---------------:|----------------:|
| B1         | all sources          |         71341 |                  0.548 |              0.880 |           86.981 |         85.969 |          88.024 |
| B1         | affiliates           |          3657 |                  0.485 |              0.881 |           76.842 |         72.473 |          81.263 |
| B1         | organic              |         14240 |                  0.548 |              0.879 |           86.413 |         84.103 |          88.607 |
| B1         | search_brand         |         10953 |                  0.549 |              0.882 |           88.402 |         85.824 |          90.979 |
| B1         | search_generic       |         18796 |                  0.553 |              0.880 |           88.115 |         86.129 |          90.051 |
| B1         | social_prospecting   |         23695 |                  0.552 |              0.879 |           87.336 |         85.629 |          89.068 |
| B2         | all sources          |          1167 |                  0.989 |              0.986 |        5,123.738 |      5,011.305 |       5,234.807 |
| B2         | linkedin             |           221 |                  0.981 |              0.987 |        5,185.965 |      4,956.022 |       5,438.495 |
| B2         | organic              |           350 |                  0.994 |              0.987 |        5,230.333 |      5,029.876 |       5,423.024 |
| B2         | programmatic_display |            81 |                  0.987 |              0.975 |        4,559.105 |      4,072.961 |       5,059.849 |
| B2         | review_sites         |           262 |                  0.992 |              0.987 |        5,221.035 |      4,987.435 |       5,456.865 |
| B2         | search_generic       |           253 |                  0.984 |              0.984 |        4,997.398 |      4,751.289 |       5,267.490 |

## E-commerce (B3): repeat orders

Repeat order rate in month 1 and its monthly decay, from a Poisson model of orders per observable customer.
`dispersion` above 1 means order counts vary more than a Poisson model assumes; standard errors are widened
by that factor.

| business   | source              |   n_customers |   repeat_rate_first_month |   repeat_decay_monthly |   dispersion |   customer_value |   value_ci_low |   value_ci_high |
|:-----------|:--------------------|--------------:|--------------------------:|-----------------------:|-------------:|-----------------:|---------------:|----------------:|
| B3         | all sources         |         71433 |                     0.050 |                  0.950 |        0.767 |           59.079 |         58.843 |          59.324 |
| B3         | affiliates          |          3572 |                     0.045 |                  0.950 |        0.885 |           56.158 |         55.133 |          57.248 |
| B3         | display_retargeting |         11348 |                     0.049 |                  0.952 |        0.990 |           58.669 |         57.969 |          59.394 |
| B3         | organic             |         23373 |                     0.051 |                  0.950 |        1.088 |           59.313 |         58.829 |          59.787 |
| B3         | shopping            |         21158 |                     0.051 |                  0.950 |        0.780 |           59.283 |         58.857 |          59.718 |
| B3         | social_prospecting  |         11982 |                     0.053 |                  0.947 |        1.144 |           59.532 |         58.845 |          60.236 |

## Check without the truth: fully observed cohorts

Customers acquired Oct 2023–Nov 2024 were watched for the
full horizon. Their actual average discounted contribution is compared with the model's value for all cohorts.

| business   |   n_customers |   observed_value |   observed_ci_half | cohorts_from        | cohorts_to          |   model_value_all_cohorts |
|:-----------|--------------:|-----------------:|-------------------:|:--------------------|:--------------------|--------------------------:|
| B1         |         26153 |           87.401 |              1.602 | 2023-10-30 00:00:00 | 2024-11-23 00:00:00 |                    86.981 |
| B2         |           393 |        5,141.862 |            187.123 | 2023-10-30 00:00:00 | 2024-11-23 00:00:00 |                 5,123.738 |
| B3         |         26299 |           58.850 |              0.458 | 2023-10-30 00:00:00 | 2024-11-23 00:00:00 |                    59.079 |

## Validation against the SYNTHETIC ground truth

`true_value` is the true average value of the customers in each CRM source, a mix of customers the channel
caused and organic customers it was credited with. `true_incremental_value` is the value of the caused
customers alone: what a budget decision needs. 16 of 18 intervals
contain the true value. Where the two true values differ (affiliates), the CRM-source estimate overstates
what the channel's own customers are worth, because the source mixes in organic buyers. Intervals that miss: B3 all sources (error +0.6%); B3 affiliates (error +2.3%). The intervals cover sampling error only, not the simplification of fitting one retention curve to a group whose customers behave differently (for B3, affiliate customers repeat less).

| business   | source               |   n_customers |   customer_value |   value_ci_low |   value_ci_high |   true_value |   error_pct | true_in_ci   |   true_incremental_value |
|:-----------|:---------------------|--------------:|-----------------:|---------------:|----------------:|-------------:|------------:|:-------------|-------------------------:|
| B1         | all sources          |         71341 |           86.981 |         85.969 |          88.024 |       86.964 |       0.000 | True         |                  nan     |
| B1         | affiliates           |          3657 |           76.842 |         72.473 |          81.263 |       77.131 |      -0.004 | True         |                   69.997 |
| B1         | organic              |         14240 |           86.413 |         84.103 |          88.607 |       87.496 |      -0.012 | True         |                   87.496 |
| B1         | search_brand         |         10953 |           88.402 |         85.824 |          90.979 |       87.496 |       0.010 | True         |                   87.496 |
| B1         | search_generic       |         18796 |           88.115 |         86.129 |          90.051 |       87.496 |       0.007 | True         |                   87.496 |
| B1         | social_prospecting   |         23695 |           87.336 |         85.629 |          89.068 |       87.496 |      -0.002 | True         |                   87.496 |
| B2         | all sources          |          1167 |        5,123.738 |      5,011.305 |       5,234.807 |    5,133.363 |      -0.002 | True         |                  nan     |
| B2         | linkedin             |           221 |        5,185.965 |      4,956.022 |       5,438.495 |    5,162.115 |       0.005 | True         |                5,162.115 |
| B2         | organic              |           350 |        5,230.333 |      5,029.876 |       5,423.024 |    5,162.115 |       0.013 | True         |                5,162.115 |
| B2         | programmatic_display |            81 |        4,559.105 |      4,072.961 |       5,059.849 |    4,747.871 |      -0.040 | True         |                4,645.904 |
| B2         | review_sites         |           262 |        5,221.035 |      4,987.435 |       5,456.865 |    5,162.115 |       0.011 | True         |                5,162.115 |
| B2         | search_generic       |           253 |        4,997.398 |      4,751.289 |       5,267.490 |    5,162.115 |      -0.032 | True         |                5,162.115 |
| B3         | all sources          |         71433 |           59.079 |         58.843 |          59.324 |       58.748 |       0.006 | False        |                  nan     |
| B3         | affiliates           |          3572 |           56.158 |         55.133 |          57.248 |       54.920 |       0.023 | False        |                   50.106 |
| B3         | display_retargeting  |         11348 |           58.669 |         57.969 |          59.394 |       58.949 |      -0.005 | True         |                   58.949 |
| B3         | organic              |         23373 |           59.313 |         58.829 |          59.787 |       58.949 |       0.006 | True         |                   58.949 |
| B3         | shopping             |         21158 |           59.283 |         58.857 |          59.718 |       58.949 |       0.006 | True         |                   58.949 |
| B3         | social_prospecting   |         11982 |           59.532 |         58.845 |          60.236 |       58.949 |       0.010 | True         |                   58.949 |
