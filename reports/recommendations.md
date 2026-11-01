# Recommendations (SYNTHETIC data)

> **The data are simulated (SYNTHETIC).** The company, its three businesses and every figure below come from
> a simulation built for this project, because only a simulation reveals each channel's true effect and so
> lets the method be checked. The figures show what the method recommends and how; they are not facts
> about a real company.

## Summary for management

1. **Business question.** What should the company do with next year's $2.0M paid-acquisition
   budget, line by line, and what would make us change course?
2. **Why it matters.** Last year's split was rolled forward and steered by platform dashboards. The model
   estimates that steering harder by those dashboards would cost $794k a year, and that a better
   split would add $437k.
3. **What this establishes.** 6 of the 12 moves hold under every alternative assumption
   tested; 3 lines are anchored by randomised tests. The rest are model estimates from history.
4. **In business terms.** The biggest cuts are B3 retargeting and B2 generic search; the biggest increases B3 social prospecting and B1 generic search.
   Cuts on untested lines stay within the guardrail; increases are committed only where a test supports them.
5. **Action to consider.** The seven actions in the [executive memo](executive_memo.md#4-what-should-management-do),
   applied line by line below.
6. **Assumptions and limits.** Customer values (24 months, 10% discount, finance's margins), payback targets
   and B2 sales capacity are management inputs (`configs/config.yaml`). Untested lines move at most
   25%. Gains are model estimates, not achieved savings.

## Line by line

`across scenarios` is the phase 5 verdict over 21 alternative assumptions: *no-regret* means the
direction never changed. `move now` is reserved for lines that are both tested and no-regret.

| line                    | last year   | plan   | change   | across scenarios       | evidence     | action                     | what would change it                                                   |
|:------------------------|:------------|:-------|:---------|:-----------------------|:-------------|:---------------------------|:-----------------------------------------------------------------------|
| B1 affiliates           | $77k        | $57k   | -$20k    | no-regret cut          | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B1 brand search         | $163k       | $183k  | +$20k    | depends on assumptions | experiment   | reserve until tested       | a test at the new spend showing the next dollar returns less than $1   |
| B1 generic search       | $311k       | $384k  | +$74k    | no-regret increase     | history only | reserve until tested       | a test at the new spend showing the next dollar returns less than $1   |
| B1 social prospecting   | $341k       | $315k  | -$26k    | mostly cut             | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B2 LinkedIn             | $138k       | $111k  | -$27k    | mostly cut             | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B2 programmatic display | $107k       | $79k   | -$28k    | no-regret cut          | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B2 review sites         | $79k        | $59k   | -$20k    | mostly cut             | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B2 generic search       | $178k       | $138k  | -$40k    | mostly cut             | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B3 affiliates           | $39k        | $29k   | -$10k    | mostly cut             | history only | cut now (within guardrail) | a test of a part-way cut showing the dollars cut returned more than $1 |
| B3 retargeting          | $173k       | $43k   | -$130k   | no-regret cut          | experiment   | move now                   | a test of a part-way cut showing the dollars cut returned more than $1 |
| B3 shopping ads         | $242k       | $299k  | +$57k    | no-regret increase     | history only | reserve until tested       | a test at the new spend showing the next dollar returns less than $1   |
| B3 social prospecting   | $153k       | $303k  | +$150k   | no-regret increase     | experiment   | move now                   | a test at the new spend showing the next dollar returns less than $1   |

## Payback (months for the customers advertising adds to repay their acquisition cost)

| business   |   target_months |   payback_months_last_year_split |   payback_months_recommended |
|:-----------|----------------:|---------------------------------:|-----------------------------:|
| B1         |              12 |                              7.0 |                          7.0 |
| B2         |              18 |                              9.0 |                          8.0 |
| B3         |               9 |                              1.0 |                          0.0 |

## Quantified, with the assumptions shown

| Recommendation | Annual value | Assumptions it rests on |
|---|---|---|
| Adopt the plan | +$437k (pessimistic +$409k) | Response curves (3 test-calibrated, the rest history); 24-month values |
| Launch the landing page | +$192k | Test uplift holds after launch; B1 traffic stays at last year's level |
| Reduce B3 retargeting | part of the plan's gain; a full switch-off tested at +$150k | Test period representative of the year |
| B2 capacity case | up to +$409k before hiring | Leads above capacity convert like today's once worked |
| Cap the total at $2.0M | profit would be $17k higher at $1.8M; with the reserve unspent, committed spend starts at $1,849k | Curves for untested lines |

## Risks and what would change the recommendation

See the [executive memo, section 6](executive_memo.md#6-what-could-invalidate-the-recommendation). In short:
a reserve line whose test shows a next-dollar return below $1 stays in reserve or is cut; a B2 hiring cost
below $409k a year makes the capacity case; a repaired B1 social prospecting tag requires a refit.
