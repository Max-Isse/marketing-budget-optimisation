# Phase plan

Each phase ends with tests green, lint clean, and a summary: what was built, key results, assumptions and open
questions. Every report opens with the six-part business summary (see `CLAUDE.md`). Status is updated at the
end of each phase.

| Phase | Scope | Main outputs | Brief | Status |
|---|---|---|---|---|
| 0 | Scope, business case, metric definitions, design of the simulated world, sealed ground truth, budget-policy feasibility check | `docs/`, `configs/`, `reports/ground_truth_summary_SYNTHETIC.md` | — | done |
| 1 | Generator (weekly media, funnel, customer cohorts, injected data problems) → Parquet → DuckDB SQL views; data-quality checks that must find every injected issue; retention estimated from cohorts; lineage with row counts | `synthetic/`, `sql/`, `reports/data_quality.md`, `reports/customer_value.md`, `docs/data_lineage.md` | WS1 inputs | done |
| 2 | Forecasts of spend, clicks, leads, qualified leads, customers, revenue, CAC and contribution. Compares naive, seasonal naive, ETS/SARIMAX, regression with seasonality and media, and gradient boosting. Rolling-origin validation; MAE, RMSE, WAPE, bias; prediction intervals; optimistic, baseline and pessimistic scenarios | `forecasting/`, `reports/forecasting.md` | WS1 | |
| 3 | Experiment framework: power and sample-size calculator, design of the five experiments, analysis (uplift, confidence intervals, significance vs practical significance, incremental customers and profit), CUPED where it helps, geo-holdout analysis. Correlation vs attribution vs causation, with an evidence label on every result | `experiments/`, `reports/experiments.md` | WS2 | |
| 4 | Response curves per line (adstock + Hill) fitted on history, calibrated to experiment results, with bootstrap uncertainty. Constrained optimiser over curve draws (D-006). Historical roll-forward vs optimised allocation; cost of each policy constraint (shadow prices); scored against the ground truth | `optimisation/`, `validation/`, `reports/optimisation.md` | WS3 | |
| 5 | Sensitivity and scenarios: horizon, discount rate, curve misspecification, experiment results at their confidence limits, payback and volume floors, brand-search floor, ±budget. How the recommendation changes and which assumptions matter | `reports/sensitivity.md` | WS3 | |
| 6 | Tableau: dashboard extracts from the SQL layer, dashboard spec (screens, calculated fields, filters), built and published in Tableau Public | `dashboard/`, `docs/dashboard_spec.md` | Deliverable 5 | |
| 7 | AI-assisted reporting: validated KPI deltas → anomaly flags → a first-draft commentary limited to source-cited metrics → automatic checks (every number traced, no causal wording on non-causal metrics) → questions for investigation → human sign-off record | `reporting_ai/`, `reports/ai_commentary_example.md` | WS6 | |
| 8 | Stakeholder simulation: requirements matrix, common metric framework, agenda, briefing per stakeholder, objections and responses, reconciled recommendation, how to communicate uncertainty | `reports/stakeholder_simulation.md` | WS5 | |
| 9 | Technical report, executive decision memo, model card, monitoring plan, limitations, final README, one-command reproducibility check | `reports/technical_report.md`, `reports/executive_memo.md`, `docs/model_card.md` | WS4 | |

## Repository layout

```
configs/config.yaml                    finance assumptions, budget policies, paths, seeds
configs/ground_truth_SYNTHETIC.yaml    the simulated world (sealed: generator and validation only)
data/raw/                              generated Parquet (git-ignored, rebuilt by `mbo generate`)
data/processed/                        DuckDB database (git-ignored)
sql/                                   numbered SQL views: the validated metric layer
src/marketing_budget/
  curves.py economics.py constraints.py   shared maths: response curves, customer value, budget bounds
  synthetic/                           generator and ground truth
  validation/                          scores models against the truth (phase 4)
  forecasting/ experiments/ optimisation/ reporting_ai/   (phases 2-7)
  reporting/                           generated Markdown reports
tests/                                 pytest; includes the ground-truth isolation test
docs/                                  business case, metrics, data design, decisions, lineage, model card
reports/                               generated reports, tables and figures
```
