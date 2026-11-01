# Model card: marketing-mix model and budget optimiser

> **The data are simulated (SYNTHETIC).** The company, its three businesses and every figure below come from
> a simulation built for this project, because only a simulation reveals each channel's true effect and so
> lets the method be checked. The figures show what the method recommends and how; they are not facts
> about a real company.

## Model details

- **What it is.** One marketing-mix model per business (weekly new customers = organic base × (1 + paid lift),
  with adstock and Hill saturation per channel), calibrated to 3 region budget tests, with
  200 bootstrap refits. A constrained optimiser (SLSQP) chooses the split across the
  12 lines. Code: `src/marketing_budget/optimisation/`.
- **Owner.** Analytics. **Inputs owned by** Finance (margins, payback targets, budget), Sales (B2 capacity),
  Marketing (channel limits). All in `configs/config.yaml`.
- **Version.** Rebuilt from seed 20261031; outputs pinned by `reports/manifest.csv`.

## Intended use

- Deciding the annual split of a fixed paid-acquisition budget across channels and businesses.
- Ranking where the next test should go (the money at stake on each uncertain line).
- Comparing plans by their *difference* in expected contribution.

## Not intended for

- Reporting what a channel "achieved" (use randomised tests).
- Weekly bidding or seasonal timing (the model sets annual totals).
- Quoting absolute profit (the level is overstated; differences are more reliable).
- Lines or businesses outside the training data, or spend far outside the range seen (more than about
  25% from last year on lines without a test).

## Training data

156 weeks of weekly spend and CRM customers per line (SYNTHETIC), CRM organic-source customers for the
organic floor, and 3 region tests for calibration. Customer values from the retention models.

## Evaluation

- **Calibration:** 3 of 3 measured test effects fall inside the model's 10-90% range.
- **Robustness:** 6 of 12 line directions hold in all 21 alternative scenarios.
- **Plan:** expected gain +$437k a year vs last year's split; worst-10% average +$409k.

**Against the simulation's truth** ([technical report, section 9](../reports/technical_report.md#9-validation-against-the-simulations-truth)):
- the plan truly gains +$268k a year vs the model's +$437k (58% of what is achievable);
- 7 of 12 next-dollar estimates fall inside the model's 80% band; on untested lines the
  estimate is 0.3x to 2.2x the truth;
- all 6 no-regret directions are right; 3 of 5 "mostly" directions are.

## Limitations and risks

- History-only response curves lean optimistic and their uncertainty bands are too narrow.
- Switch-off tests fix a channel's average effect, not the slope at today's spend.
- No channel interactions, no seasonal timing, no competitor response.
- B2 is capped by sales capacity, so B2 curves are only identified up to that cap.
- Mitigations: ±25% guardrail on untested lines, a reserve for unproven increases, a downside
  constraint, and a test plan targeted at the most uncertain money.

## Monitoring

See [monitoring_plan.md](monitoring_plan.md). Refit when a new test reads out, when a monitor fires, or
quarterly, whichever comes first.
