"""Phase 0 report: what the simulated world looks like at last year's spend, and whether the budget policies
in config can all be met at once."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from marketing_budget.config import Config
from marketing_budget.constraints import Bounds


def _md(df: pd.DataFrame, floatfmt: str = ",.2f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def write_design_report(lines: pd.DataFrame, biz: pd.DataFrame, bounds: Bounds, cfg: Config) -> Path:
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    lines.to_csv(tables / "ground_truth_lines_SYNTHETIC.csv", index=False, float_format="%.6g")
    biz.to_csv(tables / "ground_truth_businesses_SYNTHETIC.csv", index=False, float_format="%.6g")
    bounds.lines.to_csv(tables / "budget_bounds_planned_SYNTHETIC.csv", index=False, float_format="%.6g")

    total_spend = float(biz["annual_spend"].sum())
    total_net = float(biz["annual_net_contribution"].sum())
    trap = lines[(lines["attributed_return"] > 1.2) & (lines["marginal_return"] < 0.6)]
    headroom = lines[lines["marginal_return"] > 1.2]
    cheap_poor = lines.loc[lines.groupby("business")["cost_per_lead"].idxmin()]
    cheap_poor = cheap_poor[cheap_poor["marginal_return"] < 1]

    show_lines = lines[
        [
            "business",
            "channel",
            "weekly_spend",
            "cost_per_lead",
            "incremental_cac",
            "marginal_cac",
            "attributed_return",
            "incremental_return",
            "marginal_return",
        ]
    ]
    show_biz = biz[
        [
            "business",
            "name",
            "model",
            "annual_spend",
            "customer_value_24m",
            "incremental_cac",
            "payback_months",
            "qualified_leads_per_week",
            "annual_net_contribution",
        ]
    ]
    feas = (
        "All budget policies can be met at the same time."
        if bounds.feasible
        else "**The budget policies contradict each other:**\n\n" + "\n".join(f"- {p}" for p in bounds.problems)
    )

    text = f"""# Simulated world at last year's spend (SYNTHETIC ground truth)

> **This is a design check, not a finding.** It describes the simulated company that later phases analyse.
> The models never see these numbers. They have to recover them from the generated data, and phase 4 scores
> them against this table.

## Summary for management

1. **Business question.** Does the simulated company look like a real multi-business advertiser? In
   particular, are its dashboard numbers misleading in the ways real ones are?
2. **Why it matters.** If the simulation were too easy, every method would look good and the project would
   prove nothing. The test only works if some channels look better on the dashboard than they really are.
3. **What this establishes.** Last year's planned spend of ${total_spend:,.0f} generates about
   ${total_net:,.0f} a year of contribution after paying for the advertising. That total hides large
   differences between channels: {len(trap)} channels look strong on platform-reported return but earn
   less than 60 cents per extra dollar, and {len(headroom)} channels earn more than $1.20 per extra dollar
   and are under-funded.
4. **In business terms.** Moving money by dashboard ROAS would move it the wrong way. The analysis has to
   measure what each extra dollar actually buys.
5. **Action to consider.** None yet. This table sets the benchmark the analysis must hit.
6. **Assumptions and limits.** All values are simulation inputs chosen to be plausible (see
   `docs/data_design.md`). The figures assume average demand: no seasonality, trend or noise.

## How to read the returns

All returns are 24-month discounted contribution per advertising dollar. Above 1.0 the spend pays for itself;
below 1.0 it loses money.

- **Attributed return** is what an ad platform or last-click dashboard reports. It includes customers who
  would have bought anyway.
- **Incremental return** counts only the customers the advertising caused, averaged over all spend on the line.
- **Marginal return** is what the *next* dollar earns. This is the number a budget decision needs. Because
  returns diminish as spend grows, it is usually lower than the average.

## Businesses

{_md(show_biz)}

## Business-channel lines (weekly spend, average demand)

{_md(show_lines)}

### Dashboard traps (attributed return above 1.2, marginal return below 0.6)

{_md(trap[["business", "channel", "attributed_return", "marginal_return"]])}

### Under-funded lines (marginal return above 1.2)

{_md(headroom[["business", "channel", "incremental_return", "marginal_return"]])}

### Cheapest leads in each business that lose money at the margin

{_md(cheap_poor[["business", "channel", "cost_per_lead", "lead_to_customer", "marginal_return"]])}

## Budget policy feasibility at last year's spend

{feas}

{_md(bounds.business, ",.0f")}
"""
    path = cfg.path("reports_dir") / "ground_truth_summary_SYNTHETIC.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
