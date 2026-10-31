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
**Why:** the floor is a common management belief that, in this simulated world, costs money. The analysis
should show that cost, not quietly remove a policy management chose.

## D-011 B3 payback target: 9 months instead of 6
**Choice:** set B3's payback ceiling to 9 months.
**Why:** at last year's channel mix B3 pays back in about 13 months, so a 6-month ceiling could not be met
by any allocation. Retargeting and affiliates raise B3's average CAC without adding many customers. 9 months
is achievable only by moving money out of them, so the constraint still bites.
**Needs confirmation:** this changes a CFO policy. The 6-month case is kept as a phase 5 sensitivity run, to
show what it would take to meet it.
