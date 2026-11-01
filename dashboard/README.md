# Executive dashboard

Tableau Public workbook, built from the CSVs in this folder. **All data are SYNTHETIC** (see the root README).

| File | What it is |
|---|---|
| `data/synthetic_*.csv` | 13 extracts, one or more per dashboard page (rebuilt by `uv run mbo dashboard`) |
| `data_dictionary.csv` | Every field of every extract, with its type and row count |
| `tieout.csv` | The number each headline tile must show, with the Tableau formula: use it to QA the workbook |
| `marketing_budget.twb` | The workbook: six dashboards built to the spec |
| `extracts/*.hyper` | The extracts the workbook reads (Tableau Public requires extracts) |

The build specification (pages, layout, fields, calculated fields, colours, QA checklist) is
[docs/dashboard_spec.md](../docs/dashboard_spec.md). The column names are a contract enforced by
`tests/test_dashboard.py`.

**Published workbook:** [https://public.tableau.com/app/profile/mohamed.isse7985/viz/marketing_budget/1Executivesummary](https://public.tableau.com/app/profile/mohamed.isse7985/viz/marketing_budget/1Executivesummary)

To refresh after a pipeline re-run: open `marketing_budget.twb` in Tableau Public, use **Data → Refresh** on each
source, check the headline figures against `tieout.csv`, then save to Tableau Public under the same name.
