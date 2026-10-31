"""Phase 4 report: reports/optimisation.md, tables and one figure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.experiments.results import CHANNEL_NAMES
from marketing_budget.optimisation.optimiser import allocation_table
from marketing_budget.optimisation.plan import Plan

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BEFORE, AFTER = "#2a78d6", "#eb6834"  # validated pair (dataviz reference palette, light mode)
POLICY_NAMES = {
    "untested_guardrail": "+/-25% limit on lines without an experiment",
    "brand_search_floor": "B1 brand-search floor (50% of last year)",
    "channel_limits": "line floors and ceilings (0.25x-2x last year)",
    "business_limits": "business floors and ceilings agreed at acquisition",
    "concentration": "concentration caps (25% per line, 50% per business)",
    "min_acquisition": "keep 90% of each business's customer volume",
    "payback": "payback targets (B1 12, B2 18, B3 9 months)",
    "sales_capacity": "B2 sales capacity (40 qualified leads a week)",
    "downside": "pessimistic case no worse than last year's split",
}


def _md(df: pd.DataFrame, floatfmt: str = ",.0f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def _k(x: object) -> str:
    x = float(x)  # type: ignore[arg-type]
    return f"-${abs(x) / 1e3:,.0f}k" if x < 0 else f"${x / 1e3:,.0f}k"


def _label(line: object) -> str:
    b, ch = str(line).split(".")
    return f"{b} {CHANNEL_NAMES.get(ch, ch)}"


def _figure(tab: pd.DataFrame, cfg: Config) -> Path:
    t = tab.assign(change=tab["recommended"] - tab["status_quo"]).sort_values("change")
    fig, ax = plt.subplots(figsize=(8.5, 5.2), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    y = np.arange(len(t))
    for yi, a, b in zip(y, t["status_quo"] / 1e3, t["recommended"] / 1e3, strict=True):
        ax.plot([a, b], [yi, yi], color=GRID, linewidth=2, zorder=1)
    ax.scatter(
        t["status_quo"] / 1e3,
        y,
        s=64,
        color=BEFORE,
        zorder=2,
        label="Last year's split",
        edgecolor=SURFACE,
        linewidth=2,
    )
    ax.scatter(
        t["recommended"] / 1e3, y, s=64, color=AFTER, zorder=3, label="Recommended", edgecolor=SURFACE, linewidth=2
    )
    ax.set_yticks(y, [_label(x) for x in t["line"]], color=INK_2, fontsize=9)
    ax.set_xlabel("Annual spend ($k)", color=INK_2, fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.set_title("Where the $2M goes: last year's split vs the recommended plan", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="lower right")
    fig.tight_layout()
    path = cfg.path("figures_dir") / "allocation_change.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def write_optimisation_report(plan: Plan, cfg: Config, score: dict[str, Any] | None = None) -> Path:
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    tab = allocation_table(plan.rm, plan.allocations)
    tab.to_csv(tables / "allocation_by_line.csv", index=False, float_format="%.6g")
    plan.evaluation.to_csv(tables / "allocation_evaluation.csv", index=False, float_format="%.6g")
    plan.policy_costs.to_csv(tables / "policy_costs.csv", index=False, float_format="%.6g")
    plan.marginal.to_csv(tables / "marginal_returns.csv", index=False, float_format="%.6g")
    plan.calibration.to_csv(tables / "model_calibration_check.csv", index=False, float_format="%.6g")
    plan.next_tests.to_csv(tables / "next_tests.csv", index=False, float_format="%.6g")
    fig = _figure(tab, cfg)

    ev: dict[Any, dict[Any, Any]] = plan.evaluation.set_index("allocation").to_dict("index")
    sq, rec = ev["status_quo"], ev["recommended"]
    gain = float(rec["expected_profit"] - sq["expected_profit"])
    down_gain = float(rec["downside_profit"] - sq["downside_profit"])
    plat_loss = float(ev["platform_roas"]["expected_profit"] - sq["expected_profit"])
    t = tab.assign(change=tab["recommended"] - tab["status_quo"]).sort_values("change")
    cuts = t[t["change"] < -5000]
    adds = t[t["change"] > 5000].iloc[::-1]
    pc = plan.policy_costs.assign(policy=lambda d: d["policy_removed"].map(POLICY_NAMES))
    pc_sorted = pc.sort_values("expected_profit_gain", ascending=False)
    pcd: dict[Any, dict[Any, Any]] = pc.set_index("policy_removed").to_dict("index")
    cap = float(pcd["sales_capacity"]["expected_profit_gain"])
    guard = float(pcd["untested_guardrail"]["expected_profit_gain"])
    bv = plan.budget_value
    nt = plan.next_tests.head(3)
    m = plan.marginal
    mrec = m[m["allocation"] == "recommended"].set_index(["business", "channel"])
    msq = m[m["allocation"] == "status_quo"].set_index(["business", "channel"])
    mtab = (
        msq[["tested", "annual_spend", "marginal_return", "marginal_p10", "marginal_p90"]]
        .join(mrec[["annual_spend", "marginal_return"]], rsuffix="_recommended")
        .reset_index()
    )
    biz = pd.DataFrame(
        {
            "business": plan.rm.businesses,
            "spend_last_year_split": [sq[f"spend_{b}"] for b in plan.rm.businesses],
            "spend_recommended": [rec[f"spend_{b}"] for b in plan.rm.businesses],
            "customers_last_year_split": [sq[f"incremental_customers_{b}"] for b in plan.rm.businesses],
            "customers_recommended": [rec[f"incremental_customers_{b}"] for b in plan.rm.businesses],
        }
    )
    move_total = float(t.loc[t["change"] > 0, "change"].sum())
    back_next, back_last = 1 + bv["next_dollar"], 1 + bv["last_dollar"]
    step_k = _k(bv["step"])
    if back_last < 1:
        budget_text = (
            f"At the optimum, the last dollar spent brings back ${back_last:.2f} of contribution and an extra dollar "
            f"would bring back ${back_next:.2f}. Cutting the budget by {step_k} would *add* about "
            f"{_k(-bv['last_dollar'] * bv['step'])} a year by the model. With today's policies the plan cannot place the "
            "full $2M profitably, so the question is not more budget but fewer constraints, or a smaller budget."
        )
    elif back_next > 1:
        budget_text = (
            f"An extra dollar would bring back ${back_next:.2f} of contribution: a larger budget would pay, by "
            f"{_k(bv['next_dollar'] * bv['step'])} per extra {step_k}, if the model's curves are right."
        )
    else:
        budget_text = f"The last dollar brings back ${back_last:.2f} and an extra one ${back_next:.2f}: the budget is about right."

    def lines(df: pd.DataFrame) -> str:
        return ", ".join(f"{_label(r.line)} {_k(r.change)}" for r in df.itertuples())

    validation = ""
    if score is not None:
        a = score["allocations"].set_index("allocation")
        rec_t = a.loc["recommended"]
        rcv, rcu = score["recovery"], score["recovery_uncalibrated"]
        score["allocations"].to_csv(tables / "allocation_true_profit_SYNTHETIC.csv", index=False, float_format="%.6g")
        rcv.to_csv(tables / "curve_recovery_SYNTHETIC.csv", index=False, float_format="%.6g")
        validation = f"""
## Validation against the SYNTHETIC ground truth

What each allocation would *really* earn next year, using the simulation's true curves and customer values.
`true_optimum` is the best split achievable under the same policies (it knows the truth, so no guardrail).

{_md(score["allocations"].assign(share_of_achievable_gain=score["allocations"]["share_of_achievable_gain"].map(lambda v: "" if pd.isna(v) else f"{v:.0%}")))}

- The recommended plan really earns **{_k(rec_t["true_gain_vs_status_quo"])}** more than last year's split:
  {rec_t["share_of_achievable_gain"]:.0%} of what perfect knowledge could achieve. The model promised {_k(gain)}.
  It is optimistic, and the gap is the confounding phase 2 measured.
- Following platform ROAS really loses {_k(-a.loc["platform_roas", "true_gain_vs_status_quo"])}.
- Without the guardrail the plan earns {_k(a.loc["recommended_without_guardrail", "true_gain_vs_status_quo"])}
  instead of {_k(rec_t["true_gain_vs_status_quo"])}. The model's promised extra from moving untested lines is not real.
- The uncalibrated model's plan earns {_k(a.loc["uncalibrated_model", "true_gain_vs_status_quo"])}: calibration to the
  experiments is worth {_k(rec_t["true_gain_vs_status_quo"] - a.loc["uncalibrated_model", "true_gain_vs_status_quo"])} a year here.

### Curve recovery at last year's spend (customers per $1,000 from the next dollar)

The true marginal return lies inside the model's 80% band for {int(rcv["true_in_80pct_band"].sum())} of {len(rcv)} lines
(uncalibrated model: {int(rcu["true_in_80pct_band"].sum())} of {len(rcu)}). The bands reflect sampling noise only, not the
confounding that remains in lines no experiment touched. That is why the guardrail exists. For brand search, the
switch-off test pinned down the *average* effect but not the *marginal* one. The next brand test should cut spend
part-way, not switch it off.

{_md(rcv, ",.2f")}
"""

    text = f"""# Budget optimisation (SYNTHETIC data)

## Summary for management

1. **Business question.** How should next year's $2.0M be split across the three businesses and 12
   channels to earn the most long-term contribution, without betting on numbers we cannot trust?
2. **Why it matters.** Last year's split was rolled forward and steered by dashboards. Phases 2 and 3 showed
   that dashboards and history overstate what extra spend achieves, sometimes by a factor of ten.
3. **What this establishes.** The recommended plan moves {_k(move_total)} between channels. The model expects
   **{_k(gain)} more contribution a year** than last year's split, and its pessimistic case is {_k(down_gain)}
   better too. Steering by platform ROAS instead would cost {_k(-plat_loss)} a year by the same model.
   *Evidence: model-based; calibrated to experiments for three lines, the rest from history only.*
4. **In business terms.**
   - Cut: {lines(cuts)}.
   - Add: {lines(adds)}.
   - **B2 has outgrown its sales team.** At last year's spend it would generate more qualified leads than 40 a
     week can absorb, and extra B2 advertising buys leads nobody can call. Removing that limit would be worth
     {_k(cap)} a year by the model. That is the most extra sales capacity could be worth, before its cost.
   - **Is $2M the right budget?** {budget_text}
5. **Action to consider.** Adopt the plan. Lines without an experiment move at most 25% this year; test the
   biggest uncertain lines next ({", ".join(_label(f"{r.business}.{r.channel}") for r in nt.itertuples())}), then
   re-run this model. Decide on B2 sales capacity separately: it limits B2's growth more than its budget does.
6. **Assumptions and limits.**
   - Response curves for lines without an experiment come from history. They lean optimistic and may rank
     channels wrongly; the 25% guardrail limits the damage.
   - A switch-off test fixes a channel's average effect, not its next-dollar effect.
   - Spend is assumed flat across the year (no seasonal timing), and channels are assumed not to boost each
     other.
   - Customer values are phase 1's estimates. Payback limits use the CFO targets (B3 at 9 months, D-011).

![Annual spend by line: last year's split vs recommended]({fig.relative_to(cfg.path("reports_dir")).as_posix()})

## Method

**Response curves.** One marketing-mix model per business, fitted to 156 weeks:
- weekly customers = organic demand (trend and seasonality) × (1 + the lift from each channel);
- each channel's lift = its maximum × adstock ÷ (adstock + half-saturation spend), with adstock carrying part
  of each week's spend into later weeks.

Three things keep it honest:
- **Calibration.** It must reproduce what the phase 3 budget tests measured, weighted by their precision.
- **Over-dispersion correction.** Weekly counts vary several times more than a simple count model assumes, so
  the history's weight is divided by that factor. Without this, 156 weeks would drown out the experiments.
- **An organic floor.** Organic demand is at least the customers who arrive with no paid last click.

**Uncertainty.** {plan.extras["n_draws"]} refits, each with random weights on the weeks and test results redrawn
within their error. The optimiser sees all of them.

**Optimiser.** It maximises expected annual contribution (customers the business can serve × 24-month value
− spend), subject to every policy in the table below. The plan's average across the worst 10% of draws must
be no worse than last year's split.

### Does the model reproduce the experiments it was calibrated to?

{_md(plan.calibration, ",.3f")}

## The allocations compared

{_md(tab)}

Model view of each allocation (expected and pessimistic are annual incremental contribution after spend;
pessimistic = average of the worst 10% of curve draws):

{_md(plan.evaluation)}

By business:

{_md(biz)}

## Where the next dollar works hardest

Contribution per extra dollar (above 1.0 the next dollar pays for itself), with the model's 80% range. At the
optimum, the returns of unconstrained lines converge. Lines held at a floor, ceiling or guardrail do not.

{_md(mtab, ",.2f")}

## What each policy costs

Each policy removed in turn, the plan re-optimised: the gain in expected contribution is what keeping the
policy costs. A cost near zero means the policy does not bind.

{_md(pc_sorted[["policy", "solved", "expected_profit_gain", "downside_profit_change"]])}

The guardrail "costs" {_k(guard)} by the model's reckoning. That figure is only as good as the model's view of
untested lines.

## What to test next

Untested lines ranked by spend at stake × the width of the model's uncertainty about the next dollar's return:

{_md(plan.next_tests, ",.2f")}
{validation}"""
    path = cfg.path("reports_dir") / "optimisation.md"
    path.write_text(text, encoding="utf-8")
    return path
