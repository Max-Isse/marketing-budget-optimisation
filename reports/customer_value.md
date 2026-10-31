# Customer value (SYNTHETIC data)

## Summary for management

1. **Business question.** What is a new customer worth to each business over 24 months, and does
   it depend on where the customer came from?
2. **Why it matters.** Customer value is the most a business can pay to acquire a customer and still profit.
   Every return figure in later phases is customers × this value ÷ spend, so an error here scales every
   recommendation.
3. **What this establishes.** Discounted contribution per new customer, after one-off acquisition costs:
   **B1 $87.22** (95% interval $86.21–$88.27),
   **B2 $5,117** ($5,002–$5,231),
   **B3 $59.02** ($58.75–$59.29).
   Customers acquired long enough ago to be watched for the full 24 months confirm these
   figures (table below).
4. **In business terms.** B1 loses 45% of new subscribers after the first
   box; the customers who stay drive the value. B2 keeps 84% of customers a year, so one
   customer is worth as much as about 59 B1 customers.
   For B3, 46% of a customer's value comes from repeat orders after the first. B1 customers
   credited to affiliates are worth 10% less than average. Because the CRM also
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
| B1         | all sources          |         71341 |                  0.550 |              0.880 |           87.223 |         86.207 |          88.266 |
| B1         | affiliates           |          3657 |                  0.502 |              0.879 |           78.910 |         74.519 |          83.332 |
| B1         | organic              |         14240 |                  0.559 |              0.878 |           87.635 |         85.318 |          89.840 |
| B1         | search_brand         |         10953 |                  0.552 |              0.882 |           88.851 |         86.269 |          91.429 |
| B1         | search_generic       |         18796 |                  0.547 |              0.880 |           86.988 |         85.008 |          88.919 |
| B1         | social_prospecting   |         23695 |                  0.553 |              0.880 |           87.681 |         85.970 |          89.415 |
| B2         | all sources          |          1154 |                  0.987 |              0.986 |        5,117.286 |      5,002.113 |       5,230.993 |
| B2         | linkedin             |           242 |                  0.983 |              0.984 |        5,024.623 |      4,781.326 |       5,303.236 |
| B2         | organic              |           332 |                  0.987 |              0.987 |        5,217.829 |      5,005.296 |       5,416.677 |
| B2         | programmatic_display |            73 |                  0.986 |              0.984 |        4,987.020 |      4,527.099 |       5,453.851 |
| B2         | review_sites         |           273 |                  0.985 |              0.987 |        5,161.608 |      4,922.650 |       5,407.613 |
| B2         | search_generic       |           234 |                  0.996 |              0.984 |        5,059.280 |      4,804.204 |       5,329.788 |

## E-commerce (B3): repeat orders

Repeat order rate in month 1 and its monthly decay, from a Poisson model of orders per observable customer.
`dispersion` above 1 means order counts vary more than a Poisson model assumes; standard errors are widened
by that factor.

| business   | source              |   n_customers |   repeat_rate_first_month |   repeat_decay_monthly |   dispersion |   customer_value |   value_ci_low |   value_ci_high |
|:-----------|:--------------------|--------------:|--------------------------:|-----------------------:|-------------:|-----------------:|---------------:|----------------:|
| B3         | all sources         |         71829 |                     0.051 |                  0.949 |        0.976 |           59.017 |         58.752 |          59.292 |
| B3         | affiliates          |          3433 |                     0.044 |                  0.944 |        0.790 |           54.577 |         53.614 |          55.602 |
| B3         | display_retargeting |         11583 |                     0.051 |                  0.951 |        0.987 |           59.892 |         59.173 |          60.630 |
| B3         | organic             |         24392 |                     0.051 |                  0.949 |        0.717 |           59.305 |         58.920 |          59.682 |
| B3         | shopping            |         20957 |                     0.050 |                  0.949 |        1.213 |           58.936 |         58.406 |          59.477 |
| B3         | social_prospecting  |         11464 |                     0.051 |                  0.949 |        1.032 |           59.016 |         58.350 |          59.701 |

## Check without the truth: fully observed cohorts

Customers acquired Oct 2023–Nov 2024 were watched for the
full horizon. Their actual average discounted contribution is compared with the model's value for all cohorts.

| business   |   n_customers |   observed_value |   observed_ci_half | cohorts_from        | cohorts_to          |   model_value_all_cohorts |
|:-----------|--------------:|-----------------:|-------------------:|:--------------------|:--------------------|--------------------------:|
| B1         |         26154 |           87.560 |              1.581 | 2023-10-30 00:00:00 | 2024-11-23 00:00:00 |                    87.223 |
| B2         |           382 |        5,101.326 |            200.648 | 2023-10-30 00:00:00 | 2024-11-22 00:00:00 |                 5,117.286 |
| B3         |         25559 |           59.329 |              0.468 | 2023-10-30 00:00:00 | 2024-11-23 00:00:00 |                    59.017 |

## Validation against the SYNTHETIC ground truth

`true_value` is the true average value of the customers in each CRM source, a mix of customers the channel
caused and organic customers it was credited with. `true_incremental_value` is the value of the caused
customers alone: what a budget decision needs. 17 of 18 intervals
contain the true value. Where the two true values differ (affiliates), the CRM-source estimate overstates
what the channel's own customers are worth, because the source mixes in organic buyers. Intervals that miss: B3 display_retargeting (error +1.6%). The intervals cover sampling error only, not the simplification of fitting one retention curve to a group whose customers behave differently (a CRM source mixes customers the channel caused with organic ones), and roughly 1 interval in 20 misses by chance.

| business   | source               |   n_customers |   customer_value |   value_ci_low |   value_ci_high |   true_value |   error_pct | true_in_ci   |   true_incremental_value |
|:-----------|:---------------------|--------------:|-----------------:|---------------:|----------------:|-------------:|------------:|:-------------|-------------------------:|
| B1         | all sources          |         71341 |           87.223 |         86.207 |          88.266 |       86.964 |       0.003 | True         |                  nan     |
| B1         | affiliates           |          3657 |           78.910 |         74.519 |          83.332 |       77.131 |       0.023 | True         |                   69.997 |
| B1         | organic              |         14240 |           87.635 |         85.318 |          89.840 |       87.496 |       0.002 | True         |                   87.496 |
| B1         | search_brand         |         10953 |           88.851 |         86.269 |          91.429 |       87.496 |       0.015 | True         |                   87.496 |
| B1         | search_generic       |         18796 |           86.988 |         85.008 |          88.919 |       87.496 |      -0.006 | True         |                   87.496 |
| B1         | social_prospecting   |         23695 |           87.681 |         85.970 |          89.415 |       87.496 |       0.002 | True         |                   87.496 |
| B2         | all sources          |          1154 |        5,117.286 |      5,002.113 |       5,230.993 |    5,137.512 |      -0.004 | True         |                  nan     |
| B2         | linkedin             |           242 |        5,024.623 |      4,781.326 |       5,303.236 |    5,162.115 |      -0.027 | True         |                5,162.115 |
| B2         | organic              |           332 |        5,217.829 |      5,005.296 |       5,416.677 |    5,162.115 |       0.011 | True         |                5,162.115 |
| B2         | programmatic_display |            73 |        4,987.020 |      4,527.099 |       5,453.851 |    4,773.189 |       0.045 | True         |                4,645.904 |
| B2         | review_sites         |           273 |        5,161.608 |      4,922.650 |       5,407.613 |    5,162.115 |      -0.000 | True         |                5,162.115 |
| B2         | search_generic       |           234 |        5,059.280 |      4,804.204 |       5,329.788 |    5,162.115 |      -0.020 | True         |                5,162.115 |
| B3         | all sources          |         71829 |           59.017 |         58.752 |          59.292 |       58.756 |       0.004 | True         |                  nan     |
| B3         | affiliates           |          3433 |           54.577 |         53.614 |          55.602 |       54.911 |      -0.006 | True         |                   50.106 |
| B3         | display_retargeting  |         11583 |           59.892 |         59.173 |          60.630 |       58.949 |       0.016 | False        |                   58.949 |
| B3         | organic              |         24392 |           59.305 |         58.920 |          59.682 |       58.949 |       0.006 | True         |                   58.949 |
| B3         | shopping             |         20957 |           58.936 |         58.406 |          59.477 |       58.949 |      -0.000 | True         |                   58.949 |
| B3         | social_prospecting   |         11464 |           59.016 |         58.350 |          59.701 |       58.949 |       0.001 | True         |                   58.949 |
