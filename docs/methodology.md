# Methodology: why each method, what it assumes, how that was checked, where it fails

Results are in [reports/technical_report.md](../reports/technical_report.md), which is generated. This page
holds the reasoning and has no result numbers. Judgement calls are logged in [decisions.md](decisions.md).

## Data-quality checks

| | |
|---|---|
| **Why** | Every later number depends on it. A broken tag looks the same as a channel losing performance. |
| **Method** | Structural checks for completeness, funnel order and cross-table reconciliation. Scans for four problems: tracking outages (platform zero, CRM not); attribution change-points (log platform/CRM ratio, 4-week blocks then weekly refinement, Bonferroni-adjusted, with a minimum size of change); duplicate leads (same contact within a window); cost restatements. |
| **Assumes** | The CRM is the more stable source, so a change in the platform/CRM ratio is a tracking change, not a real one. |
| **Checked** | Scored against the problems injected into the simulation, including false alarms. |
| **Fails when** | Both sources change at once, or a change is gradual rather than a step. |

## Customer value

| | |
|---|---|
| **Why** | The most a business can pay for a customer is what the customer is worth. Average order value ignores retention. |
| **Method** | Subscriptions: survival with a separate first-month hazard and a constant hazard after that, fitted with censoring, because recent customers have not had time to churn. E-commerce: a Poisson GLM of repeat orders with monthly decay. Value is 24-month discounted contribution; intervals come from parameter draws. |
| **Assumes** | Retention after the first month is constant (subscriptions) or decays geometrically (repeat orders). New customers behave like recent cohorts. |
| **Checked** | Fully observed early cohorts, valued directly, against the model's estimate. Model fit compared by source. |
| **Fails when** | Retention changes shape, or the customer mix shifts. CRM-source values mix customers a channel caused with organic customers it was credited with. |

## Forecasting

| | |
|---|---|
| **Why** | Planning needs a baseline with an honest range. Simple baselines show whether complexity earns its keep. |
| **Method** | Naive, seasonal naive, Holt-Winters ETS, a regression (trend, Fourier seasonality, log planned spend) and gradient boosting on detrended data. Rolling-origin back-test: no fold sees its future. Intervals from back-test errors, with leave-one-origin-out coverage. Parsimony rule: take the simplest model within a tolerance of the best. |
| **Assumes** | Next year's seasonality resembles past years'. Planned spend is known in advance. |
| **Checked** | MAE, RMSE, WAPE and bias by horizon. Interval coverage against its target. Leakage tests confirm that models ignore future actuals and that each back-test fold trains only on the past. |
| **Fails when** | There is a structural break, such as a new channel, a price change or a competitor. **The spend coefficient is not causal**: budgets followed demand, so history credits spend with demand that was already there. Forecasts are never used to set budgets. |

## Experiments

| | |
|---|---|
| **Why** | Only randomisation separates what a channel causes from what it is credited with. |
| **Method** | Each test is designed before launch: minimum worthwhile effect, sample size or holdout share and duration. Region designs are chosen by an A/A rehearsal on pre-period data. User-level tests use two-proportion tests, the delta method for ratio metrics and Poisson rates for counts. Region tests use ANCOVA on the pre-period with HC2 errors and t critical values, confirmed by randomisation inference. Decisions compare the interval to the business's break-even threshold, not to zero. Holm correction across metrics; no early stopping (a peeking simulation shows why). |
| **Assumes** | Regions do not affect each other. The test period is representative. The pre-period predicts the test period. |
| **Checked** | Each interval against the true effect. Each region-test method re-run many times with fresh draws, to check bias and coverage. |
| **Fails when** | Regions spill over (for example national TV or shipping), effects vary by season, or the business is too small for a test to detect a worthwhile effect. That last case is reported, not hidden. |

## Response curves (marketing-mix model)

| | |
|---|---|
| **Why** | A budget decision needs the return on the **next** dollar, which neither attribution nor a switch-off test gives directly. |
| **Method** | One model per business: organic base exp(trend + Fourier) × (1 + Σ β·Hill(adstock)). Geometric adstock and Hill saturation per channel, with weak priors on decay and half-saturation. Quasi-Poisson scaling divides the history's weight by its over-dispersion. Calibration terms tie the model to the region tests. An organic floor holds the base near the customers who arrive without a paid click. Weighted-likelihood bootstrap for uncertainty. |
| **Assumes** | Channels add up within a business, with no synergy. The curve shape is the same all year. Past spend variation is enough to identify each curve. |
| **Checked** | It must reproduce the calibrating tests. Its next-dollar estimates and bands are scored against the truth line by line. |
| **Fails when** | A line has no test and little spend variation. Its curve then comes from history, which leans optimistic because budgets followed demand. The bands are too narrow, and the level of profit is overstated. **Mitigations:** the untested-line guardrail, the reserve, the downside constraint, and tests aimed at the most uncertain money. |

## Optimiser

| | |
|---|---|
| **Why** | Equalising next-dollar returns under real policies, with uncertainty, is what "allocate the budget" means. |
| **Method** | SLSQP with analytic gradients maximises expected contribution across all bootstrap draws. Constraints: total budget, business and line limits, concentration, minimum customer volume, payback caps, B2 sales capacity, a guardrail on untested lines, and a CVaR floor (the average of the worst draws may be no worse than last year's split). Each policy's cost is measured by removing it. |
| **Assumes** | Spend is flat within the year. The curves above are right on average. Policy inputs are management's. |
| **Checked** | Feasibility of every scenario. The plan's true profit compared with last year's split, the platform-ROAS split and the true optimum. |
| **Fails when** | The curves are wrong in a correlated way across lines, so the downside draws do not cover it. |

## Sensitivity

| | |
|---|---|
| **Why** | A recommendation that flips under a reasonable alternative assumption is not a recommendation. |
| **Method** | Alternative valuation, policy and model scenarios, each re-optimised. Each line's direction is labelled no-regret, mostly or depends on assumptions. A budget curve across total budgets. |
| **Checked** | Each verdict's direction against the true optimum. |
| **Fails when** | Every scenario shares the same blind spot. For untested lines, agreement across scenarios is weaker evidence than for tested ones. |

## AI-assisted commentary

| | |
|---|---|
| **Why** | Monthly commentary is repetitive. The risk is an LLM inventing numbers or causal claims. |
| **Method** | A fact sheet from the SQL layer. Code checks every sentence (citations, numbers at the precision written, metric vocabulary, causal wording only for causal facts). One retry, then a template. A named reviewer signs off a hash of the exact draft. |
| **Fails when** | A fact is wrong upstream: the checks verify consistency with the fact sheet, not truth. |
