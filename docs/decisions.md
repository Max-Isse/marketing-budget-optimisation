# Decision log

Judgement calls, with the alternatives considered. OPEN items are decided in the phase named.

## D-001 Synthetic data, despite the "use real public data" standard
**Choice:** simulate the company: three businesses, 12 channel lines, 156 weeks, customer cohorts and five
experiments. All generated data carry `synthetic` in their names.
**Why:** the brief needs, all at once, spend by channel, a funnel down to customers, customer economics,
experiments, *and* the true incremental effect of each channel. No public dataset has that last part. That
part is the most important, because it is the only way to show that the method separates attribution from
causation instead of just claiming to.
**Cost:** results show that the method works; they are not facts about a market. Every report says so.
**Alternatives:**
- *Public MMM sample data* (e.g. the Robyn and Meridian demo sets): single business, no funnel or customer
  economics, and no known truth.
- *Kaggle ad-campaign datasets*: platform metrics only, no incrementality.
- *Criteo uplift data*: real randomised data, but one channel with no spend.

## D-002 Ground truth sealed in its own config; models cannot read it
**Choice:** the true parameters live in `configs/ground_truth_SYNTHETIC.yaml`. Only the generator, the
validation package and the CLI that orchestrates them may load it. `tests/test_isolation.py` enforces this.
**Why:** if a model could read the truth, its validation would be meaningless.
**Alternatives:** one config with a "do not read" comment (not enforceable).

## D-003 Weekly grain, three years
**Choice:** weekly data by business and channel, 156 weeks. Experiments are generated at their own
randomisation level.
**Why:** weekly is the grain at which budgets are managed and media effects are usually modelled. Three
years gives two full seasonal cycles for fitting and one for rolling-origin testing.
**Alternatives:** daily (noisier, and heavy day-of-week effects distract from the decision); monthly (only
36 points, too few to separate seasonality from media).

## D-004 Decision metric: incremental 24-month discounted contribution, net of spend
**Choice:** value each incremental customer at 24-month discounted contribution minus one-off acquisition
costs, at a 10% annual discount rate. Payback months are reported alongside and constrained per business.
**Why:** revenue ROAS ignores margins, and margins differ several-fold between the businesses. First-order
profit ignores retention, which is what makes B1 and B2 worth acquiring. Lifetime value without a horizon
leans on retention far beyond the observed data.
**Alternatives:** 12- or 36-month horizons. These are tested in phase 5 sensitivity analysis, because B2's
value depends heavily on the horizon.

## D-005 Response curves: geometric adstock + Hill saturation
**Choice:** each line's incremental leads follow Hill(adstock(spend)). The same family is used to generate
the data and to fit models in phase 4.
**Why:** it is the standard parsimonious form. It has carry-over, diminishing returns and an optional S-shape,
each controlled by one parameter that can be explained.
**Risk:** using the same family in generator and model makes recovery easier than in reality. Phase 4
therefore also fits a misspecified alternative (log response) and reports how much the recommendation moves.
**Alternatives:** Weibull adstock; a fully Bayesian MMM (PyMC-Marketing or Meridian). The latter is outside the
brief's stack, and bootstrap uncertainty gives the optimiser what it needs.

## D-006 Uncertainty in the optimiser: optimise over curve draws
**Choice:** draw 500 sets of response-curve parameters from the fitted uncertainty. Choose the allocation
that maximises average net contribution across the draws, subject to a floor on the 10th-percentile outcome.
Report expected and pessimistic results.
**Why:** optimising on point estimates rewards whichever line is most over-estimated (the "optimiser's
curse"). Optimising over draws shrinks moves towards lines whose returns are uncertain.
**Alternatives:** point estimates plus sensitivity runs (simpler, but no protection against the curse);
robust worst-case optimisation (too conservative with 12 lines).

## D-007 SQL layer in DuckDB
**Choice:** generated data go to Parquet, and numbered SQL views in DuckDB build the validated metric tables.
The forecasts, the optimiser, the Tableau extracts and the AI commentary all read from those views.
**Why:** the brief requires that the AI workflow uses validated SQL outputs. One SQL layer means every
consumer uses the same definitions (`docs/metric_definitions.md`).

## D-008 (OPEN, phase 7) LLM provider and model
**Plan:** a provider-agnostic interface with a deterministic template fallback, so the pipeline and CI run
without an API key. Provider and model are chosen in phase 7, with current model IDs and costs checked at
that time.

## D-009 Tableau deliverable
**Choice:** the repo produces the dashboard data extracts (CSV/Hyper-ready) and a written dashboard spec:
screens, calculated fields, filters. The workbook itself is built in Tableau Public and linked from the README.
**Why:** a Tableau workbook is built in a GUI. A spec plus extracts keeps the data reproducible.

## D-010 Brand-search floor kept, then tested
**Choice:** keep a 50% floor on B1 brand search in the base case (defending against competitor bidding on
the brand name). Phase 4 reports what the floor costs; phase 3 designs a brand-search holdout to measure it.
**Why:** the floor is a common management belief that may cost money. The analysis should show that cost,
not quietly remove a policy management chose.
**Phase 3 result:** the brand-search holdout found a real effect (−9% of B1 customers in the held-out
regions, 95% range −18% to −0.2%). Switching brand search off is roughly break-even (−$161k to +$167k a
year). The evidence does not justify removing it, so the floor stays in the base case; phase 5 shows its
cost.

## D-011 B3 payback target: 9 months instead of 6
**Choice:** set B3's payback ceiling to 9 months.
**Why:** at last year's channel mix B3 pays back in about 13 months, so a 6-month ceiling could not be met
by any allocation. Retargeting and affiliates raise B3's average CAC without adding many customers. 9 months
is achievable only by moving money out of them, so the constraint still bites.
**Status:** accepted by the project owner on 2026-10-31, acting as the CFO. The 6-month case is kept as a phase 5
sensitivity run to show what meeting it would take.

## D-012 Three levels of attribution: platform, last click, incremental
**Choice:** the simulation has three distinct views of a channel's customers.
1. **Platform-reported:** last click × an over-claim factor for view-through and multi-touch credit.
2. **CRM last click:** includes organic customers whose last click was the channel.
3. **Incremental:** only customers the advertising caused.

The analysis judges channels on CRM numbers, never on platform numbers, and treats even CRM numbers as
non-causal.
**Why:** a real multi-channel advertiser faces exactly this, and the brief asks for attribution and
causation to be told apart. With only two levels, the platform-vs-CRM reconciliation, which is the Data
Engineer's main concern, would not exist.
**Alternatives:** platform = CRM (unrealistic; this was the first generator version and was changed during
phase 1); a multi-touch attribution model (adds a fourth number without adding causal evidence).

## D-013 Retention estimated with censoring, not from finished lifetimes
**Choice:** first-month survival as a share of customers observable in month 1, and a constant later
monthly hazard as churn events ÷ observed month-to-month transitions (censored-geometric MLE). B3 repeat
orders come from a Poisson GLM with an offset for observable customers and quasi-likelihood standard errors.
**Why:** a third of customers were acquired in the last year and are still active. Dropping them, or
counting only finished lifetimes, understates retention. Treating them as churned understates it further.
**Checked by:** cohorts observed for the full 24 months (no model needed). Their realised value is within 1%
of the model value for all three businesses (`reports/customer_value.md`).
**Limit:** a constant hazard after month 1. A Kaplan–Meier curve by month would relax this. The
full-horizon check does not suggest it is needed.

## D-014 Attribution-change detector: one change point on the platform/CRM ratio
**Choice:** for each line, find the single split of log(platform ÷ CRM conversions) that minimises squared
error. The search runs on 4-week sums, then refines to the week. A line is flagged only if the difference is
significant after a Bonferroni correction across the 12 lines *and* the ratio moves by more than 15%.
**Why:** a tracking change shifts the ratio between two systems that measure the same customers, while a
genuine performance change moves both. Searching for the best split inflates significance, so the
minimum-size rule guards against flagging noise on the small-count B2 lines.
**Alternatives:** CUSUM or Bayesian change-point methods (handle several changes, but are harder to explain
to the Data Engineer); comparing platform conversions with spend (cannot tell a tracking change from a real
one).

## D-015 Flagged rows are kept, not deleted
**Choice:** data-quality flags are columns in `line_week` (`tracking_outage`, `cost_restated`,
`attribution_changed`, `any_dq_flag`). Each later step decides what to exclude and says so.
**Why:** the right treatment depends on the use. A forecast of spend needs outage weeks (spend was real); a
model of platform conversions does not.

## D-016 An inherited customer base before the data window
**Choice:** the generator also creates customers acquired in the five years before the data (at the first
year's acquisition rate). Only those still active inside the window appear, and only through that activity.
Retention estimates exclude them, because their early months are unobserved (left-truncated). The weekly P&L
includes them.
**Why:** an acquired business comes with customers. Without them, revenue climbed from zero for two years,
and a revenue forecast would have learned a simulation artefact. Five years, not two, because B2 customers
stay about six years on average; with a two-year base, B2 revenue still grew 34% in a year for no business
reason.
**Alternatives:** model revenue from new cohorts only (not what finance reports); use left-truncated customers
in retention with delayed entry (possible, but nothing gained when in-window cohorts are plentiful).

## D-017 Forecasting design
**Choice:** weekly forecasts per business for spend, clicks, leads, qualified leads, customers, revenue and
contribution profit, 13 weeks ahead. Five models: naive, seasonal naive, Holt-Winters ETS, a seasonal
regression with the spend plan, and gradient boosting on the de-trended series. Testing is rolling-origin:
every 4 weeks from week 104, 10 origins. The selected model is the simplest within 5% (relative) of the best
WAPE. CAC is planned spend ÷ forecast customers, not a forecast of its own.
**Why:**
- *13 weeks* is the budget review cycle.
- *Conditioning on the spend plan* is honest because the plan is known when a forecast is made. A
  regression variant with forecast spend shows what that knowledge is worth.
- *The parsimony rule* avoids picking a complex model for a difference within noise.
- *Ratios forecast directly* behave badly when the denominator is small (B2: about 7 customers a week).

**Result:** the regression wins most series; gradient boosting rarely helps with 104–150 weekly points.
**Reproducibility:** DuckDB sums floating-point columns in parallel, in a varying order, so money totals
differed in the last bits between rebuilds and nudged the forecasts. Money sums are rounded to cents in SQL,
which makes rebuilds byte-identical.
**Alternatives:** SARIMA (similar to ETS here, slower); Prophet (not in the stack); forecasting at line level
(12× the series, much noisier, and not needed for the quarter plan).

## D-018 Prediction intervals and scenarios from backtest errors
**Choice:**
- *Weekly intervals:* the 10th–90th percentiles of log(actual ÷ forecast) from the backtest, by horizon
  bucket (1–4, 5–8, 9–13 weeks). Coverage is checked leaving one origin out.
- *Scenarios:* percentiles of 13-week-*total* errors. Spend is held at plan in every scenario, and CAC
  follows from customers. The 12-month band reuses the quarterly error (an assumption).

**Why:** model-based intervals assume the model is right. Backtest errors include model error, and
quarter-total errors include the week-to-week correlation that weekly intervals ignore.
**Limits:** 10 origins make the 10%/90% scenarios rough. The 80% intervals covered 75% in the leave-one-out
test (slightly narrow).

## D-019 Experiments are designed from data before they run; the world is simulated after
**Choice:** each experiment's size and duration come from historical data and stated business thresholds
(`experiments/design.py`). The simulation then runs the experiment as designed (`synthetic/experiments.py`).
Truth holds only how the world responds; which tests to run, how many regions to hold out and for how long
are analyst choices in `config.yaml`.
**Why:** this is how experiments work in practice, and it keeps design honest. A test sized after seeing its
result is not a test.
**Region tests:** each is sized to detect half of what the ad platform claims the channel does. The design
picks the cheapest holdout share and duration (25% or 50% of regions; 8, 12 or 16 weeks) that achieves this.
When none does, it uses the most sensitive design and flags it. Sensitivity comes from an A/A rehearsal on
the 8 pre-period weeks.
**Consequence:** three of the four region tests could not reach their target sensitivity. With about 470
customers a week per business, 40 regions and 16 weeks, effects below about 8% of customers cannot be
reliably detected. That is a finding about the business, not a flaw to hide.

## D-020 Region-test analysis: ANCOVA, t intervals, randomisation inference
**Choice:** region-level test-period customers ~ treated + pre-period customers, with HC2 robust standard
errors, t critical values (df = regions − 3) and randomisation-inference p-values (2,000 re-assignments
within the same blocks).
**Why:** the pre-period absorbs persistent region differences (as CUPED does at user level). With 40 regions
normal critical values gave 87–90% coverage in a 40-run check, and t values bring it to about 95%.
Randomisation inference needs no distributional assumption.
**Checked by:** each region test re-run 40 times with fresh random draws. Bias is within 1.4 standard errors
and coverage 90–97.5% (`reports/experiments.md`).
**Alternatives:** difference-in-differences (equivalent here, less efficient); synthetic control (for few
regions; unnecessary with 40); a Bayesian structural time series (not in the stack).

## D-021 Statistical vs practical significance: compare the interval with a business threshold
**Choice:** each result's 95% interval is compared with the smallest effect worth having:
- the break-even uplift for the landing page (build cost ÷ a year of conversion value: 0.8%);
- any gain for the free creative switch;
- 15% for the audience switch.

The decisions are adopt / reject / real but maybe too small / no worthwhile effect / inconclusive. Rollout
decisions are then taken on annual contribution, with a cautious–optimistic range.
**Why:** "p < 0.05" alone says nothing about whether a change is worth making. A 5% *design* threshold (what
the test can detect) is not the same as the *decision* threshold (what pays): the first draft used 5% for
both, which would have wrongly called a +6.6% (CI +2.9% to +10.5%) page change "possibly too small".
