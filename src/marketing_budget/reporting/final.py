"""Phase 9: the write-up (executive memo, recommendations, technical report, model card, monitoring plan).

Every number is computed here from the SQL layer and the phase 1-8 outputs in `reports/tables`, so the documents
can be regenerated and cannot drift from the analysis. The memo and recommendations use only what management
could know: actuals, randomised tests and the model. The technical report and model card add a separate,
labelled check against the simulation's truth, read from the tables the validation package wrote
(`*_SYNTHETIC.csv`); nothing here reads the truth itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.analysis.retention import ALL
from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.optimisation.inputs import LAST_52
from marketing_budget.reporting.stakeholders import NAMES, Numbers, _k, _label, _more_fewer, _signed, compute_numbers

DISCLAIMER = """> **The data are simulated (SYNTHETIC).** The company, its three businesses and every figure below come from
> a simulation built for this project, because only a simulation reveals each channel's true effect and so
> lets the method be checked. The figures show what the method recommends and how; they are not facts
> about a real company."""

LABELS = """**Evidence labels.** *Actual*: measured in the company's own systems. *Causal*: measured by a randomised
test. *Model*: estimated by the marketing-mix model; depends on its assumptions. *Assumption*: a finance or
management input, not something the data showed."""


def _md(df: pd.DataFrame, floatfmt: str = ",.2f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def _range(a: float, b: float) -> str:
    return f"{_k(a)} to {_k(b)}"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def final_numbers(con: duckdb.DuckDBPyConnection, cfg: Config) -> Numbers:
    """The phase 8 numbers plus what the write-up adds. Management-side only: no truth-based tables."""
    n = compute_numbers(con, cfg)
    v = n.v
    t = cfg.path("tables_dir")

    sp = query_df(
        con,
        f"SELECT business, sum(spend) AS spend FROM business_week WHERE {LAST_52} GROUP BY business ORDER BY business",
    )
    v["actual_spend"] = float(sp["spend"].sum())
    # the plan's baseline: last year's split scaled to the budget (phase 4)
    ev_rows: dict[Any, dict[Any, Any]] = (
        pd.read_csv(t / "allocation_evaluation.csv").set_index("allocation").to_dict("index")
    )
    v["sq_spend"] = {b: float(ev_rows["status_quo"][f"spend_{b}"]) for b in cfg.businesses}
    v["budget_total"] = float(cfg.section("budget")["annual_total"])
    v["monitoring"] = cfg.section("monitoring")
    al = v["allocation"]
    firm = al["evidence"].eq("experiment") & al["verdict"].str.startswith("no-regret")
    cuts = al[(al["change"] < -1000) & ~firm].sort_values("change")
    v["cuts_now"] = float(cuts["change"].sum())
    v["cuts_now_lines"] = ", ".join(_label(x) for x in cuts["line"])
    v["top_cuts"] = " and ".join(_label(x) for x in al.nsmallest(2, "change")["line"])
    v["top_adds"] = " and ".join(_label(x) for x in al.nlargest(2, "change")["line"])

    est = pd.read_csv(t / "customer_value_estimates.csv")
    est = est[est["source"] == ALL].set_index("business")
    v["values"] = {
        str(b): (float(r["customer_value"]), float(r["value_ci_low"]), float(r["value_ci_high"]))
        for b, r in est.iterrows()
    }

    sel = pd.read_csv(t / "forecast_selected_models.csv")
    v["forecast_selected"] = sel
    qa = pd.read_csv(t / "forecast_quarter_accuracy.csv")
    qw = {(str(b), str(g)): float(w) for b, g, w in zip(qa["business"], qa["target"], qa["quarter_wape"], strict=True)}
    for key, target in (("wape_customers", "customers"), ("wape_contribution", "contribution_profit")):
        w = [x for (_, g), x in qw.items() if g == target]
        v[key] = (min(w), max(w))
    v["forecast_quarter"] = qa
    v["n_regression_wins"] = int((sel["selected"] == "regression").sum())
    v["n_forecasts"] = len(sel)
    fs = pd.read_csv(t / "forecast_scenarios.csv")
    fs = fs[fs["period"] == "next quarter"]
    v["forecast_next_q"] = fs.pivot_table(
        index=["business", "target"], columns="scenario", values="value"
    ).reset_index()
    cov = pd.read_csv(t / "forecast_interval_coverage.csv")
    cov = cov.merge(
        sel[["business", "target", "selected"]],
        left_on=["business", "target", "model"],
        right_on=["business", "target", "selected"],
    )
    v["interval_coverage"] = (
        float(cov["coverage"].min()),
        float(cov["coverage"].max()),
        float(cov["target_level"].iloc[0]),
    )

    el = pd.read_csv(t / "spend_elasticity_observational.csv")
    piv = el.pivot_table(index="business", columns="specification", values="elasticity")
    v["elasticity_shrink"] = (piv["spend + trend + seasonality"] / piv["spend only"]).agg(["min", "max"]).tolist()

    eff = pd.read_csv(t / "experiment_effects.csv")
    v["n_experiments"] = int(eff["experiment"].nunique())
    geo = pd.read_csv(t / "experiment_geo_design.csv")
    v["n_geo"], v["n_geo_powered"] = len(geo), int(geo["powered"].sum())
    dec = pd.read_csv(t / "experiment_decisions.csv")
    v["decisions"] = dec
    v["n_do_it"] = int(dec["verdict"].str.startswith("do it").sum())
    v["effects"] = eff
    cal = pd.read_csv(t / "model_calibration_check.csv")
    v["calibration"] = cal
    v["n_cal_in_band"] = int(((cal["measured"] >= cal["model_p10"]) & (cal["measured"] <= cal["model_p90"])).sum())

    ev = pd.read_csv(t / "allocation_evaluation.csv")
    v["evaluation"] = ev
    v["policy_costs"] = pd.read_csv(t / "policy_costs.csv")
    mr = pd.read_csv(t / "marginal_returns.csv")
    sq = mr[mr["allocation"] == "status_quo"]
    v["mr_status_quo"] = sq
    lo, hi = (
        sq.iloc[int(np.argmin(sq["marginal_return"].to_numpy()))],
        sq.iloc[int(np.argmax(sq["marginal_return"].to_numpy()))],
    )
    v["mr_low"] = (_label(f"{lo['business']}.{lo['channel']}"), float(lo["marginal_return"]))
    v["mr_high"] = (_label(f"{hi['business']}.{hi['channel']}"), float(hi["marginal_return"]))

    # a warning sign the analysis can see without the truth: a history-only line whose modelled NEXT dollar
    # brings more customers than the platform credits to its AVERAGE dollar. Platforms over-claim and returns
    # diminish, so this points to an optimistic curve.
    lens = pd.read_csv(cfg.path("dashboard_dir") / "data" / "synthetic_channel_lenses.csv")
    model = lens[lens["lens"].str.contains("next dollar")].set_index("line")
    plat = lens[lens["lens"].str.contains("Platform")].set_index("line")["customers_per_1000"]
    sus = model[(model["customers_per_1000"] > plat.reindex(model.index)) & model["evidence"].str.contains("history")]
    plat_d = {str(k): float(x) for k, x in plat.items()}
    v["suspicious"] = [(_label(str(i)), float(m), plat_d[str(i)]) for i, m in sus["customers_per_1000"].items()]

    sc = pd.read_csv(t / "sensitivity_scenarios.csv")
    others = sc[sc["scenario"] != "base"]
    v["n_scenarios"] = len(others)
    v["moved_by_group"] = others.groupby("group")["share_of_budget_moved_vs_base"].mean().to_dict()
    v["min_scenario_gain"] = float(others.loc[others["solved"].astype(bool), "gain_under_base_assumptions"].min())
    gains = dict(zip(sc["scenario"], sc["gain_own_assumptions"], strict=True))
    v["value_minus_20_gain"] = float(gains["all_values_minus_20"])
    ver = pd.read_csv(t / "sensitivity_line_verdicts.csv")
    v["verdicts"] = ver
    v["no_regret"] = ver.loc[ver["verdict"].str.startswith("no-regret"), "line"].map(_label).tolist()
    v["mostly"] = ver.loc[ver["verdict"].str.startswith("mostly"), "line"].map(_label).tolist()
    v["guardrail"] = float(cfg.section("budget")["untested_line_guardrail"])
    v["n_tested_lines"] = int(ver["evidence"].eq("experiment").sum())
    v["n_lines"] = len(ver)

    fact = pd.read_csv(t / "ai_fact_sheet.csv")
    v["n_facts"] = len(fact)
    lin = pd.read_csv(t / "lineage.csv")
    v["lineage"] = lin
    v["dq_checks"] = pd.read_csv(t / "dq_checks.csv")
    v["dq_issues"] = pd.read_csv(t / "dq_issues.csv")
    return n


def truth_check(cfg: Config) -> dict[str, Any] | None:
    """Results the validation package scored against the simulation's truth; None if they were not written."""
    t = cfg.path("tables_dir")
    files = {
        "allocation": "allocation_true_profit_SYNTHETIC.csv",
        "curves": "curve_recovery_SYNTHETIC.csv",
        "dq": "dq_validation_SYNTHETIC.csv",
        "value": "customer_value_validation_SYNTHETIC.csv",
        "experiments": "experiment_validation_SYNTHETIC.csv",
        "method": "experiment_method_check_SYNTHETIC.csv",
        "verdicts": "sensitivity_verdicts_validation_SYNTHETIC.csv",
        "budget": "sensitivity_budget_curve_truth_SYNTHETIC.csv",
        "payback": "sensitivity_payback_truth_SYNTHETIC.csv",
        "elasticity": "spend_elasticity_validation.csv",
    }
    if not all((t / f).exists() for f in files.values()):
        return None
    d = {k: pd.read_csv(t / f) for k, f in files.items()}
    s: dict[str, Any] = {"tables": d}
    al: dict[Any, dict[Any, Any]] = d["allocation"].set_index("allocation").to_dict("index")
    s["true_gain"] = float(al["recommended"]["true_gain_vs_status_quo"])
    s["share_achievable"] = float(al["recommended"]["share_of_achievable_gain"])
    s["achievable"] = float(al["true_optimum"]["true_gain_vs_status_quo"])
    s["roas_true"] = float(al["platform_roas"]["true_gain_vs_status_quo"])
    s["no_guardrail_true"] = float(al["recommended_without_guardrail"]["true_gain_vs_status_quo"])
    s["sq_model_profit"] = float(al["status_quo"]["model_expected_profit"])
    s["sq_true_profit"] = float(al["status_quo"]["true_profit"])
    s["dq_found"], s["dq_total"] = int(d["dq"]["detected"].sum()), len(d["dq"])
    s["value_in_ci"], s["value_total"] = int(d["value"]["true_in_ci"].sum()), len(d["value"])
    s["exp_in_ci"], s["exp_total"] = int(d["experiments"]["true_in_ci"].sum()), len(d["experiments"])
    cr = d["curves"]
    s["curves_in_band"], s["curves_total"] = int(cr["true_in_80pct_band"].sum()), len(cr)
    tested = {f"{x}" for x in cfg_tested_lines(cfg)}
    cr = cr.assign(line=cr["business"] + "." + cr["channel"])
    s["curves_in_band_tested"] = int(cr.loc[cr["line"].isin(tested), "true_in_80pct_band"].sum())
    s["n_tested"] = int(cr["line"].isin(tested).sum())
    ratio = cr["model_marginal_per_1000"] / cr["true_marginal_per_1000"]
    hist = ~cr["line"].isin(tested)
    s["curve_ratio_untested"] = (float(ratio[hist].min()), float(ratio[hist].max()))
    vd = d["verdicts"]
    nr, ms = vd[vd["verdict"].str.startswith("no-regret")], vd[vd["verdict"].str.startswith("mostly")]
    s["nr_right"], s["nr_total"] = int(nr["direction_right"].sum()), len(nr)
    s["mostly_right"], s["mostly_total"] = int(ms["direction_right"].sum()), len(ms)
    s["mostly_wrong"] = ms.loc[ms["direction_right"] == 0, "line"].map(_label).tolist()
    tc = d["budget"]
    s["true_best_budget"] = float(
        tc["budget"].to_numpy()[int(np.nanargmax(tc["true_profit_of_model_plan"].to_numpy()))]
    )
    el = d["elasticity"]
    s["elasticity_over"] = {
        str(spec): (float(g["overstatement"].min()), float(g["overstatement"].max()))
        for spec, g in el.groupby("specification")
    }
    return s


def cfg_tested_lines(cfg: Config) -> list[str]:
    """Lines with a calibrating experiment (the region tests that change a channel's budget)."""
    cal = pd.read_csv(cfg.path("tables_dir") / "model_calibration_check.csv")
    geo = pd.read_csv(cfg.path("tables_dir") / "experiment_geo_design.csv").set_index("experiment")["line"]
    return [str(geo[e]).replace(" ", ".", 1) for e in cal["experiment"]]


# ----------------------------------------------------------------------------------------------- memo


def _actions(v: dict[str, Any]) -> pd.DataFrame:
    lp = v["decisions"].set_index("experiment").loc["landing_page"]
    rows = [
        {
            "#": 1,
            "action": f"Make the tested moves now ({v['now_moves']}) and the cuts the model supports on untested lines ({_k(v['cuts_now'])}: {v['cuts_now_lines']})",
            "owner": "Marketing Director",
            "when": "Next budget cycle",
            "evidence": "Causal + Model",
        },
        {
            "#": 2,
            "action": f"Launch the new B1 landing page ({_signed(float(lp['estimate']))} a year, range {_range(float(lp['low']), float(lp['high']))})",
            "owner": "B1 general manager",
            "when": "Now",
            "evidence": "Causal",
        },
        {
            "#": 3,
            "action": f"Hold {_k(v['reserve'])} of increases as a reserve ({v['reserve_lines']}); release each line when a test shows its next dollar earns more than it costs",
            "owner": "CFO (release), Analytics (tests)",
            "when": "Line by line, as tests read out",
            "evidence": "Model, to be tested",
        },
        {
            "#": 4,
            "action": f"Treat ${v['budget_total'] / 1e6:,.1f}M as a ceiling, not a target; do not raise it. Profit peaks near ${v['best_budget'] / 1e6:.1f}M; with the reserve unspent, committed spend starts at {_k(v['budget_total'] - v['reserve'])}, and the reserve is the first money to return if tests disappoint",
            "owner": "CFO",
            "when": "This budget round",
            "evidence": "Model",
        },
        {
            "#": 5,
            "action": f"Prepare a B2 sales-capacity business case: lifting the {v['b2_capacity']:.0f}-leads-a-week limit is worth up to {_k(v['capacity_value'])} a year before hiring costs",
            "owner": "B2 BU Director, CFO",
            "when": "Next quarter",
            "evidence": "Model",
        },
        {
            "#": 6,
            "action": f"Run the next tests where the money at stake is largest: {v['next_tests']}",
            "owner": "Analytics, Marketing",
            "when": "Start within the quarter",
            "evidence": "Model (prioritisation)",
        },
        {
            "#": 7,
            "action": f"Fix the {_label(v['shift_line'])} conversion tag, remove duplicate B2 demo requests at entry ({v['dup_rate']:.1%} of leads), and judge channels on the shared metric framework, not platform ROAS",
            "owner": "Data Engineer",
            "when": "Now",
            "evidence": "Actual",
        },
    ]
    return pd.DataFrame(rows)


def _evidence(v: dict[str, Any]) -> pd.DataFrame:
    lp_up = v["lp_uplift"]
    rows = [
        (
            "Ad platforms claim more conversions than the CRM credits",
            f"up to {v['overclaim_max']:.1f}x",
            "Actual",
            "data_quality.md",
        ),
        (
            "B3 retargeting: customers per $1,000 by platform / last click / randomised test",
            f"{v['rt_platform']:.0f} / {v['rt_lastclick']:.0f} / {v['rt_causal']:.0f} (test range up to {v['rt_causal_high']:.0f})",
            "Actual / Actual / Causal",
            "experiments.md",
        ),
        (
            "New B1 landing page: conversion uplift",
            f"{100 * lp_up:+.1f}%, {_signed(v['lp_value'])} a year",
            "Causal",
            "experiments.md",
        ),
        (
            "Switching off B3 retargeting entirely",
            f"{_signed(v['rt_value'])} a year (cautious case {_signed(v['rt_value_low'])})",
            "Causal",
            "experiments.md",
        ),
        (
            "LinkedIn lookalike audiences (B2)",
            f"{_more_fewer(v['li_leads'], 'leads')}, {_more_fewer(v['li_qual'], 'qualified leads')}",
            "Causal",
            "experiments.md",
        ),
        (
            "B2 qualified leads a week vs what sales can work",
            f"{v['b2_qualified_per_week']:.0f} vs {v['b2_capacity']:.0f}",
            "Actual / Assumption",
            "stakeholder_simulation.md",
        ),
        (
            "Recommended plan vs last year's split",
            f"{_signed(v['plan_gain'])} a year (pessimistic {_signed(v['plan_down_gain'])})",
            "Model",
            "optimisation.md",
        ),
        ("Steering by platform ROAS instead", f"{_signed(v['roas_loss'])} a year", "Model", "optimisation.md"),
        (
            "Moves that hold under every one of the alternative assumptions",
            f"{len(v['no_regret'])} of {v['n_lines']} lines",
            "Model",
            "sensitivity.md",
        ),
        ("Budget at which profit peaks", f"${v['best_budget'] / 1e6:.1f}M", "Model", "sensitivity.md"),
        (
            "24-month value of a new customer: B1 / B2 / B3",
            " / ".join(f"${v['values'][b][0]:,.0f}" for b in ("B1", "B2", "B3")),
            "Actual (cohorts) + Assumption (margins)",
            "customer_value.md",
        ),
        (
            "Error of the quarterly new-customer forecast",
            f"{100 * v['wape_customers'][0]:.0f}-{100 * v['wape_customers'][1]:.0f}% across businesses",
            "Actual (back-test)",
            "forecasting.md",
        ),
    ]
    return pd.DataFrame(rows, columns=["finding", "number", "evidence", "detail in"])


def _success(v: dict[str, Any]) -> pd.DataFrame:
    pay = v["payback"].set_index("business")["target_months"]
    mo = v["monitoring"]
    rows = [
        (
            "Contribution after ad spend, by business",
            "At or above the plan's pessimistic case",
            "P&L (Actual)",
            "Monthly; formal review each quarter",
            "CFO",
        ),
        (
            "Incremental customers on the moved lines",
            f"Measured by a {mo['holdout_share']:.0%} region holdout on each line whose spend moved by more than {mo['holdout_min_move']:.0%}",
            "Region holdout (Causal)",
            f"Read out at {mo['holdout_weeks']} weeks",
            "Analytics",
        ),
        (
            "Reserve releases",
            "Released only where the test's cautious case shows the next dollar returns more than $1",
            "Region test (Causal)",
            "As each test reads out",
            "CFO",
        ),
        (
            "Payback by business",
            " / ".join(f"{b} within {int(pay[b])} months" for b in ("B1", "B2", "B3")),
            "Cohort value vs incremental CAC (Actual + Model)",
            "Quarterly",
            "CFO",
        ),
        (
            "B2 sales workload",
            f"Qualified leads at or below {v['b2_capacity']:.0f} a week, unless capacity is added",
            "CRM (Actual)",
            "Weekly",
            "B2 BU Director",
        ),
        (
            "Forecast accuracy",
            f"Actual quarterly customers inside the forecast's {100 * v['interval_coverage'][2]:.0f}% range",
            "Forecast vs actual",
            "Quarterly",
            "Analytics",
        ),
        (
            "Data trust",
            "Every data-quality check passes before figures go to management",
            "Pipeline checks (Actual)",
            "Every build",
            "Data Engineer",
        ),
    ]
    return pd.DataFrame(rows, columns=["measure", "success means", "source", "when", "owner"])


def write_executive_memo(n: Numbers, cfg: Config, truth: dict[str, Any] | None) -> Path:
    v = n.v
    spend_by = ", ".join(f"{b} {NAMES[b]} {_k(x)}" for b, x in v["sq_spend"].items())
    pay = v["payback"]
    all_meet = bool((pay["payback_months_recommended"] <= pay["target_months"]).all())
    sus = "; ".join(
        f"{name} ({m:.0f} customers per $1,000 for the next dollar vs {p:.0f} the platform credits on average)"
        for name, m, p in v["suspicious"]
    )
    mbg = v["moved_by_group"]
    actions = _actions(v)
    shrink = v["elasticity_shrink"]
    b2_note = (
        " Every B2 line is near zero because its sales team is full: extra leads go unworked."
        if v["mr_low"][0].startswith("B2") and v["b2_qualified_per_week"] >= v["b2_capacity"]
        else ""
    )
    annex = ""
    if truth:
        annex = f"""
## Annex: does the method work? (simulation only)

Because the data are simulated, the plan can be scored against the true effects, which no real company could
do. The model expected {_signed(v["plan_gain"])}; the plan **really earns {_signed(truth["true_gain"])} a year**,
{truth["share_achievable"]:.0%} of the {_k(truth["achievable"])} that perfect knowledge would achieve. Steering by platform
ROAS would really lose {_k(-truth["roas_true"])}. All {truth["nr_total"]} moves that held under every assumption point the
right way; {truth["mostly_total"] - truth["mostly_right"]} of {truth["mostly_total"]} "probably" moves on untested lines do not
({", ".join(truth["mostly_wrong"]) or "none"}). The model overstates the gain by about
{v["plan_gain"] / truth["true_gain"] - 1:.0%}: the reason for the reserve, the guardrail and the tests in actions 3 and 6.
Full scoring: [technical_report.md](technical_report.md#9-validation-against-the-simulations-truth).
"""

    text = f"""# Executive decision memo: next year's paid-acquisition plan

**To:** CEO, CFO, Marketing Director · **From:** Head of Analytics · **Decision:** how to spend the
${v["budget_total"] / 1e6:,.1f}M paid-acquisition budget across Hearth Box (B1), Ledgerline (B2) and Atlas Outdoor (B3)

{DISCLAIMER}

**Recommendation.** Approve a plan that keeps the total within ${v["budget_total"] / 1e6:,.1f}M but moves {_k(v["moved"])}
between channels, makes the tested moves now, and holds {_k(v["reserve"])} of unproven increases in reserve until
tests support them. The model expects it to add **{_k(v["plan_gain"])} a year of contribution** (pessimistic case
{_k(v["plan_down_gain"])}). Separately, decide whether to expand B2's sales team: that, not advertising, now limits B2.

{LABELS}

## 1. What is happening?

- Last year's split, scaled to the ${v["budget_total"] / 1e6:,.1f}M budget, is {spend_by} (actual spend over the
  last 52 weeks: {_k(v["actual_spend"])}). *Actual.*
- **The dashboards and the economics disagree.** Ad platforms claim up to {v["overclaim_max"]:.1f}x the conversions the
  company's CRM credits to them. *Actual.* For B3 retargeting, the platform credits {v["rt_platform"]:.0f} new customers
  per $1,000, CRM last click {v["rt_lastclick"]:.0f}, and a randomised test about {v["rt_causal"]:.0f} (at most
  {v["rt_causal_high"]:.0f}). *Causal.* Most of what retargeting is credited with would have happened anyway.
- **B2 has outgrown its sales team.** It produces {v["b2_qualified_per_week"]:.0f} qualified leads a week; the team can work
  {v["b2_capacity"]:.0f}. *Actual; capacity is a management input.*
- **Some numbers were wrong.** {v["n_issues"]} data problems were found, including a tracking change from
  {v["shift_date"]:%d %b %Y} that makes {_label(v["shift_line"])} look worse than it is, and duplicate B2 demo requests
  ({v["dup_rate"]:.1%} of leads). *Actual.*

## 2. Why?

- **Platforms count customers who were already on their way.** That is why retargeting and brand search look
  best on dashboards and earn least from the next dollar.
- **Budgets followed demand.** Spend was raised in strong seasons, so history credits advertising with demand
  that was there anyway: the measured effect of spend falls to {shrink[0]:.0%}-{shrink[1]:.0%} of its raw size once
  season and trend are accounted for. *Model (regression on history).*
- **Returns diminish.** At last year's split the next dollar earned anywhere from ${v["mr_low"][1]:.2f}
  ({v["mr_low"][0]}) to ${v["mr_high"][1]:.2f} ({v["mr_high"][0]}) of 24-month contribution. *Model.*{b2_note} Money
  was in the wrong places, not too little of it.

## 3. What are the financial consequences?

| | Annual contribution | Evidence |
|---|---|---|
| Recommended plan vs last year's split | {_signed(v["plan_gain"])} (pessimistic {_signed(v["plan_down_gain"])}) | Model |
| Steering by platform ROAS instead | {_signed(v["roas_loss"])} | Model |
| New B1 landing page | {_signed(v["lp_value"])} | Causal |
| Switching off B3 retargeting entirely | {_signed(v["rt_value"])} (cautious {_signed(v["rt_value_low"])}) | Causal |
| Lifting B2's sales-capacity limit, before hiring costs | up to {_signed(v["capacity_value"])} | Model |
| Moving untested lines by more than {v["guardrail"]:.0%} | up to {_signed(v["guardrail_cost"])}, not taken (see section 6) | Model |

The budget itself is not the constraint: the last $200k returned about ${v["last_200k_back"]:.2f} per dollar, and profit
peaks near ${v["best_budget"] / 1e6:.1f}M. {"Every business meets its payback target under the plan." if all_meet else "Not every business meets its payback target under the plan."} *Model.*

## 4. What should management do?

{_md(actions)}

## 5. What evidence supports this?

{_md(_evidence(v))}

Reports are in [reports/](.); the method is in [technical_report.md](technical_report.md).

## 6. What could invalidate the recommendation?

- **Untested lines rest on history.** Only {v["n_tested_lines"]} of {v["n_lines"]} lines have a test behind them. On
  some untested lines the model looks optimistic: {sus or "none flagged"}. A next dollar should not beat the
  platform's own average claim. Hence the {v["guardrail"]:.0%} limit on untested lines and the reserve.
- **Some moves depend on assumptions.** {len(v["mostly"])} lines move in the same direction in most but not all of
  {v["n_scenarios"]} alternative scenarios ({", ".join(v["mostly"])}). Treat these as probable, not proven.
- **Tests measure averages.** A switch-off test shows what a channel's whole budget does, not its next dollar.
- **Value assumptions.** Customer values use a 24-month horizon, a 10% discount rate and finance's margins. If every
  customer were worth 20% less, the plan would still gain {_k(v["value_minus_20_gain"])}; valuation choices move only
  {mbg.get("valuation", 0):.1%} of the budget. *Model.*
- **Not modelled:** seasonal timing of spend, channels boosting each other, competitor moves, and the cost of
  hiring B2 sales staff.

**What would change the recommendation:** a test showing a reserve line's next dollar returns less than $1 (keep it
in reserve or cut); a B2 hiring cost below {_k(v["capacity_value"])} a year (expand B2); a fixed tracking tag that changes
{_label(v["shift_line"])}'s numbers (re-run the model).

## 7. How will success be measured?

{_md(_success(v))}
{annex}"""
    return _write(cfg.path("reports_dir") / "executive_memo.md", text)


# ------------------------------------------------------------------------------------- recommendations


def recommendations_table(n: Numbers) -> pd.DataFrame:
    v = n.v
    al = v["allocation"].copy()
    firm = al["evidence"].eq("experiment") & al["verdict"].str.startswith("no-regret")

    def act(r: dict[str, Any], is_firm: bool) -> str:
        if abs(r["change"]) <= 1000:
            return "hold"
        if is_firm:
            return "move now"
        if r["change"] > 0:
            return "reserve until tested"
        return "cut now (within guardrail)"

    def change_view(r: dict[str, Any]) -> str:
        if abs(r["change"]) <= 1000:
            return "a test showing the next dollar returns well above or below $1"
        if r["change"] > 0:
            return "a test at the new spend showing the next dollar returns less than $1"
        return "a test of a part-way cut showing the dollars cut returned more than $1"

    recs = al.to_dict("records")
    return pd.DataFrame(
        {
            "line": [_label(r["line"]) for r in recs],
            "last year": [_k(r["status_quo"]) for r in recs],
            "plan": [_k(r["recommended"]) for r in recs],
            "change": [_signed(r["change"]) for r in recs],
            "across scenarios": [str(r["verdict"]) for r in recs],
            "evidence": ["experiment" if r["evidence"] == "experiment" else "history only" for r in recs],
            "action": [act(r, bool(f)) for r, f in zip(recs, firm, strict=True)],
            "what would change it": [change_view(r) for r in recs],
        }
    )


def write_recommendations(n: Numbers, cfg: Config) -> Path:
    v = n.v
    rec = recommendations_table(n)
    rec.to_csv(cfg.path("tables_dir") / "recommendations_by_line.csv", index=False)
    pay = v["payback"][["business", "target_months", "payback_months_last_year_split", "payback_months_recommended"]]
    text = f"""# Recommendations (SYNTHETIC data)

{DISCLAIMER}

## Summary for management

1. **Business question.** What should the company do with next year's ${v["budget_total"] / 1e6:,.1f}M paid-acquisition
   budget, line by line, and what would make us change course?
2. **Why it matters.** Last year's split was rolled forward and steered by platform dashboards. The model
   estimates that steering harder by those dashboards would cost {_k(-v["roas_loss"])} a year, and that a better
   split would add {_k(v["plan_gain"])}.
3. **What this establishes.** {len(v["no_regret"])} of the {v["n_lines"]} moves hold under every alternative assumption
   tested; {n.v["n_tested_lines"]} lines are anchored by randomised tests. The rest are model estimates from history.
4. **In business terms.** The biggest cuts are {v["top_cuts"]}; the biggest increases {v["top_adds"]}.
   Cuts on untested lines stay within the guardrail; increases are committed only where a test supports them.
5. **Action to consider.** The seven actions in the [executive memo](executive_memo.md#4-what-should-management-do),
   applied line by line below.
6. **Assumptions and limits.** Customer values (24 months, 10% discount, finance's margins), payback targets
   and B2 sales capacity are management inputs (`configs/config.yaml`). Untested lines move at most
   {v["guardrail"]:.0%}. Gains are model estimates, not achieved savings.

## Line by line

`across scenarios` is the phase 5 verdict over {v["n_scenarios"]} alternative assumptions: *no-regret* means the
direction never changed. `move now` is reserved for lines that are both tested and no-regret.

{_md(rec)}

## Payback (months for the customers advertising adds to repay their acquisition cost)

{_md(pay, ",.1f")}

## Quantified, with the assumptions shown

| Recommendation | Annual value | Assumptions it rests on |
|---|---|---|
| Adopt the plan | {_signed(v["plan_gain"])} (pessimistic {_signed(v["plan_down_gain"])}) | Response curves (3 test-calibrated, the rest history); 24-month values |
| Launch the landing page | {_signed(v["lp_value"])} | Test uplift holds after launch; B1 traffic stays at last year's level |
| Reduce B3 retargeting | part of the plan's gain; a full switch-off tested at {_signed(v["rt_value"])} | Test period representative of the year |
| B2 capacity case | up to {_signed(v["capacity_value"])} before hiring | Leads above capacity convert like today's once worked |
| Cap the total at ${v["budget_total"] / 1e6:,.1f}M | profit would be {_k(v["best_minus_2m"])} higher at ${v["best_budget"] / 1e6:.1f}M; with the reserve unspent, committed spend starts at {_k(v["budget_total"] - v["reserve"])} | Curves for untested lines |

## Risks and what would change the recommendation

See the [executive memo, section 6](executive_memo.md#6-what-could-invalidate-the-recommendation). In short:
a reserve line whose test shows a next-dollar return below $1 stays in reserve or is cut; a B2 hiring cost
below {_k(v["capacity_value"])} a year makes the capacity case; a repaired {_label(v["shift_line"])} tag requires a refit.
"""
    return _write(cfg.path("reports_dir") / "recommendations.md", text)


# ------------------------------------------------------------------------------------ technical report


def _truth_section(v: dict[str, Any], s: dict[str, Any] | None) -> str:
    if s is None:
        return "Validation tables not found; run the full pipeline (`uv run mbo all`)."
    d = s["tables"]
    cr = d["curves"][
        [
            "business",
            "channel",
            "model_marginal_per_1000",
            "model_p10",
            "model_p90",
            "true_marginal_per_1000",
            "true_in_80pct_band",
        ]
    ]
    al = d["allocation"]
    eo = s["elasticity_over"]
    return f"""The data are simulated, so each result can be scored against the truth. Models never see it
(a test enforces this); scoring happens only in `src/marketing_budget/validation/`.

| Check | Result |
|---|---|
| Injected data problems found | {s["dq_found"]} of {s["dq_total"]} |
| Customer-value intervals containing the true value | {s["value_in_ci"]} of {s["value_total"]} |
| Experiment intervals containing the true effect | {s["exp_in_ci"]} of {s["exp_total"]} |
| Spend effect estimated from history, vs the true effect | overstated {eo["spend only"][0]:.1f}x-{eo["spend only"][1]:.1f}x without controls, {eo["spend + trend + seasonality"][0]:.1f}x-{eo["spend + trend + seasonality"][1]:.1f}x with trend and seasonality |
| Model's 80% next-dollar bands containing the truth | {s["curves_in_band"]} of {s["curves_total"]} lines ({s["curves_in_band_tested"]} of {s["n_tested"]} tested lines) |
| "No-regret" directions right | {s["nr_right"]} of {s["nr_total"]} |
| "Mostly" directions right | {s["mostly_right"]} of {s["mostly_total"]} (wrong: {", ".join(s["mostly_wrong"]) or "none"}) |
| Plan's true gain vs last year's split | {_signed(s["true_gain"])} (model said {_signed(v["plan_gain"])}); {s["share_achievable"]:.0%} of the achievable {_k(s["achievable"])} |
| Same plan without the {v["guardrail"]:.0%} guardrail | {_signed(s["no_guardrail_true"])} |
| Platform-ROAS split | {_signed(s["roas_true"])} |
| Budget at which the model's plan truly earns most | ${s["true_best_budget"] / 1e6:.1f}M (model: ${v["best_budget"] / 1e6:.1f}M) |

**What this says about the method.**
- Experiments, retention and data checks are well calibrated: their intervals behave as stated.
- The marketing-mix model is not. On untested lines its next-dollar estimate is {s["curve_ratio_untested"][0]:.1f}x to
  {s["curve_ratio_untested"][1]:.1f}x the truth, and its bands are too narrow. It also overstates the level of
  profit (last year's split: model {_k(s["sq_model_profit"])}, truth {_k(s["sq_true_profit"])}), because it credits paid
  media with some organic demand. Gains between plans are more reliable than levels, but are still overstated.
- The safeguards earn their keep: the guardrail adds {_k(s["true_gain"] - s["no_guardrail_true"])} of true gain, and
  directions that held under every scenario were all right.

### Plans in truth

{_md(al, ",.0f")}

### Next-dollar returns: model vs truth (new customers per $1,000)

{_md(cr, ",.2f")}
"""


def write_technical_report(n: Numbers, cfg: Config, truth: dict[str, Any] | None) -> Path:
    v = n.v
    fc, rm = cfg.section("forecasting"), cfg.section("response_model")
    val, rk = cfg.section("valuation"), cfg.section("budget")["risk"]
    sel = v["forecast_selected"]
    acc = sel[sel["target"].isin(["customers", "contribution_profit", "revenue"])][
        ["business", "target", "selected", "selected_wape", "selected_bias", "seasonal_naive_wape"]
    ]
    nq = v["forecast_next_q"]
    nq = nq[nq["target"].isin(["customers", "contribution_profit"])]
    eff = v["effects"][["experiment", "metric", "relative_effect", "ci_low", "ci_high", "p_value", "decision"]]
    ev = v["evaluation"][["allocation", "expected_profit", "downside_profit", "p90_profit", "incremental_customers"]]
    al = v["allocation"][["line", "status_quo", "recommended", "change", "verdict", "evidence"]]
    pc = v["policy_costs"]
    mbg = v["moved_by_group"]
    cov = v["interval_coverage"]
    checks = v["dq_checks"]
    values = pd.DataFrame(
        [
            {"business": b, "24-month value": f"${x[0]:,.0f}", "95% interval": f"${x[1]:,.0f}-${x[2]:,.0f}"}
            for b, x in v["values"].items()
        ]
    )
    text = f"""# Technical report (SYNTHETIC data)

{DISCLAIMER}

## Summary for management

1. **Business question.** How should a fixed ${v["budget_total"] / 1e6:,.1f}M paid-acquisition budget be split across three
   businesses and {v["n_lines"]} channels to maximise long-term contribution, without excessive risk?
2. **Why it matters.** Steering by platform-reported returns would cost {_k(-v["roas_loss"])} a year by the model;
   a better split would add {_k(v["plan_gain"])}.
3. **What this establishes.** A pipeline that cleans and checks the data, values customers, forecasts, runs and
   reads experiments, fits calibrated response curves and optimises the split under policy constraints and
   uncertainty, then reports each result with its evidence type. Each step is checked against a simulated truth
   (section 9).
4. **In business terms.** Tested moves are reliable; untested ones are directionally useful but optimistic, so
   the plan limits them and holds a reserve.
5. **Action to consider.** See the [executive memo](executive_memo.md) and [recommendations](recommendations.md).
6. **Assumptions and limits.** Section 10.

This report gathers the method and results in one place. Each phase report has the full detail.

## 1. Data

A simulation (`src/marketing_budget/synthetic/`, seed {cfg.raw["seed"]}) produces weekly media, CRM, lead and customer
records for three businesses with {v["n_lines"]} channel lines over 156 weeks, plus five years of inherited customers.
It injects realistic problems: platform over-claiming, an attribution change, tracking outages, duplicate leads
and cost restatements. Design: [docs/data_design.md](../docs/data_design.md).

**Lineage** (row counts at each layer; [docs/data_lineage.md](../docs/data_lineage.md)):

{_md(v["lineage"], ",.0f")}

**Quality.** {int(checks["passed"].sum())} of {len(checks)} structural checks pass; {len(v["dq_issues"])} issues found and handled
(outage weeks excluded from platform metrics, duplicates removed, restated costs used, the attribution change
dated). [data_quality.md](data_quality.md)

{_md(v["dq_issues"])}

## 2. Customer value

24-month discounted contribution per new customer ({val["annual_discount_rate"]:.0%} a year). Subscriptions (B1, B2):
survival with a separate first-month hazard, fitted with censoring. E-commerce (B3): a Poisson model of repeat
orders decaying by month. Intervals are from {cfg.section("retention")["value_draws"]} parameter draws. Fully observed
early cohorts check the model. [customer_value.md](customer_value.md)

{_md(values)}

## 3. Forecasting

Models: {", ".join(fc["models"])}. The regression has trend, {fc["fourier_terms"]} Fourier seasonal pairs and log planned
spend; gradient boosting runs on detrended data. Validation is rolling-origin: train on at least
{fc["min_train_weeks"]} weeks, forecast {fc["horizon_weeks"]} weeks, move the origin {fc["origin_step_weeks"]} weeks, repeat.
Metrics: MAE, RMSE, WAPE and bias. The simplest model within {fc["selection_tolerance"]:.0%} of the best WAPE is chosen.
The regression is chosen for {v["n_regression_wins"]} of {v["n_forecasts"]} business-metric forecasts. {100 * cov[2]:.0f}% intervals come from
back-test errors; leave-one-origin-out coverage of the chosen models is {cov[0]:.0%}-{cov[1]:.0%}.
[forecasting.md](forecasting.md)

{_md(acc, ",.3f")}

Next quarter (pessimistic / baseline / optimistic):

{_md(nq, ",.0f")}

**Not causal.** The regression's spend coefficient falls to {v["elasticity_shrink"][0]:.0%}-{v["elasticity_shrink"][1]:.0%} of its
spend-only size once trend and seasonality are controlled, because budgets followed demand. Forecasts are
used for planning, never to set budgets.

## 4. Experiments

{v["n_experiments"]} randomised tests, each sized before launch. User-level tests use two-proportion tests (delta method
for click-through rates, Poisson for count rates). Region tests change budgets in randomly chosen regions and are
analysed by ANCOVA on the pre-period with HC2 errors and t critical values, checked by randomisation inference;
holdout share and duration come from an A/A rehearsal on the pre-period. {v["n_geo_powered"]} of {v["n_geo"]} region tests
reach the targeted detectable effect: the businesses are too small for more. Decisions compare the interval with
the business's break-even threshold. A peeking simulation shows why tests are not stopped early; Holm correction
is applied across metrics. [experiments.md](experiments.md)

{_md(eff, ",.3f")}

## 5. Response curves (marketing-mix model)

One model per business: weekly customers = organic base exp(trend + Fourier) × (1 + Σ β·Hill(adstock(spend))).
Adstock is geometric (decay in {rm["decay_bounds"]}, prior mean {rm["decay_prior"]["mean"]}); Hill shape {rm["shape"]}, half-saturation
in {rm["half_sat_bounds"]}× average spend. Quasi-Poisson weighting divides the history's weight by its over-dispersion, so
calibration to the {len(v["calibration"])} budget tests binds. The organic base is held near the CRM's organic-source
customers. Uncertainty: {rk["uncertainty_draws"]} weighted-likelihood bootstrap refits with test results redrawn within
their error. [optimisation.md](optimisation.md)

Calibration: {v["n_cal_in_band"]} of {len(v["calibration"])} measured test effects fall inside the model's 10-90% range.

{_md(v["calibration"], ",.3f")}

## 6. Optimisation

SLSQP with analytic gradients maximises expected annual contribution across all draws: customers the business
can serve × 24-month value − spend. Constraints: the total budget; business and channel limits; concentration;
keeping at least 90% of each business's customer volume; payback caps on incremental CAC; B2 sales capacity as a
cap on usable leads; untested lines within ±{v["guardrail"]:.0%} of last year; and the average of the worst
{rk["downside_quantile"]:.0%} of draws no worse than last year's split.

{_md(ev, ",.0f")}

{_md(al, ",.2f")}

**Cost of each policy** (gain if removed):

{_md(pc, ",.0f")}

## 7. Sensitivity

{v["n_scenarios"]} alternative scenarios change valuation, policy or the model itself (refits with {cfg.section("sensitivity")["refit_draws"]}
draws). Average share of the budget moved vs the plan: valuation {mbg.get("valuation", 0):.1%}, policy {mbg.get("policy", 0):.1%},
model {mbg.get("model", 0):.1%}. Each line's direction is labelled no-regret (same in every scenario), mostly, or depends.
The smallest gain of any scenario's plan under base assumptions is {_k(v["min_scenario_gain"])}. Profit peaks at a total
budget of ${v["best_budget"] / 1e6:.1f}M. [sensitivity.md](sensitivity.md)

{_md(v["verdicts"], ",.2f")}

## 8. Reporting and stakeholders

- Monthly KPI commentary is drafted from a {v["n_facts"]}-fact sheet built from the SQL layer. Code checks every
  sentence (citations, numbers, causal wording, metric names); a named reviewer signs off a hash of the exact
  draft. Claude is optional; the template is the default. [ai_reporting.md](ai_reporting.md)
- A simulated budget review reconciles four stakeholders on one metric framework.
  [stakeholder_simulation.md](stakeholder_simulation.md)

## 9. Validation against the simulation's truth

{_truth_section(v, truth)}

## 10. Limitations

- **Synthetic data.** The simulation is built to be hard in known ways (over-claiming, demand-following budgets,
  saturation, capacity). A real market has effects it does not, such as competitors and cross-channel synergy.
- **History-only curves are optimistic and over-confident** (section 9). The guardrail, reserve and next tests
  exist because of this.
- **Switch-off tests identify average effects**, not the shape of the curve near today's spend.
- **Flat spend across the year.** The optimiser sets annual totals; seasonal timing is not optimised.
- **No channel interactions.** Each channel's lift is additive within its business.
- **Inputs from management.** Margins, payback targets, B2 capacity and the 24-month horizon are assumptions
  (`configs/config.yaml`); section 7 shows how much they matter.
- **Profit levels are overstated** by the model; compare plans by difference, not level.

## 11. Reproducibility

- Python 3.11; dependencies pinned in `uv.lock`; one seed ({cfg.raw["seed"]}) drives the simulation; every random step
  uses its own stream.
- `uv run mbo all` rebuilds everything from nothing in about 15 minutes. Money sums are rounded in SQL and every
  query that feeds an output is ordered, so rebuilds are byte-identical.
- `reports/manifest.csv` records a SHA-256 hash of every committed output. `uv run mbo verify` checks the files
  against it in seconds; `uv run mbo reproduce` rebuilds everything and then checks.
- CI runs ruff, mypy and the tests on a small simulated fixture.
"""
    return _write(cfg.path("reports_dir") / "technical_report.md", text)


# ------------------------------------------------------------------------------- model card, monitoring


def write_model_card(n: Numbers, cfg: Config, truth: dict[str, Any] | None) -> Path:
    v = n.v
    rk = cfg.section("budget")["risk"]
    perf = ""
    if truth:
        perf = f"""
**Against the simulation's truth** ([technical report, section 9](../reports/technical_report.md#9-validation-against-the-simulations-truth)):
- the plan truly gains {_signed(truth["true_gain"])} a year vs the model's {_signed(v["plan_gain"])} ({truth["share_achievable"]:.0%} of what is achievable);
- {truth["curves_in_band"]} of {truth["curves_total"]} next-dollar estimates fall inside the model's 80% band; on untested lines the
  estimate is {truth["curve_ratio_untested"][0]:.1f}x to {truth["curve_ratio_untested"][1]:.1f}x the truth;
- all {truth["nr_total"]} no-regret directions are right; {truth["mostly_right"]} of {truth["mostly_total"]} "mostly" directions are.
"""
    text = f"""# Model card: marketing-mix model and budget optimiser

{DISCLAIMER}

## Model details

- **What it is.** One marketing-mix model per business (weekly new customers = organic base × (1 + paid lift),
  with adstock and Hill saturation per channel), calibrated to {len(v["calibration"])} region budget tests, with
  {rk["uncertainty_draws"]} bootstrap refits. A constrained optimiser (SLSQP) chooses the split across the
  {v["n_lines"]} lines. Code: `src/marketing_budget/optimisation/`.
- **Owner.** Analytics. **Inputs owned by** Finance (margins, payback targets, budget), Sales (B2 capacity),
  Marketing (channel limits). All in `configs/config.yaml`.
- **Version.** Rebuilt from seed {cfg.raw["seed"]}; outputs pinned by `reports/manifest.csv`.

## Intended use

- Deciding the annual split of a fixed paid-acquisition budget across channels and businesses.
- Ranking where the next test should go (the money at stake on each uncertain line).
- Comparing plans by their *difference* in expected contribution.

## Not intended for

- Reporting what a channel "achieved" (use randomised tests).
- Weekly bidding or seasonal timing (the model sets annual totals).
- Quoting absolute profit (the level is overstated; differences are more reliable).
- Lines or businesses outside the training data, or spend far outside the range seen (more than about
  {v["guardrail"]:.0%} from last year on lines without a test).

## Training data

156 weeks of weekly spend and CRM customers per line (SYNTHETIC), CRM organic-source customers for the
organic floor, and {len(v["calibration"])} region tests for calibration. Customer values from the retention models.

## Evaluation

- **Calibration:** {v["n_cal_in_band"]} of {len(v["calibration"])} measured test effects fall inside the model's 10-90% range.
- **Robustness:** {len(v["no_regret"])} of {v["n_lines"]} line directions hold in all {v["n_scenarios"]} alternative scenarios.
- **Plan:** expected gain {_signed(v["plan_gain"])} a year vs last year's split; worst-10% average {_signed(v["plan_down_gain"])}.
{perf}
## Limitations and risks

- History-only response curves lean optimistic and their uncertainty bands are too narrow.
- Switch-off tests fix a channel's average effect, not the slope at today's spend.
- No channel interactions, no seasonal timing, no competitor response.
- B2 is capped by sales capacity, so B2 curves are only identified up to that cap.
- Mitigations: ±{v["guardrail"]:.0%} guardrail on untested lines, a reserve for unproven increases, a downside
  constraint, and a test plan targeted at the most uncertain money.

## Monitoring

See [monitoring_plan.md](monitoring_plan.md). Refit when a new test reads out, when a monitor fires, or
quarterly, whichever comes first.
"""
    return _write(cfg.path("docs_dir") / "model_card.md", text)


def monitoring_table(n: Numbers, cfg: Config) -> pd.DataFrame:
    v = n.v
    dq = cfg.section("data_quality")
    fc = cfg.section("forecasting")
    rows = [
        (
            "Data",
            "Tracking outage",
            f"Platform reports 0 conversions while the CRM has {dq['outage_min_crm_customers']}+ customers on the line",
            "Weekly build",
            "Exclude the week from platform metrics; raise with the ad platform",
            "Data Engineer",
        ),
        (
            "Data",
            "Attribution change",
            f"Platform/CRM ratio shifts by more than {dq['shift_min_change']:.0%} (p < {dq['shift_alpha']}, at least {dq['shift_min_segment_weeks']} weeks each side)",
            "Weekly build",
            "Freeze platform-based reporting for the line; investigate the tag",
            "Data Engineer",
        ),
        (
            "Data",
            "Duplicate leads",
            f"Share of leads repeating a contact within {dq['duplicate_window_days']} days rises above today's {v['dup_rate']:.1%}",
            "Weekly build",
            "Fix at entry; B2 lead counts use de-duplicated data",
            "Data Engineer",
        ),
        (
            "Data",
            "Cost restatement",
            f"Spend changes by more than {dq['restatement_tolerance']:.0%} after first report",
            "Weekly build",
            "Use the restated cost; close weeks only after restatements",
            "Data Engineer",
        ),
        (
            "Forecast",
            "Forecast miss",
            f"Actual quarterly customers or contribution outside the {fc['interval_level']:.0%} range",
            "Quarterly",
            "Investigate; refit the forecast; check for an unlogged change",
            "Analytics",
        ),
        (
            "Model",
            "Calibration break",
            "A new test's measured effect falls outside the model's 10-90% range for that change",
            "Each test read-out",
            "Refit with the new test; re-run the optimiser and sensitivity",
            "Analytics",
        ),
        (
            "Model",
            "Plan tracking",
            "Contribution after ad spend below the plan's pessimistic case for two months running",
            "Monthly",
            "Review the lines that moved; check holdout results",
            "CFO, Analytics",
        ),
        (
            "Business",
            "B2 capacity",
            f"Qualified leads above {v['b2_capacity']:.0f} a week for four weeks",
            "Weekly",
            "Cap B2 spend or hire; leads above capacity are wasted",
            "B2 BU Director",
        ),
        (
            "Business",
            "Payback",
            "Any business's incremental-CAC payback above its target",
            "Quarterly",
            "Shift budget out of the business's lowest-return line",
            "CFO",
        ),
        (
            "Reporting",
            "Commentary checks",
            "Any sentence fails the code checks after the retry, or a draft ships without sign-off",
            "Monthly",
            "Template fallback; reviewer must approve the exact draft",
            "Analytics",
        ),
    ]
    return pd.DataFrame(rows, columns=["area", "monitor", "fires when", "checked", "response", "owner"])


def write_monitoring_plan(n: Numbers, cfg: Config) -> Path:
    mon = monitoring_table(n, cfg)
    mo = cfg.section("monitoring")
    mon.to_csv(cfg.path("tables_dir") / "monitoring_plan.csv", index=False)
    text = f"""# Monitoring plan

What is watched after the plan is adopted, when an alert fires, and who acts. Data checks run on every build
(`uv run mbo quality`); thresholds come from `configs/config.yaml`.

{_md(mon)}

**Refit schedule.** The response model and optimiser are refitted when a test reads out, when a model or forecast
monitor fires, or quarterly. Each refit re-runs the sensitivity analysis before any change to the plan.

**Holdouts.** Each line whose spend moved by more than {mo["holdout_min_move"]:.0%} keeps a {mo["holdout_share"]:.0%} region
holdout for {mo["holdout_weeks"]} weeks, so the effect of the move is measured by experiment rather than inferred from
the model.
"""
    return _write(cfg.path("docs_dir") / "monitoring_plan.md", text)


def write_final(con: duckdb.DuckDBPyConnection, cfg: Config, truth: dict[str, Any] | None) -> list[Path]:
    n = final_numbers(con, cfg)
    return [
        write_executive_memo(n, cfg, truth),
        write_recommendations(n, cfg),
        write_technical_report(n, cfg, truth),
        write_model_card(n, cfg, truth),
        write_monitoring_plan(n, cfg),
    ]
