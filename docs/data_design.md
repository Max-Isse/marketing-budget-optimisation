# Data design (SYNTHETIC)

Why the data are simulated is explained in D-001. This document explains how the simulation is built and
why each choice makes the test harder, not easier. Every parameter is in `configs/ground_truth_SYNTHETIC.yaml`,
and `uv run mbo design` writes the resulting world to `reports/ground_truth_summary_SYNTHETIC.md`.

## Structure

- **156 weeks** (3 years) of weekly history, starting Monday 30 October 2023.
- **3 businesses × 4 channels = 12 lines.** Planned spend sums to about $2.0M a year.
- **Tables to be generated in phase 1**, all with `synthetic` in the name:
  - `synthetic_weekly_media`: spend, impressions, clicks, platform-attributed conversions
  - `synthetic_weekly_funnel`: leads, qualified leads, customers by source line, including organic
  - `synthetic_customers` and `synthetic_customer_months`: customer-level cohorts, with activity and
    contribution by month
  - `synthetic_experiment_*`: one table per experiment, at the level the experiment randomises

## How outcomes are generated

For each line and week:

1. **Spend** = planned spend × demand index^0.6 × noise × any scheduled budget shift. Managers partly
   followed demand, so spend and demand are correlated, as they are in real data (confounding).
2. **Adstock** carries part of each week's advertising into later weeks (decay 0.05 to 0.45, longest for
   social and LinkedIn).
3. **Incremental leads** = demand × trend × Hill(adstock). The response curve flattens as spend grows
   (saturation). Social prospecting in B1 and B3 is S-shaped (shape > 1), so it is weak at low spend.
4. **Qualified leads and customers** come from binomial draws using per-line qualification rates and a
   per-business close rate.
5. **Organic customers** arrive regardless of advertising. Platforms claim a share of them
   (`attribution_capture`). This is the gap between attributed and incremental results.
6. **Customer value** comes from simulated customer lifetimes: subscription survival, or e-commerce repeat
   orders. Affiliate customers are worth 15–20% less.

## Features the simulation must contain (asserted by `tests/test_ground_truth_world.py`)

| Feature | Where | Why it matters |
|---|---|---|
| High platform ROAS but low marginal return | B1 brand search, B3 retargeting, both affiliate lines | Tests whether the analysis can tell attribution from causation |
| Under-funded lines (marginal return > 1.2) | B1 generic search and social, B2 LinkedIn and review sites, B3 social | The reallocation opportunity the optimiser should find |
| Cheapest leads, worst value | B2 programmatic display | The BU Director's lead-quality concern |
| Average return below marginal return | B3 social (S-shaped) | Average ROAS can mislead in both directions |
| Spend correlated with demand | All lines (`seasonality_follow: 0.6`) | Naive regression over-credits media; experiments are needed |
| Budget shifts | Three lines, 20–25 weeks each | The only independent variation the history provides |

## Problems the phase 1 data-quality checks must detect

| Injected issue | Line | Effect if missed |
|---|---|---|
| Tracking outage, 2 weeks | B3 retargeting | The channel looks dead for two weeks and attributed CAC jumps |
| Tracking outage, 1 week | B1 generic search | Same, smaller |
| Attribution signal loss from week 90 (30% of conversions lost) | B1 social | The channel appears to decline when nothing changed. This is the Data Engineer's concern |
| 3% duplicate leads | B2 CRM | Lead volume is overstated and qualification rates understated |
| Late cost restatement (+25%) | B2 programmatic, week 130 | That week's CAC is understated in early reports |

## Experiments (true effects, for scoring phase 3)

| Experiment | Business / channel | Randomised at | True effect |
|---|---|---|---|
| Landing page | B1 | Visitor | +6% relative conversion |
| Ad creative | B3 social | User | No effect. Tests whether the analysis avoids a false positive |
| Audience targeting | B2 LinkedIn | Campaign-week | +25% leads but −30% qualification, so fewer qualified leads overall |
| Bidding strategy | B1 generic search | Campaign-week | Platform-reported CPA falls 15%, but incremental conversions fall 5% |
| Budget holdout | B3 retargeting | Region (40 regions, 25% held out) | Measures how little retargeting truly adds |

## What the simulation does not capture

- **Competitors.** Their bids and promotions are only present as random demand shocks.
- **Cross-channel interaction.** In the simulation, social does not raise brand-search volume; in reality it
  often does. The optimiser therefore treats lines as independent, and the report says so.
- **Creative wear-out and auction dynamics within a week.**
- **Customers moving between the three businesses.**
