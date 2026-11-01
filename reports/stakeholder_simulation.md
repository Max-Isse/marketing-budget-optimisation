# Stakeholder management simulation (SYNTHETIC data)

## Summary for management

1. **Business question.** Four people with different priorities must agree next year's paid-acquisition plan.
   How does one body of analysis become a decision they can all sign?
2. **Why it matters.** Without a shared definition of "return", each person wins the argument with a
   different number. Dashboards would side with the Marketing Director, the P&L with the CFO, the CRM with
   the BU Director, and the tracking logs with the Data Engineer, and the budget would follow whoever argues
   best.
3. **What this establishes.** The conflicts are mostly about *which number*, not about goals. Once everyone
   uses one framework (attributed, incremental and next-dollar returns, kept separate), the disagreements
   narrow to two real questions: how much to bet on untested channels, and whether to expand B2's sales
   capacity.
4. **In business terms.**
   - The plan moves $301k between channels. The model expects it to add $437k a year
     (pessimistic case $409k).
   - Increasing the budget would not pay: profit peaks near $1.8M.
   - B2 is limited by its sales team, not by its advertising.
5. **Action to consider.** Approve the reconciled recommendation below:
   - experiment-backed moves now;
   - increases we cannot yet prove ($151k) held as a reserve until tested;
   - a B2 sales-capacity business case;
   - a shared metric framework owned by the Data Engineer.
6. **Assumptions and limits.**
   - The meeting is simulated. The positions are typical of these roles, not quotes.
   - Every figure comes from the pipeline: actual where marked, otherwise model or test-based, as labelled.

## The setting

Annual budget review, 60 minutes. Attendees: CEO (chair), CFO, Marketing Director, B2 Business Unit Director,
Data Engineer, Head of Analytics (presenting). Pre-read: the executive memo, dashboard pages 1–3, and the
metric framework below.

## 1. Stakeholder requirements matrix

| stakeholder                            | wants                                           | watches                                                  | worry                                                               | needs from the analysis                                        | decision rights                         | success looks like                                     |
|:---------------------------------------|:------------------------------------------------|:---------------------------------------------------------|:--------------------------------------------------------------------|:---------------------------------------------------------------|:----------------------------------------|:-------------------------------------------------------|
| Marketing Director                     | More budget to grow customer volume             | Platform ROAS, new customers, share of voice             | Cuts to channels that 'clearly work' on the dashboards              | Where the next dollar works hardest, by channel                | Proposes channel split                  | More profitable customers, a plan the team can execute |
| CFO                                    | Cash efficiency and fast payback                | Contribution after ad spend, payback months, cash out    | Spend justified by numbers that do not tie to the P&L               | Incremental, not attributed, return; the downside case         | Sets total budget and payback targets   | Every dollar defensible; targets met; no surprises     |
| Business Unit Director (B2 Ledgerline) | Leads the sales team can close                  | Qualified leads, win rate, sales workload                | Cheap leads that waste sales time                                   | Qualified leads and customers per dollar, not leads per dollar | Owns sales capacity and lead acceptance | Qualified leads within the 40-a-week the team can work |
| Data Engineer                          | Decisions on numbers that are measured reliably | Tracking coverage, data freshness, reconciliation breaks | Platform pixels and attribution changes silently moving the numbers | Clear metric definitions; which sources are trusted for what   | Owns pipelines and metric definitions   | One definition per metric, checked on every build      |

## 2. Common metric definition framework

The single most useful outcome of the meeting: one definition per word, with its source, owner, evidence
type and what it may be used for. It is the same framework the dashboard and the AI commentary use.

| metric                        | agreed definition                                                                | source              | owner         | evidence type   | used for                                |
|:------------------------------|:---------------------------------------------------------------------------------|:--------------------|:--------------|:----------------|:----------------------------------------|
| Lead                          | First identifiable action, de-duplicated (B2: same e-mail domain within 30 days) | CRM                 | BU Director   | Actual          | Never to judge a channel on its own     |
| Qualified lead                | B1 checkout-ready; B2 sales-accepted; B3 checkout started                        | CRM                 | BU Director   | Actual          | Channel quality; sales workload         |
| New customer                  | First paid transaction                                                           | CRM / billing       | Data Engineer | Actual          | Volume targets, payback                 |
| Platform CAC / ROAS           | Spend per conversion as the ad platform reports it                               | Ad platforms        | Marketing     | Attribution     | Tracking health only, never budgets     |
| Last-click CAC                | Spend per customer whose last click was the channel                              | CRM                 | Marketing     | Attribution     | Day-to-day trends, with care            |
| Incremental CAC / return      | Spend per customer the advertising caused                                        | Randomised tests    | Analytics     | Causal          | Keep, cut or scale a channel            |
| Next-dollar (marginal) return | Contribution from the next dollar on a channel                                   | Calibrated model    | Analytics     | Model           | Splitting the budget                    |
| Customer value                | Discounted contribution per new customer over 24 months                          | Phase 1 cohorts     | Finance       | Model           | The most a customer is worth paying for |
| Payback months                | Months until a customer's contribution covers its CAC                            | Finance + analytics | CFO           | Model           | Cash planning, targets                  |
| Contribution profit           | Contribution from all customers minus acquisition costs and ad spend             | Finance             | CFO           | Actual          | The P&L line marketing answers to       |

**The rule that settles most arguments:** attribution numbers (platform and last-click) describe what was
*credited*; they are for monitoring, not for budgets. Budgets move on causal and calibrated-model evidence.

## 3. Agenda

| Time | Item | Lead | Outcome needed |
|---|---|---|---|
| 0–5 | Purpose: agree next year's split and how we will judge it | CEO | Shared goal: profit, not volume or ROAS |
| 5–15 | One framework for "return" (section 2) | Head of Analytics, Data Engineer | Definitions accepted |
| 15–30 | What the tests and the model say (findings below) | Head of Analytics | Questions answered |
| 30–45 | The disputes: budget size, retargeting, B2 leads and capacity | CEO facilitates | Positions heard against the evidence |
| 45–55 | Reconciled recommendation | Head of Analytics | Decision, or a named open question |
| 55–60 | Measures of success and review dates | CFO | Owners and dates |

## 4. The meeting, simulated

**Marketing Director:** "The dashboards are clear: retargeting returns more than twice what it costs, and
brand search is our best channel. Give us more budget and we'll grow."

**Head of Analytics:** "The dashboards are counting customers who'd have bought anyway. For retargeting:
history suggests 86 customers per $1,000, the platform reports 35, our CRM
credits 23. When we switched it off in randomly chosen regions, we lost about
1.7. Each lens strips out more of the customers who were coming anyway."

**CFO:** "So what is it actually worth?"

**Head of Analytics:** "Switching retargeting off is worth $150k a year; at least
$31k even in the cautious case. That's a test result, not a model guess."

**Marketing Director:** "Fine, but the budget overall: more money still means more customers."

**Head of Analytics:** "More customers, yes. Not more profit. At $2M the last $200k brings back
$0.91 per dollar, and another $200k would bring back $0.43. On the
model, profit peaks near $1.8M. The money is better moved than added."

**BU Director (B2):** "And please don't send me more cheap leads. Half of them never pick up the phone."

**Head of Analytics:** "You're right, and the data backs you. Programmatic display leads cost $77 each,
among your cheapest, but only 1.8% become customers: $4,408 per customer, against
$1,378 through LinkedIn. The LinkedIn lookalike test brought 12% more leads per dollar
and 35% fewer qualified ones. Bigger point: your team works about 40 qualified leads a week, and you're already getting 41. More B2 advertising buys leads nobody can call."

**BU Director (B2):** "So the constraint is my team, not the ads."

**Head of Analytics:** "Exactly. The model values lifting that limit at up to $409k a year. That's
the ceiling for a hiring case, before salaries."

**Data Engineer:** "Before we celebrate, the platform numbers have been unreliable all year."

**Head of Analytics:** "Agreed, and that's why we didn't use them. The checks found 5 problems. The worst
is the tracking change on B1 social prospecting from 21 Jul 2025: the platform started reporting
29% fewer conversions per CRM customer. On platform numbers the channel looked
like it was failing; it wasn't. Budgets now run on the CRM and on tests, so a broken pixel can't move them."

**CFO:** "And if the model is wrong?"

**Head of Analytics:** "Then the plan limits the damage. Channels we've tested move in full. Channels we
haven't move by at most 25%, and the increases we can't yet prove ($151k) stay in reserve until a test
supports them. Even the pessimistic case is $409k a year better than last year's split.
The guardrail costs $268k *on paper*, by the model's own reckoning, and that's the paper
we trust least."

**CEO:** "Then the decision is the split, the reserve, the B2 capacity case and the tracking fixes. Owners and
dates, please."

## 5. What each stakeholder needs to know

**Marketing Director.** Your best channels are not the ones the dashboards show.
- Experiment-backed moves to make now: B3 retargeting -$130k; B3 social prospecting +$150k.
- The new landing page lifts conversion +6.6% ($192k a year): launch it.
- Next tests: B1 generic search, B1 social prospecting, B3 shopping ads. Each one, if positive, releases reserve budget to that channel.

**CFO.** The plan adds $437k a year by the model, $409k in the pessimistic case, with the
reserve held back until tests support it. Every business meets its payback target under the plan:

| business   |   target_months |   payback_months_last_year_split |   payback_months_recommended |   incremental_cac_last_year_split |   incremental_cac_recommended |
|:-----------|----------------:|---------------------------------:|-----------------------------:|----------------------------------:|------------------------------:|
| B1         |              12 |                              7.0 |                          7.0 |                              50.7 |                          48.2 |
| B2         |              18 |                              9.0 |                          8.0 |                           1,883.5 |                       1,485.8 |
| B3         |               9 |                              1.0 |                          0.0 |                              32.7 |                          28.4 |

Last year's split was slowest in B2 (9 months). A payback of 0 months
means the first order already covers the acquisition cost. These are model-based CACs (customers the advertising caused),
higher than the blended CACs on the dashboard, which also count customers who came without ads.

**BU Director (B2).** Judge channels on qualified leads and customers per dollar, never leads per dollar.
B2 ad spend changes by -$115k under the plan, because ads beyond sales capacity buy nothing. The
capacity case is worth up to $409k a year by the model.

Last 52 weeks, CRM last-click (attribution, not incremental):

| channel              | spend   |   leads |   customers | cost per lead   | leads that become customers   | cost per customer   |
|:---------------------|:--------|--------:|------------:|:----------------|:------------------------------|:--------------------|
| LinkedIn             | $136k   |     954 |          99 | $143            | 10.4%                         | $1,378              |
| programmatic display | $106k   |   1,371 |          24 | $77             | 1.8%                          | $4,408              |
| review sites         | $78k    |   1,055 |         104 | $74             | 9.9%                          | $754                |
| generic search       | $176k   |   1,334 |          85 | $132            | 6.4%                          | $2,073              |

**Data Engineer.**
- 5 problems were found and flagged in the data, including 2.9% duplicate B2 leads and
  the B1 social prospecting tracking change.
- Platforms claim up to 1.60x the conversions the CRM credits.
- You own the metric framework. The dashboard and the AI commentary read from the same SQL layer, and a test
  fails if a dashboard column changes.

## 6. Objections and responses

| objection                                                           | raised by          | response                                                                                                                                                                                                                                                    | evidence                                            | what would change our view                                                     |
|:--------------------------------------------------------------------|:-------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------|:-------------------------------------------------------------------------------|
| Retargeting returns over 2x on the platform. Cutting it is madness. | Marketing Director | The platform counts 35 customers per $1,000; switching it off in randomly chosen regions lost about 1.7 (at most 14). Most of what it claims would have bought anyway. Cutting it is worth $150k a year (at least $31k).                                    | Causal (region test)                                | A repeat test in peak season showing a larger loss                             |
| Give us more budget and we will grow faster.                        | Marketing Director | Volume would grow, profit would not: the last $200k of the $2M brings back $0.91 per dollar and another $200k would bring back $0.43. The model's profit peaks near $1.8M.                                                                                  | Model (calibrated), checked in sensitivity analysis | Tests showing an untested channel earns well above $1 per dollar at the margin |
| These are model numbers. How do I know the gain is real?            | CFO                | Part of the plan rests on experiments, part on the model. The experiment-backed moves are made in full; increases we cannot yet prove ($151k) are held as a reserve until tested. The pessimistic case is still $409k a year better than last year's split. | Causal for tested lines, model for the rest         | A quarterly read-out below the pessimistic case                                |
| LinkedIn lookalikes bring more leads for the same money. Switch.    | Marketing Director | They bring 12% more leads per dollar but 35% fewer qualified leads. The sales team would work more leads to win fewer customers.                                                                                                                            | Causal (split test), small sample                   | A longer test showing qualified leads per dollar at least level                |
| Programmatic display gives us some of the cheapest leads in B2.     | Marketing Director | Programmatic display leads cost $77 (number 2 cheapest) but only 1.8% become customers, so each customer costs $4,408, against $1,378 through LinkedIn. Cost per lead is the wrong measure.                                                                 | Actual (CRM)                                        | Better lead scoring that lifts its conversion rate                             |
| We cannot trust any of this: the tracking keeps breaking.           | Data Engineer      | The checks found 5 problems, all now flagged in the data. Budget decisions use the CRM and randomised tests, not platform pixels, so a broken pixel cannot move the budget.                                                                                 | Actual (data-quality checks)                        | A break in the CRM itself (not yet covered by the checks)                      |
| Cutting B2 advertising will starve sales.                           | BU Director        | B2 already produces about 41 qualified leads a week against a team that can work 40. Ads beyond that buy leads nobody calls. Extra capacity, not extra ads, is what grows B2: the model values lifting the limit at up to $409k a year.                     | Actual (volume) and model (value)                   | Sales hiring or faster lead handling                                           |

## 7. Reconciled recommendation

| # | Decision | Satisfies | Evidence |
|---|---|---|---|
| 1 | Make the experiment-backed moves now: B3 retargeting -$130k; B3 social prospecting +$150k | CFO (proven), Marketing (moves money to what works) | Causal |
| 2 | Hold the increases we cannot yet prove ($151k: B1 brand search (+$20k), B1 generic search (+$74k), B3 shopping ads (+$57k)) as a reserve, released line by line when a test shows the next dollar earns more than it costs. B1 brand search stays at last year's level until a part-way cut is tested | Marketing (budget not cut), CFO (cash only on evidence) | Model, to be tested |
| 3 | Keep the total at $2.0M as a ceiling, not a target. Do not increase it: profit peaks near $1.8M | CFO | Model, sensitivity-tested |
| 4 | B2: no extra advertising until sales capacity grows; prepare a hiring case (worth up to $409k a year before cost); keep the job-title LinkedIn audience; judge on qualified leads and customers | BU Director, CFO | Actual, causal and model |
| 5 | Launch the new landing page ($192k a year) | All | Causal |
| 6 | Fix the B1 social prospecting conversion tag, de-duplicate B2 forms at entry, close cost data after restatements, adopt the metric framework (Data Engineer owns it) | Data Engineer, everyone downstream | Actual |
| 7 | Review quarterly against: incremental contribution, payback by business, qualified leads within capacity, test read-outs. Triggers: a result below the pessimistic case reopens the plan | CEO, CFO | — |

## 8. Communicating uncertainty without undermining confidence

1. **Lead with the decision, then the range.** "Cut retargeting: it is worth $150k a year, at least
   $31k", not "the estimate is uncertain, but…".
2. **Label each number once, by where it came from.** Actual, test, model or assumption. People trust a number
   more when they know what kind it is.
3. **Say which conclusions do not depend on the uncertain part.** The no-regret moves hold under every
   assumption we tried; say so. Confidence comes from robustness, not from narrow intervals.
4. **Turn uncertainty into a plan, not a caveat.** The reserve, the guardrail and the next tests are how the
   plan handles what we do not know. Uncertainty becomes a schedule of decisions.
5. **Pre-agree what would change the plan.** Each objection above has a "what would change our view". Agreeing
   these in advance keeps a bad quarter from becoming a debate about the method.
6. **Don't hedge every sentence.** One clear statement of the main limits, in the place they matter, is more
   credible than qualifiers everywhere.
