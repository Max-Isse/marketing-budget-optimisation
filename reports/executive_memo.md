# Executive decision memo: next year's paid-acquisition plan

**To:** CEO, CFO, Marketing Director · **From:** Head of Analytics · **Decision:** how to spend the
$2.0M paid-acquisition budget across Hearth Box (B1), Ledgerline (B2) and Atlas Outdoor (B3)

> **The data are simulated (SYNTHETIC).** The company, its three businesses and every figure below come from
> a simulation built for this project, because only a simulation reveals each channel's true effect and so
> lets the method be checked. The figures show what the method recommends and how; they are not facts
> about a real company.

**Recommendation.** Approve a plan that keeps the total within $2.0M but moves $301k
between channels, makes the tested moves now, and holds $151k of unproven increases in reserve until
tests support them. The model expects it to add **$437k a year of contribution** (pessimistic case
$409k). Separately, decide whether to expand B2's sales team: that, not advertising, now limits B2.

**Evidence labels.** *Actual*: measured in the company's own systems. *Causal*: measured by a randomised
test. *Model*: estimated by the marketing-mix model; depends on its assumptions. *Assumption*: a finance or
management input, not something the data showed.

## 1. What is happening?

- Last year's split, scaled to the $2.0M budget, is B1 Hearth Box $892k, B2 Ledgerline $502k, B3 Atlas Outdoor $606k (actual spend over the
  last 52 weeks: $1,979k). *Actual.*
- **The dashboards and the economics disagree.** Ad platforms claim up to 1.6x the conversions the
  company's CRM credits to them. *Actual.* For B3 retargeting, the platform credits 35 new customers
  per $1,000, CRM last click 23, and a randomised test about 2 (at most
  14). *Causal.* Most of what retargeting is credited with would have happened anyway.
- **B2 has outgrown its sales team.** It produces 41 qualified leads a week; the team can work
  40. *Actual; capacity is a management input.*
- **Some numbers were wrong.** 5 data problems were found, including a tracking change from
  21 Jul 2025 that makes B1 social prospecting look worse than it is, and duplicate B2 demo requests
  (2.9% of leads). *Actual.*

## 2. Why?

- **Platforms count customers who were already on their way.** That is why retargeting and brand search look
  best on dashboards and earn least from the next dollar.
- **Budgets followed demand.** Spend was raised in strong seasons, so history credits advertising with demand
  that was there anyway: the measured effect of spend falls to 46%-63% of its raw size once
  season and trend are accounted for. *Model (regression on history).*
- **Returns diminish.** At last year's split the next dollar earned anywhere from $0.01
  (B2 programmatic display) to $2.42 (B1 generic search) of 24-month contribution. *Model.* Every B2 line is near zero because its sales team is full: extra leads go unworked. Money
  was in the wrong places, not too little of it.

## 3. What are the financial consequences?

| | Annual contribution | Evidence |
|---|---|---|
| Recommended plan vs last year's split | +$437k (pessimistic +$409k) | Model |
| Steering by platform ROAS instead | -$794k | Model |
| New B1 landing page | +$192k | Causal |
| Switching off B3 retargeting entirely | +$150k (cautious +$31k) | Causal |
| Lifting B2's sales-capacity limit, before hiring costs | up to +$409k | Model |
| Moving untested lines by more than 25% | up to +$268k, not taken (see section 6) | Model |

The budget itself is not the constraint: the last $200k returned about $0.91 per dollar, and profit
peaks near $1.8M. Every business meets its payback target under the plan. *Model.*

## 4. What should management do?

|   # | action                                                                                                                                                                                                                                                                    | owner                            | when                            | evidence               |
|----:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------|:--------------------------------|:-----------------------|
|   1 | Make the tested moves now (B3 retargeting -$130k; B3 social prospecting +$150k) and the cuts the model supports on untested lines (-$171k: B2 generic search, B2 programmatic display, B2 LinkedIn, B1 social prospecting, B2 review sites, B1 affiliates, B3 affiliates) | Marketing Director               | Next budget cycle               | Causal + Model         |
|   2 | Launch the new B1 landing page (+$192k a year, range $71k to $318k)                                                                                                                                                                                                       | B1 general manager               | Now                             | Causal                 |
|   3 | Hold $151k of increases as a reserve (B1 brand search (+$20k), B1 generic search (+$74k), B3 shopping ads (+$57k)); release each line when a test shows its next dollar earns more than it costs                                                                          | CFO (release), Analytics (tests) | Line by line, as tests read out | Model, to be tested    |
|   4 | Treat $2.0M as a ceiling, not a target; do not raise it. Profit peaks near $1.8M; with the reserve unspent, committed spend starts at $1,849k, and the reserve is the first money to return if tests disappoint                                                           | CFO                              | This budget round               | Model                  |
|   5 | Prepare a B2 sales-capacity business case: lifting the 40-leads-a-week limit is worth up to $409k a year before hiring costs                                                                                                                                              | B2 BU Director, CFO              | Next quarter                    | Model                  |
|   6 | Run the next tests where the money at stake is largest: B1 generic search, B1 social prospecting, B3 shopping ads                                                                                                                                                         | Analytics, Marketing             | Start within the quarter        | Model (prioritisation) |
|   7 | Fix the B1 social prospecting conversion tag, remove duplicate B2 demo requests at entry (2.9% of leads), and judge channels on the shared metric framework, not platform ROAS                                                                                            | Data Engineer                    | Now                             | Actual                 |

## 5. What evidence supports this?

| finding                                                                         | number                                    | evidence                                | detail in                 |
|:--------------------------------------------------------------------------------|:------------------------------------------|:----------------------------------------|:--------------------------|
| Ad platforms claim more conversions than the CRM credits                        | up to 1.6x                                | Actual                                  | data_quality.md           |
| B3 retargeting: customers per $1,000 by platform / last click / randomised test | 35 / 23 / 2 (test range up to 14)         | Actual / Actual / Causal                | experiments.md            |
| New B1 landing page: conversion uplift                                          | +6.6%, +$192k a year                      | Causal                                  | experiments.md            |
| Switching off B3 retargeting entirely                                           | +$150k a year (cautious case +$31k)       | Causal                                  | experiments.md            |
| LinkedIn lookalike audiences (B2)                                               | 12% more leads, 35% fewer qualified leads | Causal                                  | experiments.md            |
| B2 qualified leads a week vs what sales can work                                | 41 vs 40                                  | Actual / Assumption                     | stakeholder_simulation.md |
| Recommended plan vs last year's split                                           | +$437k a year (pessimistic +$409k)        | Model                                   | optimisation.md           |
| Steering by platform ROAS instead                                               | -$794k a year                             | Model                                   | optimisation.md           |
| Moves that hold under every one of the alternative assumptions                  | 6 of 12 lines                             | Model                                   | sensitivity.md            |
| Budget at which profit peaks                                                    | $1.8M                                     | Model                                   | sensitivity.md            |
| 24-month value of a new customer: B1 / B2 / B3                                  | $87 / $5,117 / $59                        | Actual (cohorts) + Assumption (margins) | customer_value.md         |
| Error of the quarterly new-customer forecast                                    | 3-19% across businesses                   | Actual (back-test)                      | forecasting.md            |

Reports are in [reports/](.); the method is in [technical_report.md](technical_report.md).

## 6. What could invalidate the recommendation?

- **Untested lines rest on history.** Only 3 of 12 lines have a test behind them. On
  some untested lines the model looks optimistic: B1 generic search (28 customers per $1,000 for the next dollar vs 21 the platform credits on average). A next dollar should not beat the
  platform's own average claim. Hence the 25% limit on untested lines and the reserve.
- **Some moves depend on assumptions.** 5 lines move in the same direction in most but not all of
  21 alternative scenarios (B1 social prospecting, B2 LinkedIn, B2 review sites, B2 generic search, B3 affiliates). Treat these as probable, not proven.
- **Tests measure averages.** A switch-off test shows what a channel's whole budget does, not its next dollar.
- **Value assumptions.** Customer values use a 24-month horizon, a 10% discount rate and finance's margins. If every
  customer were worth 20% less, the plan would still gain $350k; valuation choices move only
  0.3% of the budget. *Model.*
- **Not modelled:** seasonal timing of spend, channels boosting each other, competitor moves, and the cost of
  hiring B2 sales staff.

**What would change the recommendation:** a test showing a reserve line's next dollar returns less than $1 (keep it
in reserve or cut); a B2 hiring cost below $409k a year (expand B2); a fixed tracking tag that changes
B1 social prospecting's numbers (re-run the model).

## 7. How will success be measured?

| measure                                  | success means                                                                           | source                                           | when                                | owner          |
|:-----------------------------------------|:----------------------------------------------------------------------------------------|:-------------------------------------------------|:------------------------------------|:---------------|
| Contribution after ad spend, by business | At or above the plan's pessimistic case                                                 | P&L (Actual)                                     | Monthly; formal review each quarter | CFO            |
| Incremental customers on the moved lines | Measured by a 10% region holdout on each line whose spend moved by more than 10%        | Region holdout (Causal)                          | Read out at 12 weeks                | Analytics      |
| Reserve releases                         | Released only where the test's cautious case shows the next dollar returns more than $1 | Region test (Causal)                             | As each test reads out              | CFO            |
| Payback by business                      | B1 within 12 months / B2 within 18 months / B3 within 9 months                          | Cohort value vs incremental CAC (Actual + Model) | Quarterly                           | CFO            |
| B2 sales workload                        | Qualified leads at or below 40 a week, unless capacity is added                         | CRM (Actual)                                     | Weekly                              | B2 BU Director |
| Forecast accuracy                        | Actual quarterly customers inside the forecast's 80% range                              | Forecast vs actual                               | Quarterly                           | Analytics      |
| Data trust                               | Every data-quality check passes before figures go to management                         | Pipeline checks (Actual)                         | Every build                         | Data Engineer  |

## Annex: does the method work? (simulation only)

Because the data are simulated, the plan can be scored against the true effects, which no real company could
do. The model expected +$437k; the plan **really earns +$268k a year**,
58% of the $463k that perfect knowledge would achieve. Steering by platform
ROAS would really lose $804k. All 6 moves that held under every assumption point the
right way; 2 of 5 "probably" moves on untested lines do not
(B1 social prospecting, B2 LinkedIn). The model overstates the gain by about
63%: the reason for the reserve, the guardrail and the tests in actions 3 and 6.
Full scoring: [technical_report.md](technical_report.md#9-validation-against-the-simulations-truth).
