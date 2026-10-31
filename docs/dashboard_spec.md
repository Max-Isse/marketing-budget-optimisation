# Executive dashboard: build specification (Tableau Public)

> **SYNTHETIC data.** Every extract is generated (D-001). Publishing to Tableau Public makes the workbook
> and its data public, which is fine for synthetic data and would not be for a real company's.

The dashboard turns phases 1–5 into six pages, each answering one management question. It is built in
Tableau Public from the CSVs in `dashboard/data/`, produced by `uv run mbo dashboard`. This document
specifies everything needed to build it; `dashboard/tieout.csv` gives the number each headline tile must
show, for QA.

## Design principles

1. **One decision per page.** Each page states its question in the title and the answer in a single sentence
   under it.
2. **Every number shows its evidence type.** Each number is labelled *Causal* (randomised test), *Model*
   (fitted on history), *Attribution* (platform or CRM accounting rule) or *Actual* (recorded). Never show a
   model figure without its range.
3. **Ratios are computed, never summed.** CAC, cost per lead and conversion rates are `SUM()/SUM()` calculated
   fields, so they stay right at any level of aggregation. No extract stores a ratio that the dashboard
   re-aggregates.
4. **Ranges, not points, for anything uncertain.** Forecasts and plan gains show the pessimistic case next to
   the expected one. Uncertainty is shown as part of the answer, not hidden in a footnote.
5. **No ground truth.** The validation tables are deliberately not exported. A real dashboard would not have
   them.

## Data sources and relationships

Connect each CSV as a text file. Use **relationships** (not joins) on the keys shown.

| Extract | Grain | Keys | Used on page |
|---|---|---|---|
| `synthetic_weekly_business.csv` | business × week | week_start, business | 1 |
| `synthetic_weekly_channel.csv` | business-channel line × week | week_start, line | 3, 6 |
| `synthetic_plan_summary.csv` | allocation | allocation | 1, 2 |
| `synthetic_allocation.csv` | line | line | 2 |
| `synthetic_policy_costs.csv` | policy | policy_removed | 2 |
| `synthetic_budget_curve.csv` | budget level | budget | 2 |
| `synthetic_channel_lenses.csv` | line × lens | line, lens | 3 |
| `synthetic_next_tests.csv` | line | line | 3 |
| `synthetic_forecast.csv` | business × target × week × series | week_start, business, target | 4 |
| `synthetic_forecast_scenarios.csv` | business × target × period × scenario | business, target | 4 |
| `synthetic_experiments.csv` | experiment × metric | experiment | 5 |
| `synthetic_dq_issues.csv` | issue | issue, business, channel | 6 |
| `synthetic_attribution_ratio_weekly.csv` | line × week | week_start, line | 6 |

Relate `synthetic_weekly_channel`, `synthetic_allocation`, `synthetic_channel_lenses` and
`synthetic_next_tests` on **line**. Relate the business-level sources on **business**. Field types are listed
in `dashboard/data_dictionary.csv`; metric definitions are in `docs/metric_definitions.md`.

## Global settings

- **Size:** fixed 1366 × 768. Each page is one dashboard; navigation uses buttons across the top.
- **Filters** (one row above the charts, applied to all pages that share the source):
  - **Business:** multi-select. Show names (`business_name`), not codes.
  - **Date range** (pages 1, 3, 6): relative date filter on `week_start`, default last 52 weeks.
- **Parameter `Lens`** (page 3): All (default) / Platform-reported / CRM last click / Randomised test / Model: next dollar. The values must match `[Lens label]`.
- **Parameter `Target`** (page 4): customers (default) / revenue / contribution_profit / spend.
- **Number formats:** money in $k with no decimals ($1,234k); CAC in $ with no decimals; rates as % with one
  decimal; customer counts with thousands separators.
- **Banner:** a thin grey bar on every page reading "Synthetic data: methods demonstration, not company
  results".

### Colours (validated palette)

Validated with the dataviz palette checker. Business colours pass every check, all pairs. Aqua and yellow fall
below 3:1 contrast on the light background, so every aqua or yellow mark carries a **visible value label**, and
each page has a table view (see Accessibility).

| Use | Value | Hex |
|---|---|---|
| Business (fixed by entity, never by rank) | B1 Hearth Box | `#2a78d6` |
| | B2 Ledgerline | `#eb6834` |
| | B3 Atlas Outdoor | `#1baf7a` |
| Lens (page 3) | 1 Platform-reported | `#2a78d6` |
| | 2 CRM last click | `#eb6834` |
| | 3 Randomised test | `#1baf7a` |
| | 4 Model: next dollar | `#eda100` |
| Series (pages 2, 4) | Last year / actual | `#2a78d6` |
| | Recommended / forecast | `#eb6834` |
| Verdict (page 2) | increase | `#2a78d6` with ▲ |
| | cut | `#eb6834` with ▼ |
| | depends on assumptions | `#8a8984` with ◆ |
| Ink | primary text / secondary text / gridlines / background | `#0b0b0b` / `#52514e` / `#e4e3df` / `#fcfcfb` |

**Evidence** is shown by shape fill: filled = experiment-backed, hollow = history only. It is never shown by
colour alone.

## Calculated fields

```
// Ratios: always SUM()/SUM()
[Blended CAC]              = SUM([spend]) / SUM([customers])
[Last-click CAC]           = SUM([spend]) / SUM([crm_customers])
[Platform CAC]             = SUM([spend]) / SUM([platform_conversions])
[Cost per lead]            = SUM([spend]) / SUM([crm_leads])
[Lead to qualified rate]   = SUM([crm_qualified_leads]) / SUM([crm_leads])
[Platform / CRM ratio]     = SUM([platform_conversions]) / SUM([crm_customers])

// Plan (synthetic_plan_summary)
[Plan gain]          = { FIXED : SUM(IF [allocation] = "recommended" THEN [expected_profit] END) }
                     - { FIXED : SUM(IF [allocation] = "status_quo" THEN [expected_profit] END) }
[Plan downside gain] = { FIXED : SUM(IF [allocation] = "recommended" THEN [downside_profit] END) }
                     - { FIXED : SUM(IF [allocation] = "status_quo" THEN [downside_profit] END) }

// Allocation (synthetic_allocation)
[Change %]           = SUM([change]) / SUM([last_year_split])
[Verdict group]      = IF CONTAINS([verdict], "increase") THEN "increase"
                       ELSEIF CONTAINS([verdict], "cut") THEN "cut" ELSE "depends on assumptions" END
[Evidence fill]      = IF [evidence] = "experiment" THEN "Experiment-backed" ELSE "History only" END
[Next dollar pays?]  = IF [marginal_return_recommended] >= 1 THEN "pays back" ELSE "does not pay back" END

// Lenses (synthetic_channel_lenses)
[Lens selected]      = [Lens label] = [Lens] OR [Lens] = "All"
[Lens label]         = MID([lens], 3)                      // drop the sort prefix "1 "

// Forecast (synthetic_forecast)
[Is forecast]        = [series] = "forecast"
[Range low]          = IF [Is forecast] THEN [low] END
[Range high]         = IF [Is forecast] THEN [high] END

// Experiments (synthetic_experiments)
[Effect %]           = [relative_effect]
[Significant?]       = IF [ci_low] > 0 OR [ci_high] < 0 THEN "range excludes zero" ELSE "range includes zero" END
```

## Page 1: Executive summary

**Question:** How is paid acquisition performing, and what is the plan worth?
**Answer line (text):** "The recommended split is expected to add [Plan gain] a year (pessimistic case
[Plan downside gain]). Model estimate: see page 2."

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [Business ▼]  [Date range ▼]                         synthetic-data banner   │
├────────────┬────────────┬────────────┬────────────┬──────────────────────────┤
│ Ad spend   │ New        │ Blended    │ Contrib.   │ Plan gain (model)        │
│ $k  Actual │ customers  │ CAC  Actual│ profit     │ $437k  (pessimistic …)   │
├────────────┴────────────┴────────────┴────────────┴──────────────────────────┤
│ Weekly new customers by business (line, 3 colours)                           │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ Weekly contribution profit (area)    │ Blended CAC by business (bar + label) │
└──────────────────────────────────────┴───────────────────────────────────────┘
```

| Sheet | Source | Columns / rows | Marks |
|---|---|---|---|
| KPI tiles (×4) | weekly_business | Text: SUM(spend), SUM(customers), [Blended CAC], SUM(contribution_profit) | Text; caption "Actual, last 52 weeks" |
| Plan tile | plan_summary | Text: [Plan gain], [Plan downside gain] | Text; caption "Model, see page 2" |
| Weekly customers | weekly_business | Columns WEEK(week_start); Rows SUM(customers) | Line 2px, colour business; direct labels at line end |
| Contribution profit | weekly_business | Columns WEEK(week_start); Rows SUM(contribution_profit) | Area, colour business |
| Blended CAC | weekly_business | Rows business_name; Columns [Blended CAC] | Bar ≤ 24px, value label |

**Tooltip (all sheets):** value first, then label, then evidence type, for example "$38.68 · Blended CAC ·
Actual".

## Page 2: Budget plan

**Question:** Where should next year's $2M go?
**Answer line:** "Move [SUM change>0] between channels: cut retargeting and B2, add B3 social and B1 generic
search. Experiment-backed moves in full; history-only moves capped at ±25%."

```
┌───────────────────────────────────────────────┬──────────────────────────────┐
│ Dumbbell: last year's split → recommended,    │ Business totals (bar pairs)  │
│ one row per line, sorted by change;           │                              │
│ marker shape = verdict, fill = evidence       ├──────────────────────────────┤
│                                               │ What each policy costs       │
│                                               │ (bar, sorted; label in $k)   │
├───────────────────────────────────────────────┼──────────────────────────────┤
│ Budget curve: expected profit vs budget,      │ Plan summary table           │
│ band = pessimistic to optimistic              │ (5 allocations × 3 metrics)  │
└───────────────────────────────────────────────┴──────────────────────────────┘
```

| Sheet | Source | Specification |
|---|---|---|
| Dumbbell | allocation | Rows line_label (sort by SUM(change)); Columns Measure Values [last_year_split, recommended]; Circle marks 8px coloured by Measure Names (blue / orange); line path in grey `#e4e3df`. Shape on the recommended mark = [Verdict group] (▲▼◆); fill = [Evidence fill]. Tooltip: last year, recommended, change %, verdict, evidence, the range of change across scenarios (lowest to highest), [Next dollar pays?] |
| Business totals | allocation | Rows business_name; Columns SUM(last_year_split), SUM(recommended) side by side; labels in $k |
| Policy costs | policy_costs | Rows policy (sort by expected_profit_gain desc); Columns expected_profit_gain; label $k; caption "What removing each policy would add by the model. Near zero = not binding" |
| Budget curve | budget_curve | Columns budget ($M); Rows expected_profit (line + 6px markers) with a band from downside_profit to p90_profit (dual area on a single axis: two measures, one scale); reference line at $2.0M; annotation at the peak |
| Plan summary | plan_summary | Text table: allocation × expected_profit, downside_profit, incremental_customers |

**Caption under the page:** "Model-based: curves calibrated to three experiments; other lines rest on
history and may be optimistic."

## Page 3: Channel truth: four ways to count a channel's customers

**Question:** What does each channel really deliver, and how far do dashboards overstate it?
**Answer line:** "For retargeting, the platform reports [x] customers per $1,000; a randomised test finds about
[y]. Judge channels on the test and the model, never on platform numbers."

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [Business ▼] [Lens ▼ (All)]                                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Grouped bars: customers per $1,000 by line, one bar per lens (4 colours),    │
│ error bars where a range exists; value label on every bar                     │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ Platform vs last-click CAC (dot)     │ What to test next (table, sorted)     │
└──────────────────────────────────────┴───────────────────────────────────────┘
```

| Sheet | Source | Specification |
|---|---|---|
| Lenses | channel_lenses | Rows line_label; Columns customers_per_1000; Colour [Lens label] (4 slots, fixed order); filter [Lens selected]. Error bars via a Gantt mark from `low` to `high` (size = high − low) on the same axis. **Value label on every bar.** Tooltip includes `evidence` |
| CAC comparison | weekly_channel | Rows line_label; Columns [Platform CAC] and [Last-click CAC] (two dots per row, blue / orange) |
| Next tests | next_tests | Text: line_label, annual_spend, marginal_return (with p10–p90), stake; sorted by stake |

**Explainer text box (always visible):** "Platform = what the ad platform claims. Last click = what our CRM
credits. Randomised test = what switching spend on and off in regions actually changed. Model = what the
next dollar is expected to buy."

## Page 4: Forecast and scenarios

**Question:** What will next quarter bring if we keep last year's pattern, and how far off could that be?

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [Business ▼] [Target ▼ customers | revenue | contribution profit | spend]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Actual (52 weeks) + forecast (52 weeks) line; 80% band on the forecast;      │
│ shading after week 13 = "beyond tested horizon"                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Scenario table: next quarter and next 52 weeks × pessimistic | baseline |     │
│ optimistic                                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Sheet | Source | Specification |
|---|---|---|
| Forecast line | forecast | Columns WEEK(week_start); Rows SUM(value); Colour [series] (actual blue, forecast orange); band from [Range low] to [Range high] (area, 18% opacity). Reference band for rows where `beyond_validated_horizon` is true, labelled "beyond the 13 weeks tested". Filter `target` by parameter |
| Scenarios | forecast_scenarios | Text table: Rows business_name, target; Columns period × scenario. For CAC, pessimistic means *high*: add a note |

**Caption:** "Ranges from 10 backtests; the 80% range covered 75% of actuals in testing, so it is slightly
narrow."

## Page 5: Experiments

**Question:** What did the randomised tests prove, and what should we do about each?

| Sheet | Source | Specification |
|---|---|---|
| Effect plot | experiments | Rows experiment + metric; Columns relative_effect (circle 8px) with a range bar from ci_low to ci_high; reference line at 0; a second reference mark at `threshold` (the smallest effect worth having). Colour by [Significant?] (blue / grey). Tooltip: effect, range, p-value, decision |
| Rollout table | experiments (one row per experiment) | Text: rollout_decision, annual_value_estimate (low–high), rollout_verdict |

**Caption:** "Causal evidence: each change was assigned at random. Yearly values scale the test result and
are assumptions."

## Page 6: Data trust

**Question:** Can these numbers be trusted, and where are they wrong?

| Sheet | Source | Specification |
|---|---|---|
| Issues table | dq_issues | Text: issue, business, channel, first_week, last_week, detail |
| Platform / CRM ratio | attribution_ratio_weekly | Columns WEEK(week_start); Rows [Platform / CRM ratio]; small multiples by line_label (12 panels, shared y-axis); reference line at 1.0; mark weeks where `tracking_outage` or `attribution_changed` is true with a hollow red ring, never colour alone |

**Answer line:** "Five problems found: two tracking outages, a tracking change on B1 social from July 2025,
duplicate B2 leads and a late cost restatement. Platform figures overstate conversions by up to 1.6×."

## Build steps (Tableau Public)

1. Run `uv run mbo dashboard` (after `uv run mbo all`). The CSVs land in `dashboard/data/`.
2. In Tableau Public: Connect → Text file → `synthetic_weekly_business.csv`; add the others and relate them as
   in the table above.
3. Set `week_start` to Date, `business` and `line` to String, and the boolean flags to Boolean.
4. Create the calculated fields and the `Lens` and `Target` parameters.
5. Build the sheets per page, then the six dashboards (1366 × 768) with navigation buttons.
6. Apply the colours by entity (Edit Colours → assign each business and lens its hex).
7. QA against `dashboard/tieout.csv` (below).
8. Save to Tableau Public. Title: "Marketing budget optimisation: executive dashboard (synthetic data)". Link
   the published URL in the README.

## QA checklist

- [ ] Every row of `dashboard/tieout.csv` matches the workbook tile to the displayed precision, with the
      filter shown.
- [ ] Blended CAC by business equals SUM(spend)/SUM(customers), not the average of weekly CACs. Check
      B2 in particular: an average of weekly ratios would be badly wrong at about 7 customers a week.
- [ ] Changing the Business filter changes every page that shares the source, and no others.
- [ ] Every model figure has its range or pessimistic case next to it.
- [ ] Every aqua and yellow mark has a visible value label.
- [ ] The synthetic-data banner is on every page.
- [ ] No sheet uses a validation (`*_SYNTHETIC`) table from `reports/tables`.

## Accessibility

- Identity is never colour-only: shapes (verdict), fill (evidence), labels (lens) and rings (data flags).
- Each page has a "View as table" button (a hidden sheet with the same fields, shown by a show/hide button).
- Alt text on each dashboard object describes the answer line, not the chart type.
- Minimum font size 9 pt; titles 14 pt.

## Refreshing

Re-running the pipeline overwrites the CSVs with the same names and columns. In Tableau, use Data → Refresh,
then re-check the tie-out values. The CSV columns are the contract between the pipeline and the workbook:
`tests/test_dashboard.py` fails if a column is renamed or removed.
