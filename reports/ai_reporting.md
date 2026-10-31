# AI-assisted reporting workflow (SYNTHETIC data)

## Summary for management

1. **Business question.** Can a language model take the first pass at the monthly performance commentary
   without inventing numbers or claiming causes the evidence does not support?
2. **Why it matters.** Analysts spend hours each month turning dashboards into words, and a fluent but wrong
   sentence in a board pack is worse than none. Speed only helps if every claim can be traced and trusted.
3. **What this establishes.** The workflow builds a fact sheet of 74 numbered facts from the
   validated SQL layer; 1 is flagged as unusual by a statistical test, not by the model.
   The model drafts from those facts only, and code checks every sentence before anyone reads it:
   - every number matches a cited fact;
   - no metric the facts do not contain;
   - no causal wording without a randomised test behind it;
   - every sentence cites its sources.

   A failed draft gets one retry with its errors listed. After that a plain template is used, so the process
   never stalls. This run used: **template**.
4. **In business terms.** The model writes the prose; the numbers, the "unusual" flags and the rules stay with
   code; a named person signs off. The red-team test below shows the checker catching each kind of error.
5. **Action to consider.** Use the draft as a first pass for the monthly pack, with sign-off as a required
   step. Review the analyst questions at the monthly meeting.
6. **Assumptions and limits.**
   - The checker verifies numbers and wording, not judgement: a draft can be accurate and still emphasise the
     wrong things. That is what the reviewer is for.
   - "Unusual" means far from this series' own history, which is not the same as important.
   - Calling the API sends the fact sheet (synthetic here) to Anthropic.

## How it works

| Step | Done by | Output |
|---|---|---|
| 1. 4-week totals per business and channel | SQL (`sql/08_kpi_windows.sql`) | `kpi_windows` |
| 2. Fact sheet: values, changes, evidence type, data-quality notes; experiment and plan findings | Python | `reports/tables/ai_fact_sheet.csv` |
| 3. Unusual movements: 4-week change vs that series' own history, robust z ≥ 3.0 | Python | `unusual`, `robust_z` |
| 4. Draft: headline, paragraphs, questions; every sentence lists its fact IDs | Claude (claude-opus-5-5, structured JSON output) or template | draft JSON |
| 5. Checks: citations, numbers, causal wording, metric vocabulary | Python (`reporting_ai/validate.py`) | findings; retry once, then template |
| 6. Human sign-off, tied to the exact draft text | Named reviewer (`mbo review`) | `reports/ai_commentary_reviews.json` |
| 7. Audit: fact-sheet hash, attempts, findings, the draft | Python | `artifacts/ai_commentary_audit.json` |

The model never sees raw tables, never computes a number, and its output is data until it passes the checks.

## This run

Period: the 4 weeks from 28 Sep 2026 to 25 Oct 2026. Draft source: template. Findings on the final draft: 0.
Draft: `reports/ai_commentary_draft.md`.

| attempt   | outcome         |
|:----------|:----------------|
| none      | LLM not enabled |

## Red team: does the checker catch what it should?

| case                                          | sentence                                           | cited                              | checker                                                                                                                                    |
|:----------------------------------------------|:---------------------------------------------------|:-----------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------|
| invented number                               | B1 Hearth Box won 9,999 new customers.             | B1.customers                       | number: 9999 (count) is not a quantity of the cited facts                                                                                  |
| invented metric                               | B1 Hearth Box ROAS improved to 4.2x.               | B1.customers                       | number: 4.2 (ratio) is not a quantity of the cited facts; metric: names a metric (\bROAS\b|return on ad spend) that no cited fact is about |
| causal claim from attribution                 | B1 affiliates drove the change in customers.       | B1.affiliates.last_click_customers | causal language: 'drove' needs a causal (randomised-test) fact                                                                             |
| no citation                                   | Performance was strong across the board.           | (none)                             | citation: no fact cited                                                                                                                    |
| unknown fact ID                               | B1 Hearth Box grew.                                | B9.customers                       | citation: unknown fact IDs: B9.customers                                                                                                   |
| causal claim from a randomised test (allowed) | The new landing page caused the conversion change. | EXP.landing_page                   | passes                                                                                                                                     |

## Unusual movements this period

| fact_id                      | metric_label   |   change_vs_previous |   robust_z | dq_note   |
|:-----------------------------|:---------------|---------------------:|-----------:|:----------|
| B3.affiliates.last_click_cac | last-click CAC |                0.725 |       3.53 |           |
