"""Phase 5 report: reports/sensitivity.md, tables and two figures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.reporting.optimisation import _label

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
MODEL, TRUE = "#2a78d6", "#eb6834"  # validated pair (dataviz reference palette, light mode)


def _md(df: pd.DataFrame, floatfmt: str = ",.0f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def _k(x: object) -> str:
    v = float(x)  # type: ignore[arg-type]
    return f"-${abs(v) / 1e3:,.0f}k" if v < 0 else f"${v / 1e3:,.0f}k"


def _style(ax: Any) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.set_axisbelow(True)


def _budget_figure(curve: pd.DataFrame, true_curve: pd.DataFrame | None, cfg: Config) -> Path:
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    _style(ax)
    c = curve[curve["solved"]]
    x = c["budget"] / 1e6
    ax.fill_between(x, c["downside_profit"] / 1e6, c["p90_profit"] / 1e6, color=MODEL, alpha=0.15, linewidth=0)
    ax.plot(x, c["expected_profit"] / 1e6, color=MODEL, linewidth=2, marker="o", markersize=6, label="Model: expected")
    if true_curve is not None:
        t = true_curve.dropna(subset=["true_profit_of_model_plan"])
        ax.plot(
            t["budget"] / 1e6,
            t["true_profit_of_model_plan"] / 1e6,
            color=TRUE,
            linewidth=2,
            marker="o",
            markersize=6,
            label="Truth: what the plan really earns",
        )
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_xlabel("Annual budget ($M)", color=INK_2, fontsize=9)
    ax.set_ylabel("Contribution after ad spend ($M a year)", color=INK_2, fontsize=9)
    ax.set_title(
        "Is $2M the right budget? Profit of the optimised plan at each budget", loc="left", color=INK, fontsize=11
    )
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="lower center")
    fig.tight_layout()
    path = cfg.path("figures_dir") / "budget_curve.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def _scenario_figure(tab: pd.DataFrame, cfg: Config) -> Path:
    has_true = "true_gain" in tab
    t = tab.sort_values("true_gain" if has_true else "gain_own_assumptions")
    fig, ax = plt.subplots(figsize=(8.5, 6.4), facecolor=SURFACE)
    _style(ax)
    y = np.arange(len(t))
    ax.scatter(
        t["gain_own_assumptions"] / 1e3,
        y,
        s=56,
        color=MODEL,
        edgecolor=SURFACE,
        linewidth=2,
        zorder=3,
        label="Model's promise (its own assumptions)",
    )
    if has_true:
        ax.scatter(
            t["true_gain"] / 1e3,
            y,
            s=56,
            color=TRUE,
            edgecolor=SURFACE,
            linewidth=2,
            zorder=3,
            label="What it really earns (truth)",
        )
        for yi, a, b in zip(y, t["gain_own_assumptions"] / 1e3, t["true_gain"] / 1e3, strict=True):
            ax.plot([a, b], [yi, yi], color=GRID, linewidth=2, zorder=1)
    ax.set_yticks(y, t["scenario"].str.replace("_", " "), color=INK_2, fontsize=8.5)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.axvline(0, color=INK_2, linewidth=0.8)
    ax.set_xlabel("Gain over last year's split ($k a year)", color=INK_2, fontsize=9)
    ax.set_title("Each scenario's plan: promised vs real gain", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2)
    fig.tight_layout()
    path = cfg.path("figures_dir") / "scenario_gains.png"
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def write_sensitivity_report(
    summary: pd.DataFrame,
    verdicts: pd.DataFrame,
    curve: pd.DataFrame,
    cfg: Config,
    score: dict[str, pd.DataFrame] | None = None,
) -> Path:
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    summary.to_csv(tables / "sensitivity_scenarios.csv", index=False, float_format="%.6g")
    verdicts.to_csv(tables / "sensitivity_line_verdicts.csv", index=False, float_format="%.6g")
    curve.to_csv(tables / "sensitivity_budget_curve.csv", index=False, float_format="%.6g")
    tab = summary.merge(score["scenarios"], on="scenario") if score else summary
    f_budget = _budget_figure(curve, score["budget_curve"] if score else None, cfg)
    f_scen = _scenario_figure(tab, cfg)
    rel = cfg.path("reports_dir")

    others = summary[summary["scenario"] != "base"]
    moved = others.sort_values("share_of_budget_moved_vs_base", ascending=False).head(3)
    moved_text = ", ".join(
        f"{str(n).replace('_', ' ')} ({float(m):.0%})"
        for n, m in zip(moved["scenario"], moved["share_of_budget_moved_vs_base"], strict=True)
    )
    by_group = others.groupby("group")["share_of_budget_moved_vs_base"].mean()

    def names(verdict: str, evidence: str) -> str:
        d = verdicts[(verdicts["verdict"] == verdict) & (verdicts["evidence"] == evidence)]
        return ", ".join(d["line"].map(_label)) or "none"

    depends = verdicts[verdicts["verdict"] == "depends on assumptions"]["line"].map(_label).tolist()
    mostly = verdicts[verdicts["verdict"].str.startswith("mostly")]
    c = curve[curve["solved"]].reset_index(drop=True)
    best_budget = float(c["budget"].to_numpy()[int(np.argmax(c["expected_profit"].to_numpy()))])
    at_2m = float(c.loc[c["budget"] == float(cfg.section("budget")["annual_total"]), "expected_profit"].iloc[0])
    best_profit = float(c["expected_profit"].max())
    infeasible = curve.loc[~curve["solved"], "budget"].tolist()
    s: dict[Any, dict[Any, Any]] = summary.set_index("scenario").to_dict("index")
    b3_6 = s["b3_payback_6m"]

    validation = ""
    if score:
        tables = cfg.path("tables_dir")
        score["verdicts"].to_csv(tables / "sensitivity_verdicts_validation_SYNTHETIC.csv", index=False)
        score["budget_curve"].to_csv(tables / "sensitivity_budget_curve_truth_SYNTHETIC.csv", index=False)
        score["scenarios"].to_csv(tables / "sensitivity_scenarios_truth_SYNTHETIC.csv", index=False)
        score["payback"].to_csv(tables / "sensitivity_payback_truth_SYNTHETIC.csv", index=False)
        sv: dict[Any, dict[Any, Any]] = score["scenarios"].set_index("scenario").to_dict("index")
        v = score["verdicts"]
        nr = v[v["verdict"].str.startswith("no-regret")]
        ms = v[v["verdict"].str.startswith("mostly")]
        tc = score["budget_curve"]
        tbest = float(tc["budget"].to_numpy()[int(np.nanargmax(tc["true_profit_of_model_plan"].to_numpy()))])
        topt = float(tc["budget"].to_numpy()[int(np.nanargmax(tc["true_best_achievable"].to_numpy()))])
        pay = score["payback"]
        b3_months = float(pay.set_index("business").to_dict("index")["B3"]["true_payback_months"])
        wrong = ms[ms["direction_right"] == 0]["line"].map(_label).tolist()
        validation = f"""
## Validation against the SYNTHETIC ground truth

**No-regret verdicts:** {int(nr["direction_right"].sum())} of {len(nr)} point the same way as the true optimum. "Mostly"
verdicts: {int(ms["direction_right"].sum())} of {len(ms)}{f" (wrong: {', '.join(wrong)}, both untested lines)" if wrong else ""}. Agreement across
scenarios is good evidence where experiments anchor the lines, and weaker where they do not.

{_md(v, ",.2f")}

**Budget:** the model's plan really earns most at **${tbest / 1e6:.1f}M**; the best achievable allocation peaks at
${topt / 1e6:.1f}M. The model's advice to spend less than $2M is right about its own plan, and the truth shows that
a better plan could use more.

{_md(tc)}

**Scenario plans in reality** (true gain over last year's split; base {_k(sv["base"]["true_gain"])}):

- Planning for a B2 sales capacity of 50 that has not been hired really earns {_k(sv["b2_capacity_50"]["true_gain"])}.
- Reading the experiments at their pessimistic end earns {_k(sv["tests_pessimistic"]["true_gain"])}; at their
  optimistic end, {_k(sv["tests_optimistic"]["true_gain"])}. The model leans optimistic, so caution pays.
- The guardrail at 10%, 25% (base), 50% and none: {_k(sv["guardrail_10"]["true_gain"])}, {_k(sv["base"]["true_gain"])},
  {_k(sv["guardrail_50"]["true_gain"])}, {_k(sv["no_guardrail"]["true_gain"])}.

**Payback of the recommended plan in reality:** every business meets its target; B3 pays back in
{b3_months:.0f} months, inside even the original 6-month target.

{_md(pay, ",.1f")}
"""

    text = f"""# Sensitivity analysis (SYNTHETIC data)

## Summary for management

1. **Business question.** Which assumptions could change the recommended plan, and which parts of it stand
   whatever we assume?
2. **Why it matters.** Every number in the plan rests on choices: how long a customer is valued, which
   policies bind, how the curves were fitted. A recommendation that flips when one of them moves is a guess.
3. **What this establishes.** The plan was re-optimised under {len(others)} alternative assumptions.
   - **Valuation choices barely change the plan.** On average {by_group.get("valuation", 0):.1%} of the budget moves.
   - **Policies** ({by_group.get("policy", 0):.1%}) and **how the model was built** ({by_group.get("model", 0):.1%}) matter more.
   - The plan changes most under {moved_text}.
4. **In business terms.**
   - **No-regret moves backed by an experiment** (same direction in every scenario): increase
     {names("no-regret increase", "experiment")}; cut {names("no-regret cut", "experiment")}.
   - **Consistent in every scenario, but resting on history alone:** increase {names("no-regret increase", "history only")};
     cut {names("no-regret cut", "history only")}. Every scenario reuses the same history, so this agreement
     is weaker evidence than it looks.
   - **Probably right** (three-quarters of scenarios or more, history only): {", ".join(_label(x) for x in mostly["line"])}.
   - **Depends on assumptions:** {", ".join(depends) or "none"}. Decide these after the next tests.
   - **Budget:** by the model, profit peaks at about **${best_budget / 1e6:.1f}M**, earning {_k(best_profit - at_2m)} a
     year more than at $2.0M.{f" Budgets of ${min(infeasible) / 1e6:.1f}M and above cannot be placed within the current policies." if infeasible else ""}
   - **B3 payback at 6 months** (the CFO's original target, relaxed to 9 in D-011): {"by the model the recommended plan already meets it, unchanged" if abs(float(b3_6["share_of_budget_moved_vs_base"])) < 0.005 else "meeting it moves " + format(float(b3_6["share_of_budget_moved_vs_base"]), ".0%") + " of the budget"}. Cutting retargeting lowers B3's cost per incremental customer enough that the original target becomes reachable.
5. **Action to consider.**
   - Make the experiment-backed moves now, in full.
   - Make the history-only moves within the 25% guardrail. Test the largest of them before going further.
   - Hold the "depends" lines until they have been tested.
   - Treat $2M as a ceiling, not a target, until the untested lines are measured.
   - Do not plan B2 spend around sales capacity that has not been hired.
6. **Assumptions and limits.**
   - Each scenario changes one assumption at a time; combinations can interact.
   - Model scenarios refit with {cfg.section("sensitivity")["refit_draws"]} curve draws, not 200.
   - The budget curve keeps every other policy in place.

![Profit of the optimised plan at each budget]({f_budget.relative_to(rel).as_posix()})

## Scenarios

Gains are annual incremental contribution after spend, over last year's split at the same budget.
`gain_under_base_assumptions` shows what the scenario's plan earns if the base assumptions are right: the cost of
planning for the wrong world. `base_moves_kept` is the share of the base plan's moves that keep their direction.

{_md(summary, ",.2f")}

![Promised vs real gain by scenario]({f_scen.relative_to(rel).as_posix()})

## Line by line: which moves survive every assumption

Change from last year's split in the base plan, and the range across all scenarios (budget fixed at $2M).

{_md(verdicts.assign(line=verdicts["line"].map(_label)), ",.2f")}

## Budget curve

{_md(curve)}
{validation}"""
    path = cfg.path("reports_dir") / "sensitivity.md"
    path.write_text(text, encoding="utf-8")
    return path
