# Experimentation (SYNTHETIC data)

## Summary for management

1. **Business question.** Which changes actually win profitable customers, and what does each advertising
   channel *cause*, as opposed to what dashboards credit it with?
2. **Why it matters.** Phase 2 showed that history alone overstates what spend achieves by 1.2–3.6x, because
   budgets were raised when demand was already high. Only randomised tests separate cause from coincidence.
   The three channels tested by changing their budgets in some regions cost
   $0.48M a year.
3. **What this establishes (causal evidence: every result below comes from a randomised test).**
   - **New landing page (B1):** conversion +6.6% (95% range +2.9% to +10.5%).
     Break-even is 0.8%. Adopt: the effect is real and large enough to matter.
   - **New ad creative (B3 social):** click-through +2.3% (-1.1% to +5.7%).
     There is no evidence it is better or worse.
   - **Lookalike audience (B2 LinkedIn):** leads per dollar +12.5%, but *qualified* leads per
     dollar -34.6% (-57.6% to +0.7%). More leads, worse leads.
   - **Retargeting switched off (B3):** customers -1.2% (-9.9% to
     +7.5%): the platform's implied 25% is ruled out: the channel brings in fewer customers than it is credited with.
   - **Brand search switched off (B1):** customers -9.3% (-18.4% to
     -0.2%): consistent with the 15% the platform implies; the test cannot tell them apart.
   - **Social spend +50% (B3):** +10.6% customers (-0.7% to +22.0%).
   - **Target-CPA bidding (B1 generic search):** in the test regions the platform reported +3.6%
     conversions for the same spend, while the CRM's last-click count moved -3.7%.
     Measured effect on all B1 customers: +2.8% (-6.2% to
     +11.7%), too imprecise to confirm any gain.
4. **In business terms (annual contribution, with the cautious-to-optimistic range).**
   - Launch the new landing page: do it: $192k a year ($71k to $318k).
   - Switch off B3 retargeting: do it: $150k a year ($31k to $270k).
   - Switch off B1 brand search: uncertain: $3k a year (-$161k to $167k).
   - Raise B3 social by 50%: uncertain: $77k a year (-$82k to $235k).
   - Switch B2 LinkedIn to lookalikes: uncertain: -$162k a year (-$269k to $3k).
   - Switch to target-CPA bidding: uncertain: $47k a year (-$106k to $201k).
5. **Action to consider.**
   - Launch the new B1 landing page.
   - Switch off B3 retargeting.
   - Do not raise B3 social prospecting spend by 50% yet: the yearly result could be anywhere from -$82k to $235k; a longer or larger test would settle it.
   - Do not switch B1 generic search to target-CPA bidding yet: the yearly result could be anywhere from -$106k to $201k; a longer or larger test would settle it.
   - Do not switch off B1 brand search yet: the yearly result could be anywhere from -$161k to $167k; a longer or larger test would settle it.
   - Do not switch B2 LinkedIn to the lookalike audience: the likely result is a loss of $162k a year (range -$269k to $3k).
   - Judge bidding and audience changes by customers and qualified leads, never by the platform's own conversion
     count or by lead volume.
   - Phase 4 uses these measured effects to calibrate the budget model.
6. **Assumptions and limits.**
   - The tests ran for 8–16 weeks in summer and autumn; effects may differ in peak season.
   - Region tests assume people do not cross regions to buy.
   - LinkedIn's two audiences may overlap.
   - Yearly figures scale a test-period effect to 52 weeks and all regions (assumption), and value
     customers at phase 1's 24-month estimates: B1 $87, B2 $5,117, B3 $59.
   - 3 of the 4 region tests could not reach their target sensitivity even at the
     strongest practical design. Their ranges are honest but wide.

## Correlation, attribution and causal impact

| | Question it answers | Here | Evidence |
|---|---|---|---|
| **Correlation** | Do sales rise in weeks when this channel spends more? | Weekly business customers regressed on the channel's spend | Neither: spend followed demand |
| **Attribution** | Which channel touched the customer last, or at all? | Platform-reported and CRM last-click conversions | An accounting rule; counts customers who would have bought anyway |
| **Causal impact** | What changes if we change the spend? | Randomised tests: regions or users assigned by chance | Causal, within the test's conditions |

Customers per $1,000 of spend, four ways, for the lines whose budgets were tested:

| experiment       | line                   |   spend_change |   correlation_per_1000 |   platform_per_1000 |   last_click_per_1000 |   causal_per_1000 |   causal_change |   causal_ci_low |   causal_ci_high |
|:-----------------|:-----------------------|---------------:|-----------------------:|--------------------:|----------------------:|------------------:|----------------:|----------------:|-----------------:|
| bidding_tcpa     | B1 search_generic      |           -0.3 |                   46.3 |               nan   |                 nan   |             nan   |            78.0 |          -174.6 |            330.7 |
| retargeting_off  | B3 display_retargeting |       -9,426.6 |                   85.9 |                34.6 |                  22.5 |               1.7 |           -15.8 |          -130.4 |             98.7 |
| brand_search_off | B1 search_brand        |      -25,026.9 |                   57.1 |                19.4 |                  21.4 |              11.2 |          -281.2 |          -557.9 |             -4.6 |
| social_plus_50   | B3 social_prospecting  |       10,398.5 |                  111.6 |                35.1 |                  27.2 |              35.2 |           366.1 |           -25.7 |            757.9 |

For retargeting, history suggests 86 customers per $1,000, the platform
35, the CRM 23, and the randomised test
1.7. Each step removes customers who would have come anyway. The bidding test changes no
spend, so per-$1,000 figures do not apply (blank).

## Design: sizing the tests before running them

Each test is sized so that, if the effect worth detecting is real, it is found with 80% probability at a
5% false-alarm rate.

### Customer-level tests

| experiment         | unit                                        | metric                           |   baseline | baseline_source           |   min_worthwhile_effect |   n_per_arm_required |   weeks |   n_per_arm_planned |   mde_at_planned_n |
|:-------------------|:--------------------------------------------|:---------------------------------|-----------:|:--------------------------|------------------------:|---------------------:|--------:|--------------------:|-------------------:|
| landing_page       | visitor                                     | conversion rate (first paid box) |   0.024    | assumption: web analytics |                    0.05 |               261570 |      16 |              240000 |            0.05223 |
| ad_creative        | user                                        | click-through rate               |   0.011    | line_week, last 52 weeks  |                    0.05 |               590327 |       5 |              693259 |            0.0461  |
| audience_targeting | lead (budget split 50/50 between audiences) | qualified leads per dollar       |   0.003211 | line_week, last 52 weeks  |                    0.15 |                  647 |      12 |                  50 |            0.4931  |

The audience test would need **154 weeks** to detect a 15% change in qualified leads, because B2's
LinkedIn produces about 8 qualified leads a week. It ran for the 12-week maximum, knowing it could only
detect changes of about 49%. A test this small can catch a large problem; it cannot certify a small gain.

### Region tests (budget and bidding)

Each test was sized to detect half of what the ad platform claims the channel does (for bidding, a 2% change in
the business's customers). The design picks the cheapest combination of holdout share and duration that gets
there; when none does, it uses the most sensitive one and says so. Sensitivity comes from an A/A rehearsal on the
8 weeks before the test.

| experiment       | line                   | treatment   |   effect_if_platform_right |   target_mde |   treated_share |   regions_treated |   weeks_pre |   weeks_test |   mde_share_of_customers | powered   |   best_possible_mde |
|:-----------------|:-----------------------|:------------|---------------------------:|-------------:|----------------:|------------------:|------------:|-------------:|-------------------------:|:----------|--------------------:|
| bidding_tcpa     | B1 search_generic      | tcpa        |                    nan     |        0.020 |           0.500 |                20 |           8 |           16 |                    0.100 | False     |               0.100 |
| retargeting_off  | B3 display_retargeting | spend x 0   |                      0.253 |        0.126 |           0.250 |                10 |           8 |           12 |                    0.125 | True      |               0.096 |
| brand_search_off | B1 search_brand        | spend x 0   |                      0.154 |        0.077 |           0.500 |                20 |           8 |           16 |                    0.140 | False     |               0.140 |
| social_plus_50   | B3 social_prospecting  | spend x 1.5 |                      0.110 |        0.055 |           0.500 |                20 |           8 |           16 |                    0.083 | False     |               0.083 |

Holding out half the regions for 16 weeks is a real business cost: some customers are lost in the holdout. That
is the price of measuring the effect at all.

## Why peeking at results is dangerous

If a test with no real difference is checked every day and stopped at the first "significant" result, it
produces a false winner **38%** of the time, against
5% when read once at the planned end (112 days, simulated). Checked daily, the landing-page test first looked 'significant' on day 3, showing a +29% uplift, against +6.6% at the planned end.
The creative test's daily p-value never fell below 0.05 (lowest 0.10). Each test is read once, at its
planned end.

## Results: statistical and practical significance

A result can be *statistically* significant (unlikely to be chance) yet too small to be worth acting on, or
*practically* important but too uncertain to bet on. The decision column compares the 95% range with the
smallest effect worth having (`threshold`: break-even for the landing page; any gain for the free creative
switch; 15% for the audience switch).

| experiment         | metric                                 |    n_a |    n_b |   relative_effect |   ci_low |   ci_high |   p_value |   threshold | decision                                                                 |
|:-------------------|:---------------------------------------|-------:|-------:|------------------:|---------:|----------:|----------:|------------:|:-------------------------------------------------------------------------|
| landing_page       | conversion rate                        | 239672 | 240297 |            0.0665 |   0.0293 |    0.1050 |    0.0004 |      0.0077 | adopt: the effect is real and large enough to matter                     |
| ad_creative        | click-through rate                     | 693479 | 693304 |            0.0226 |  -0.0109 |    0.0573 |    0.1882 |      0.0000 | inconclusive: the test cannot tell; extend it or decide on other grounds |
| audience_targeting | leads per $                            |    120 |    135 |            0.1250 |  -0.1203 |    0.4386 |    0.3807 |      0.1500 | inconclusive: the test cannot tell; extend it or decide on other grounds |
| audience_targeting | qualified leads per $                  |     52 |     34 |           -0.3462 |  -0.5756 |    0.0074 |    0.0662 |      0.1500 | no worthwhile effect: even the best case is below the threshold          |
| audience_targeting | customers per $                        |      7 |      2 |           -0.7143 |  -0.9406 |    0.3753 |    0.1797 |      0.1500 | inconclusive: the test cannot tell; extend it or decide on other grounds |
| bidding_tcpa       | total business customers (region test) |     20 |     20 |            0.0276 |  -0.0617 |    0.1168 |    0.2830 |    nan      |                                                                          |
| retargeting_off    | total business customers (region test) |     30 |     10 |           -0.0120 |  -0.0990 |    0.0750 |    0.8825 |    nan      |                                                                          |
| brand_search_off   | total business customers (region test) |     20 |     20 |           -0.0925 |  -0.1835 |   -0.0015 |    0.0845 |    nan      |                                                                          |
| social_plus_50     | total business customers (region test) |     20 |     20 |            0.1063 |  -0.0075 |    0.2201 |    0.3450 |    nan      |                                                                          |

Region-test p-values come from randomisation inference: treatment re-assigned within the same blocks
2,000 times.

### Segments and analysis choices

The landing-page device results are corrected for testing two segments (Holm). The creative test's naive
analysis treats every impression as independent. Because impressions from the same user are correlated, its
range (-0.9% to +5.5%) is narrower than the correct one (-1.1% to +5.7%).

| experiment   | segment                                 |   rate_a |   rate_b |          n_a |          n_b |   relative_effect |   ci_low |   ci_high |   p_value |   p_value_holm |
|:-------------|:----------------------------------------|---------:|---------:|-------------:|-------------:|------------------:|---------:|----------:|----------:|---------------:|
| landing_page | device = desktop                        |   0.0312 |   0.0334 |  96,356.0000 |  96,099.0000 |            0.0717 |   0.0205 |    0.1254 |    0.0055 |         0.0110 |
| landing_page | device = mobile                         |   0.0192 |   0.0204 | 143,316.0000 | 144,198.0000 |            0.0631 |   0.0098 |    0.1192 |    0.0196 |         0.0196 |
| ad_creative  | naive impression-level analysis (wrong) | nan      | nan      |     nan      |     nan      |            0.0226 |  -0.0089 |    0.0552 |    0.1619 |       nan      |

### Region tests in detail

| experiment       | metric                    |   total_effect |   total_ci_low |   total_ci_high |   control_mean_per_region |
|:-----------------|:--------------------------|---------------:|---------------:|----------------:|--------------------------:|
| bidding_tcpa     | customers                 |           78.0 |         -174.6 |           330.7 |                     161.4 |
| bidding_tcpa     | line_last_click_customers |          -31.5 |         -162.8 |            99.7 |                      42.4 |
| bidding_tcpa     | line_platform_conversions |           32.9 |          -97.1 |           162.8 |                      45.8 |
| bidding_tcpa     | line_spend                |           -0.3 |           -0.6 |            -0.0 |                   2,445.9 |
| retargeting_off  | customers                 |          -15.8 |         -130.4 |            98.7 |                     134.9 |
| retargeting_off  | line_last_click_customers |         -212.2 |         -258.8 |          -165.6 |                      23.2 |
| retargeting_off  | line_platform_conversions |         -326.2 |         -426.3 |          -226.0 |                      35.3 |
| retargeting_off  | line_spend                |       -9,426.6 |      -11,463.8 |        -7,389.5 |                     956.3 |
| brand_search_off | customers                 |         -281.2 |         -557.9 |            -4.6 |                     163.7 |
| brand_search_off | line_last_click_customers |         -536.5 |         -641.1 |          -432.0 |                      26.4 |
| brand_search_off | line_platform_conversions |         -485.1 |         -552.3 |          -417.9 |                      25.0 |
| brand_search_off | line_spend                |      -25,026.9 |      -28,467.3 |       -21,586.6 |                   1,302.6 |
| social_plus_50   | customers                 |          366.1 |          -25.7 |           757.9 |                     190.7 |
| social_plus_50   | line_last_click_customers |          282.5 |          156.9 |           408.0 |                      28.5 |
| social_plus_50   | line_platform_conversions |          365.3 |          187.9 |           542.7 |                      38.2 |
| social_plus_50   | line_spend                |       10,398.5 |        8,990.3 |        11,806.7 |                   1,079.2 |

## Incremental customers and contribution profit (annual, if rolled out)

The measured effect is causal. Scaling to a year and valuing customers are assumptions (see `basis`).

| experiment         | decision                                       |   estimate |      low |    high | verdict                                         |
|:-------------------|:-----------------------------------------------|-----------:|---------:|--------:|:------------------------------------------------|
| audience_targeting | switch B2 LinkedIn to the lookalike audience   |   -161,876 | -269,189 |   3,468 | uncertain: the range includes a loss and a gain |
| bidding_tcpa       | switch B1 generic search to target-CPA bidding |     47,338 | -105,925 | 200,601 | uncertain: the range includes a loss and a gain |
| brand_search_off   | switch off B1 brand search                     |      3,380 | -160,736 | 167,497 | uncertain: the range includes a loss and a gain |
| landing_page       | launch the new B1 landing page                 |    192,013 |   70,656 | 317,751 | do it: gains even in the cautious case          |
| retargeting_off    | switch off B3 retargeting                      |    150,253 |   30,616 | 269,890 | do it: gains even in the cautious case          |
| social_plus_50     | raise B3 social prospecting spend by 50%       |     76,769 |  -81,639 | 235,178 | uncertain: the range includes a loss and a gain |

| experiment         | case     |   extra_customers_per_year |   contribution_per_year | basis                                                                                                                 |
|:-------------------|:---------|---------------------------:|------------------------:|:----------------------------------------------------------------------------------------------------------------------|
| landing_page       | estimate |                      2,488 |                 192,013 | uplift x 37,440 paid-landing conversions a year x $87 - $25,000 build cost                                            |
| landing_page       | ci_low   |                      1,097 |                  70,656 | uplift x 37,440 paid-landing conversions a year x $87 - $25,000 build cost                                            |
| landing_page       | ci_high  |                      3,930 |                 317,751 | uplift x 37,440 paid-landing conversions a year x $87 - $25,000 build cost                                            |
| audience_targeting | estimate |                        -32 |                -161,876 | change in qualified leads per $ x $136,390 a year x 20% win rate x $5,117                                             |
| audience_targeting | ci_low   |                        -53 |                -269,189 | change in qualified leads per $ x $136,390 a year x 20% win rate x $5,117                                             |
| audience_targeting | ci_high  |                          1 |                   3,468 | change in qualified leads per $ x $136,390 a year x 20% win rate x $5,117                                             |
| bidding_tcpa       | estimate |                        543 |                  47,338 | test effect scaled to 52 weeks and all regions (treated regions = 47% of customers) x $87; annual line spend $307,473 |
| bidding_tcpa       | ci_low   |                     -1,214 |                -105,925 | test effect scaled to 52 weeks and all regions (treated regions = 47% of customers) x $87; annual line spend $307,473 |
| bidding_tcpa       | ci_high  |                      2,300 |                 200,601 | test effect scaled to 52 weeks and all regions (treated regions = 47% of customers) x $87; annual line spend $307,473 |
| retargeting_off    | estimate |                       -280 |                 150,253 | test effect scaled to 52 weeks and all regions (treated regions = 24% of customers) x $59; annual line spend $171,290 |
| retargeting_off    | ci_low   |                     -2,308 |                  30,616 | test effect scaled to 52 weeks and all regions (treated regions = 24% of customers) x $59; annual line spend $171,290 |
| retargeting_off    | ci_high  |                      1,747 |                 269,890 | test effect scaled to 52 weeks and all regions (treated regions = 24% of customers) x $59; annual line spend $171,290 |
| brand_search_off   | estimate |                     -1,913 |                   3,380 | test effect scaled to 52 weeks and all regions (treated regions = 48% of customers) x $87; annual line spend $161,518 |
| brand_search_off   | ci_low   |                     -3,794 |                -160,736 | test effect scaled to 52 weeks and all regions (treated regions = 48% of customers) x $87; annual line spend $161,518 |
| brand_search_off   | ci_high  |                        -31 |                 167,497 | test effect scaled to 52 weeks and all regions (treated regions = 48% of customers) x $87; annual line spend $161,518 |
| social_plus_50     | estimate |                      2,508 |                  76,769 | test effect scaled to 52 weeks and all regions (treated regions = 47% of customers) x $59; annual line spend $151,361 |
| social_plus_50     | ci_low   |                       -176 |                 -81,639 | test effect scaled to 52 weeks and all regions (treated regions = 47% of customers) x $59; annual line spend $151,361 |
| social_plus_50     | ci_high  |                      5,192 |                 235,178 | test effect scaled to 52 weeks and all regions (treated regions = 47% of customers) x $59; annual line spend $151,361 |

## Validation against the SYNTHETIC ground truth

8 of 8 confidence intervals contain the true effect.

| experiment         | metric                                   |   estimate |   ci_low |   ci_high |   true_value | true_in_ci   |
|:-------------------|:-----------------------------------------|-----------:|---------:|----------:|-------------:|:-------------|
| landing_page       | conversion rate                          |      0.066 |    0.029 |     0.105 |        0.060 | True         |
| ad_creative        | click-through rate                       |      0.023 |   -0.011 |     0.057 |        0.000 | True         |
| audience_targeting | leads per $                              |      0.125 |   -0.120 |     0.439 |        0.250 | True         |
| audience_targeting | qualified leads per $                    |     -0.346 |   -0.576 |     0.007 |       -0.125 | True         |
| bidding_tcpa       | incremental customers in treated regions |     78.028 | -174.598 |   330.654 |      -38.029 | True         |
| retargeting_off    | incremental customers in treated regions |    -15.845 | -130.409 |    98.719 |      -80.416 | True         |
| brand_search_off   | incremental customers in treated regions |   -281.232 | -557.904 |    -4.561 |     -281.584 | True         |
| social_plus_50     | incremental customers in treated regions |    366.088 |  -25.747 |   757.924 |      250.712 | True         |

### Is the region-test method sound? (each test re-run 40 times with fresh random draws)

The average estimate should match the average true effect (bias near 0 standard errors), and 95% intervals
should contain the truth about 95% of the time.

| experiment       |   repetitions |   mean_estimate |   mean_true_effect |   bias_in_standard_errors |   ci_coverage |
|:-----------------|--------------:|----------------:|-------------------:|--------------------------:|--------------:|
| bidding_tcpa     |            40 |         -59.348 |            -40.629 |                    -0.691 |         0.900 |
| retargeting_off  |            40 |         -99.300 |            -82.185 |                    -1.386 |         0.975 |
| brand_search_off |            40 |        -298.288 |           -289.075 |                    -0.391 |         0.950 |
| social_plus_50   |            40 |         243.220 |            257.098 |                    -0.507 |         0.975 |
