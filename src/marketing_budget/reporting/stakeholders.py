"""Phase 8: stakeholder management simulation (reports/stakeholder_simulation.md).

An annual budget review with four people who want different things. Every number is computed here from the
validated SQL layer and the phase 1-5 outputs (`reports/tables`); none comes from the ground truth. The prose is
written for executives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.analysis.retention import ALL
from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.economics import customer_value
from marketing_budget.experiments.results import CHANNEL_NAMES
from marketing_budget.optimisation.inputs import LAST_52

NAMES = {"B1": "Hearth Box", "B2": "Ledgerline", "B3": "Atlas Outdoor"}


def _k(x: float) -> str:
    return f"-${abs(x) / 1e3:,.0f}k" if x < 0 else f"${x / 1e3:,.0f}k"


def _signed(x: float) -> str:
    return f"+{_k(x)}" if x >= 0 else _k(x)


def _more_fewer(x: float, noun: str) -> str:
    return f"{abs(100 * x):.0f}% {'more' if x >= 0 else 'fewer'} {noun}"


def _label(line: str) -> str:
    b, ch = line.split(".")
    return f"{b} {CHANNEL_NAMES.get(ch, ch)}"


@dataclass
class Numbers:
    """Everything the pack quotes, computed once so the text and the tests use the same values."""

    v: dict[str, Any]


def compute_numbers(con: duckdb.DuckDBPyConnection, cfg: Config) -> Numbers:
    t = cfg.path("tables_dir")
    v: dict[str, Any] = {}
    ev: dict[Any, dict[Any, Any]] = (
        pd.read_csv(t / "allocation_evaluation.csv").set_index("allocation").to_dict("index")
    )
    sq, rec = ev["status_quo"], ev["recommended"]
    v["plan_gain"] = float(rec["expected_profit"] - sq["expected_profit"])
    v["plan_down_gain"] = float(rec["downside_profit"] - sq["downside_profit"])
    v["roas_loss"] = float(ev["platform_roas"]["expected_profit"] - sq["expected_profit"])

    # budget curve: where profit peaks, and what the last and the next $200k earn
    curve = pd.read_csv(t / "sensitivity_budget_curve.csv")
    curve = curve[curve["solved"].astype(bool)]
    bc = {float(b): float(p) for b, p in zip(curve["budget"], curve["expected_profit"], strict=True)}
    total = float(cfg.section("budget")["annual_total"])
    v["best_budget"] = max(bc, key=lambda b: bc[b])
    v["best_minus_2m"] = max(bc.values()) - bc[total]
    v["last_200k_back"] = 1 + float(bc[total] - bc[total - 200_000]) / 200_000  # contribution per dollar
    v["next_200k_back"] = 1 + float(bc[total + 200_000] - bc[total]) / 200_000

    # payback in months of the model's incremental CAC, status quo vs recommended (phase 1 customer values)
    est = pd.read_csv(t / "customer_value_estimates.csv")
    est = est[est["source"] == ALL]
    ue, rate = cfg.section("unit_economics"), float(cfg.section("valuation")["annual_discount_rate"])
    pay = []
    for r in est.to_dict("records"):
        b = str(r["business"])
        econ = {k: float(x) for k, x in ue[b].items() if k != "model"}
        keys = ("survival_first_month", "survival_monthly", "repeat_rate_first_month", "repeat_decay_monthly")
        econ |= {k: float(r[k]) for k in keys if k in r and pd.notna(r[k])}
        cv = customer_value(str(ue[b]["model"]), econ, 60, rate)
        row = {"business": b, "target_months": int(cfg.section("valuation")["payback_target_months"][b])}
        for a, e in (("last_year_split", sq), ("recommended", rec)):
            cac = float(e[f"spend_{b}"] / e[f"incremental_customers_{b}"])
            row[f"incremental_cac_{a}"] = cac
            row[f"payback_months_{a}"] = cv.payback_months(cac)
        pay.append(row)
    v["payback"] = pd.DataFrame(pay)

    # the four lenses for retargeting, and the platform over-claim range
    att: dict[Any, dict[Any, Any]] = (
        pd.read_csv(t / "experiment_attribution_vs_causal.csv").set_index("experiment").to_dict("index")
    )
    r = att["retargeting_off"]
    v["rt_corr"], v["rt_platform"], v["rt_lastclick"], v["rt_causal"] = (
        float(r["correlation_per_1000"]),
        float(r["platform_per_1000"]),
        float(r["last_click_per_1000"]),
        float(r["causal_per_1000"]),
    )
    v["rt_causal_high"] = float(1000 * min(r["causal_ci_low"], r["causal_ci_high"]) / r["spend_change"])
    ratio = pd.read_csv(t / "dq_platform_vs_crm.csv")["platform_to_crm_ratio"]
    v["overclaim_max"] = float(ratio.max())

    # experiments
    ef_df = pd.read_csv(t / "experiment_effects.csv")
    ef = {
        (str(e), str(m)): float(x)
        for e, m, x in zip(ef_df["experiment"], ef_df["metric"], ef_df["relative_effect"], strict=True)
    }
    dec: dict[Any, dict[Any, Any]] = (
        pd.read_csv(t / "experiment_decisions.csv").set_index("experiment").to_dict("index")
    )
    v["lp_uplift"] = ef[("landing_page", "conversion rate")]
    v["lp_value"] = float(dec["landing_page"]["estimate"])
    v["rt_value"] = float(dec["retargeting_off"]["estimate"])
    v["rt_value_low"] = float(dec["retargeting_off"]["low"])
    v["li_leads"] = ef[("audience_targeting", "leads per $")]
    v["li_qual"] = ef[("audience_targeting", "qualified leads per $")]

    # B2: lead economics by channel over the last 52 weeks, and sales capacity
    b2 = query_df(
        con,
        f"SELECT channel, sum(spend) AS spend, sum(crm_leads) AS leads, sum(crm_customers) AS customers "
        f"FROM line_week WHERE business = 'B2' AND {LAST_52} GROUP BY channel ORDER BY channel",
    )
    b2["cost_per_lead"] = b2["spend"] / b2["leads"]
    b2["lead_to_customer"] = b2["customers"] / b2["leads"]
    v["b2_lines"] = b2
    b2["cost_per_customer"] = b2["spend"] / b2["customers"]
    # the channel whose leads convert worst: cheap per lead, expensive per customer
    worst = b2.iloc[int(np.argmin(b2["lead_to_customer"].to_numpy()))]
    best = b2.iloc[int(np.argmax(b2["lead_to_customer"].to_numpy()))]
    v["b2_worst"] = CHANNEL_NAMES.get(str(worst["channel"]), str(worst["channel"]))
    v["b2_worst_cap"] = v["b2_worst"][0].upper() + v["b2_worst"][1:]
    v["b2_worst_cpl"] = float(worst["cost_per_lead"])
    v["b2_worst_cpl_rank"] = int((b2["cost_per_lead"] < worst["cost_per_lead"]).sum()) + 1
    v["b2_worst_conv"] = float(worst["lead_to_customer"])
    v["b2_worst_cpc"] = float(worst["cost_per_customer"])
    v["b2_best"] = CHANNEL_NAMES.get(str(best["channel"]), str(best["channel"]))
    v["b2_best_cpc"] = float(best["cost_per_customer"])
    v["b2_best_conv"] = float(b2["lead_to_customer"].max())
    q = query_df(con, f"SELECT sum(qualified_leads) / 52 AS q FROM business_week WHERE business = 'B2' AND {LAST_52}")
    v["b2_qualified_per_week"] = float(q["q"].iloc[0])
    v["b2_capacity"] = float(cfg.section("budget")["sales_capacity"]["B2"]["max_qualified_leads_per_week"])
    pc = pd.read_csv(t / "policy_costs.csv").set_index("policy_removed")["expected_profit_gain"]
    v["capacity_value"] = float(pc["sales_capacity"])
    v["guardrail_cost"] = float(pc["untested_guardrail"])

    # data trust
    dq = pd.read_csv(t / "dq_issues.csv")
    v["n_issues"] = len(dq)
    dup = query_df(con, "SELECT sum(duplicate_leads) / sum(leads_recorded) AS r FROM crm_clean WHERE business = 'B2'")
    v["dup_rate"] = float(dup["r"].iloc[0])
    shift = query_df(con, "SELECT * FROM dq_attribution_shift WHERE detected")
    s0 = shift.iloc[0]
    v["shift_line"] = f"{s0['business']}.{s0['channel']}"
    v["shift_date"] = pd.Timestamp(s0["shift_week_start"])
    v["shift_change"] = float(s0["change"])

    # the plan line by line, with sensitivity verdicts; the reserve = increases resting on history alone
    al = pd.read_csv(t / "allocation_by_line.csv")
    ver = pd.read_csv(t / "sensitivity_line_verdicts.csv").set_index("line")
    al["change"] = al["recommended"] - al["status_quo"]
    al["verdict"] = al["line"].map(ver["verdict"])
    al["evidence"] = al["line"].map(ver["evidence"])
    v["allocation"] = al
    v["moved"] = float(al.loc[al["change"] > 0, "change"].sum())
    # moves made now: experiment-backed and the same direction under every assumption (phase 5)
    firm = al["evidence"].eq("experiment") & al["verdict"].str.startswith("no-regret")
    now = al[firm & (al["change"].abs() > 1000)]
    v["now_moves"] = "; ".join(f"{_label(r['line'])} {_signed(r['change'])}" for r in now.to_dict("records"))
    # increases held back: history-only lines, and any line whose direction depends on assumptions
    held = al[(al["change"] > 0) & ~firm]
    v["reserve"] = float(held["change"].sum())
    v["reserve_lines"] = ", ".join(
        f"{_label(x)} ({_signed(c)})" for x, c in zip(held["line"], held["change"], strict=True)
    )
    v["depends_lines"] = ", ".join(_label(x) for x in al.loc[al["verdict"] == "depends on assumptions", "line"])
    v["b2_change"] = float(al.loc[al["line"].str.startswith("B2."), "change"].sum())
    nt = pd.read_csv(t / "next_tests.csv").head(3)
    v["next_tests"] = ", ".join(_label(f"{b}.{c}") for b, c in zip(nt["business"], nt["channel"], strict=True))
    return Numbers(v)


def requirements_matrix(n: Numbers) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stakeholder": "Marketing Director",
                "wants": "More budget to grow customer volume",
                "watches": "Platform ROAS, new customers, share of voice",
                "worry": "Cuts to channels that 'clearly work' on the dashboards",
                "needs from the analysis": "Where the next dollar works hardest, by channel",
                "decision rights": "Proposes channel split",
                "success looks like": "More profitable customers, a plan the team can execute",
            },
            {
                "stakeholder": "CFO",
                "wants": "Cash efficiency and fast payback",
                "watches": "Contribution after ad spend, payback months, cash out",
                "worry": "Spend justified by numbers that do not tie to the P&L",
                "needs from the analysis": "Incremental, not attributed, return; the downside case",
                "decision rights": "Sets total budget and payback targets",
                "success looks like": "Every dollar defensible; targets met; no surprises",
            },
            {
                "stakeholder": "Business Unit Director (B2 Ledgerline)",
                "wants": "Leads the sales team can close",
                "watches": "Qualified leads, win rate, sales workload",
                "worry": "Cheap leads that waste sales time",
                "needs from the analysis": "Qualified leads and customers per dollar, not leads per dollar",
                "decision rights": "Owns sales capacity and lead acceptance",
                "success looks like": f"Qualified leads within the {n.v['b2_capacity']:.0f}-a-week the team can work",
            },
            {
                "stakeholder": "Data Engineer",
                "wants": "Decisions on numbers that are measured reliably",
                "watches": "Tracking coverage, data freshness, reconciliation breaks",
                "worry": "Platform pixels and attribution changes silently moving the numbers",
                "needs from the analysis": "Clear metric definitions; which sources are trusted for what",
                "decision rights": "Owns pipelines and metric definitions",
                "success looks like": "One definition per metric, checked on every build",
            },
        ]
    )


def metric_framework() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (
                "Lead",
                "First identifiable action, de-duplicated (B2: same e-mail domain within 30 days)",
                "CRM",
                "BU Director",
                "Actual",
                "Never to judge a channel on its own",
            ),
            (
                "Qualified lead",
                "B1 checkout-ready; B2 sales-accepted; B3 checkout started",
                "CRM",
                "BU Director",
                "Actual",
                "Channel quality; sales workload",
            ),
            (
                "New customer",
                "First paid transaction",
                "CRM / billing",
                "Data Engineer",
                "Actual",
                "Volume targets, payback",
            ),
            (
                "Platform CAC / ROAS",
                "Spend per conversion as the ad platform reports it",
                "Ad platforms",
                "Marketing",
                "Attribution",
                "Tracking health only, never budgets",
            ),
            (
                "Last-click CAC",
                "Spend per customer whose last click was the channel",
                "CRM",
                "Marketing",
                "Attribution",
                "Day-to-day trends, with care",
            ),
            (
                "Incremental CAC / return",
                "Spend per customer the advertising caused",
                "Randomised tests",
                "Analytics",
                "Causal",
                "Keep, cut or scale a channel",
            ),
            (
                "Next-dollar (marginal) return",
                "Contribution from the next dollar on a channel",
                "Calibrated model",
                "Analytics",
                "Model",
                "Splitting the budget",
            ),
            (
                "Customer value",
                "Discounted contribution per new customer over 24 months",
                "Phase 1 cohorts",
                "Finance",
                "Model",
                "The most a customer is worth paying for",
            ),
            (
                "Payback months",
                "Months until a customer's contribution covers its CAC",
                "Finance + analytics",
                "CFO",
                "Model",
                "Cash planning, targets",
            ),
            (
                "Contribution profit",
                "Contribution from all customers minus acquisition costs and ad spend",
                "Finance",
                "CFO",
                "Actual",
                "The P&L line marketing answers to",
            ),
        ],
        columns=["metric", "agreed definition", "source", "owner", "evidence type", "used for"],
    )


def objections(n: Numbers) -> pd.DataFrame:
    v = n.v
    return pd.DataFrame(
        [
            {
                "objection": "Retargeting returns over 2x on the platform. Cutting it is madness.",
                "raised by": "Marketing Director",
                "response": (
                    f"The platform counts {v['rt_platform']:.0f} customers per $1,000; switching it off in randomly "
                    f"chosen regions lost about {v['rt_causal']:.1f} (at most {v['rt_causal_high']:.0f}). Most of what it claims "
                    f"would have bought anyway. Cutting it is worth {_k(v['rt_value'])} a year (at least {_k(v['rt_value_low'])})."
                ),
                "evidence": "Causal (region test)",
                "what would change our view": "A repeat test in peak season showing a larger loss",
            },
            {
                "objection": "Give us more budget and we will grow faster.",
                "raised by": "Marketing Director",
                "response": (
                    f"Volume would grow, profit would not: the last $200k of the $2M brings back "
                    f"${v['last_200k_back']:.2f} per dollar and another $200k would bring back ${v['next_200k_back']:.2f}. "
                    f"The model's profit peaks near ${v['best_budget'] / 1e6:.1f}M."
                ),
                "evidence": "Model (calibrated), checked in sensitivity analysis",
                "what would change our view": "Tests showing an untested channel earns well above $1 per dollar at the margin",
            },
            {
                "objection": "These are model numbers. How do I know the gain is real?",
                "raised by": "CFO",
                "response": (
                    f"Part of the plan rests on experiments, part on the model. The experiment-backed moves are made in "
                    f"full; increases we cannot yet prove ({_k(v['reserve'])}) are held as a reserve until tested. The pessimistic "
                    f"case is still {_k(v['plan_down_gain'])} a year better than last year's split."
                ),
                "evidence": "Causal for tested lines, model for the rest",
                "what would change our view": "A quarterly read-out below the pessimistic case",
            },
            {
                "objection": "LinkedIn lookalikes bring more leads for the same money. Switch.",
                "raised by": "Marketing Director",
                "response": (
                    f"They bring {_more_fewer(v['li_leads'], 'leads')} per dollar but "
                    f"{_more_fewer(v['li_qual'], 'qualified leads')}. "
                    "The sales team would work more leads to win fewer customers."
                ),
                "evidence": "Causal (split test), small sample",
                "what would change our view": "A longer test showing qualified leads per dollar at least level",
            },
            {
                "objection": f"{v['b2_worst_cap']} gives us some of the cheapest leads in B2.",
                "raised by": "Marketing Director",
                "response": (
                    f"{v['b2_worst_cap']} leads cost ${v['b2_worst_cpl']:,.0f} (number {v['b2_worst_cpl_rank']} cheapest) but only "
                    f"{100 * v['b2_worst_conv']:.1f}% become customers, so each customer costs ${v['b2_worst_cpc']:,.0f}, against "
                    f"${v['b2_best_cpc']:,.0f} through {v['b2_best']}. Cost per lead is the wrong measure."
                ),
                "evidence": "Actual (CRM)",
                "what would change our view": "Better lead scoring that lifts its conversion rate",
            },
            {
                "objection": "We cannot trust any of this: the tracking keeps breaking.",
                "raised by": "Data Engineer",
                "response": (
                    f"The checks found {v['n_issues']} problems, all now flagged in the data. Budget decisions use the CRM "
                    "and randomised tests, not platform pixels, so a broken pixel cannot move the budget."
                ),
                "evidence": "Actual (data-quality checks)",
                "what would change our view": "A break in the CRM itself (not yet covered by the checks)",
            },
            {
                "objection": "Cutting B2 advertising will starve sales.",
                "raised by": "BU Director",
                "response": (
                    f"B2 already produces about {v['b2_qualified_per_week']:.0f} qualified leads a week against a team that can "
                    f"work {v['b2_capacity']:.0f}. Ads beyond that buy leads nobody calls. Extra capacity, not extra ads, is "
                    f"what grows B2: the model values lifting the limit at up to {_k(v['capacity_value'])} a year."
                ),
                "evidence": "Actual (volume) and model (value)",
                "what would change our view": "Sales hiring or faster lead handling",
            },
        ]
    )


def write_stakeholder_report(n: Numbers, cfg: Config) -> Path:
    v = n.v
    tables = cfg.path("tables_dir")
    rm, mf, ob = requirements_matrix(n), metric_framework(), objections(n)
    rm.to_csv(tables / "stakeholder_requirements.csv", index=False)
    mf.to_csv(tables / "metric_framework.csv", index=False)
    ob.to_csv(tables / "stakeholder_objections.csv", index=False)
    pay = v["payback"]
    pay_show = pay[
        [
            "business",
            "target_months",
            "payback_months_last_year_split",
            "payback_months_recommended",
            "incremental_cac_last_year_split",
            "incremental_cac_recommended",
        ]
    ]
    shift_label = _label(v["shift_line"])
    worst_pb = pay.loc[pay["payback_months_last_year_split"].idxmax()]
    all_meet = bool((pay["payback_months_recommended"] <= pay["target_months"]).all())
    pay_sentence = (
        "Every business meets its payback target under the plan:"
        if all_meet
        else "Not every business meets its payback target under the plan; see the table:"
    )
    over = v["b2_qualified_per_week"] >= v["b2_capacity"]
    cap_sentence = (
        f"you're already getting {v['b2_qualified_per_week']:.0f}. More B2 advertising buys leads nobody can call."
        if over
        else f"you're getting {v['b2_qualified_per_week']:.0f}, close to the limit, and growing. More B2 advertising soon buys leads nobody can call."
    )
    b2 = v["b2_lines"].assign(channel=lambda d: d["channel"].map(CHANNEL_NAMES))
    b2_show = pd.DataFrame(
        {
            "channel": b2["channel"],
            "spend": b2["spend"].map(lambda x: f"${x / 1e3:,.0f}k"),
            "leads": b2["leads"].map(lambda x: f"{x:,.0f}"),
            "customers": b2["customers"].map(lambda x: f"{x:,.0f}"),
            "cost per lead": b2["cost_per_lead"].map(lambda x: f"${x:,.0f}"),
            "leads that become customers": b2["lead_to_customer"].map(lambda x: f"{100 * x:.1f}%"),
            "cost per customer": b2["cost_per_customer"].map(lambda x: f"${x:,.0f}"),
        }
    )

    text = f"""# Stakeholder management simulation (SYNTHETIC data)

## Summary for management

1. **Business question.** Four people with different priorities must agree next year's paid-acquisition plan.
   How does one body of analysis become a decision they can all sign?
2. **Why it matters.** Without a shared definition of "return", each person wins the argument with a
   different number. Dashboards would side with the Marketing Director, the P&L with the CFO, the CRM with
   the BU Director, and the tracking logs with the Data Engineer, and the budget would follow whoever argues
   best.
3. **What this establishes.** The conflicts are mostly about *which number*, not about goals. Once everyone
   uses one framework (attributed, incremental and next-dollar returns, kept separate), the disagreements
   narrow to two real questions: how much to bet on untested channels, and whether to expand B2's sales
   capacity.
4. **In business terms.**
   - The plan moves {_k(v["moved"])} between channels. The model expects it to add {_k(v["plan_gain"])} a year
     (pessimistic case {_k(v["plan_down_gain"])}).
   - Increasing the budget would not pay: profit peaks near ${v["best_budget"] / 1e6:.1f}M.
   - B2 is limited by its sales team, not by its advertising.
5. **Action to consider.** Approve the reconciled recommendation below:
   - experiment-backed moves now;
   - increases we cannot yet prove ({_k(v["reserve"])}) held as a reserve until tested;
   - a B2 sales-capacity business case;
   - a shared metric framework owned by the Data Engineer.
6. **Assumptions and limits.**
   - The meeting is simulated. The positions are typical of these roles, not quotes.
   - Every figure comes from the pipeline: actual where marked, otherwise model or test-based, as labelled.

## The setting

Annual budget review, 60 minutes. Attendees: CEO (chair), CFO, Marketing Director, B2 Business Unit Director,
Data Engineer, Head of Analytics (presenting). Pre-read: the executive memo, dashboard pages 1–3, and the
metric framework below.

## 1. Stakeholder requirements matrix

{rm.to_markdown(index=False)}

## 2. Common metric definition framework

The single most useful outcome of the meeting: one definition per word, with its source, owner, evidence
type and what it may be used for. It is the same framework the dashboard and the AI commentary use.

{mf.to_markdown(index=False)}

**The rule that settles most arguments:** attribution numbers (platform and last-click) describe what was
*credited*; they are for monitoring, not for budgets. Budgets move on causal and calibrated-model evidence.

## 3. Agenda

| Time | Item | Lead | Outcome needed |
|---|---|---|---|
| 0–5 | Purpose: agree next year's split and how we will judge it | CEO | Shared goal: profit, not volume or ROAS |
| 5–15 | One framework for "return" (section 2) | Head of Analytics, Data Engineer | Definitions accepted |
| 15–30 | What the tests and the model say (findings below) | Head of Analytics | Questions answered |
| 30–45 | The disputes: budget size, retargeting, B2 leads and capacity | CEO facilitates | Positions heard against the evidence |
| 45–55 | Reconciled recommendation | Head of Analytics | Decision, or a named open question |
| 55–60 | Measures of success and review dates | CFO | Owners and dates |

## 4. The meeting, simulated

**Marketing Director:** "The dashboards are clear: retargeting returns more than twice what it costs, and
brand search is our best channel. Give us more budget and we'll grow."

**Head of Analytics:** "The dashboards are counting customers who'd have bought anyway. For retargeting:
history suggests {v["rt_corr"]:.0f} customers per $1,000, the platform reports {v["rt_platform"]:.0f}, our CRM
credits {v["rt_lastclick"]:.0f}. When we switched it off in randomly chosen regions, we lost about
{v["rt_causal"]:.1f}. Each lens strips out more of the customers who were coming anyway."

**CFO:** "So what is it actually worth?"

**Head of Analytics:** "Switching retargeting off is worth {_k(v["rt_value"])} a year; at least
{_k(v["rt_value_low"])} even in the cautious case. That's a test result, not a model guess."

**Marketing Director:** "Fine, but the budget overall: more money still means more customers."

**Head of Analytics:** "More customers, yes. Not more profit. At $2M the last $200k brings back
${v["last_200k_back"]:.2f} per dollar, and another $200k would bring back ${v["next_200k_back"]:.2f}. On the
model, profit peaks near ${v["best_budget"] / 1e6:.1f}M. The money is better moved than added."

**BU Director (B2):** "And please don't send me more cheap leads. Half of them never pick up the phone."

**Head of Analytics:** "You're right, and the data backs you. {v["b2_worst_cap"]} leads cost ${v["b2_worst_cpl"]:,.0f} each,
among your cheapest, but only {100 * v["b2_worst_conv"]:.1f}% become customers: ${v["b2_worst_cpc"]:,.0f} per customer, against
${v["b2_best_cpc"]:,.0f} through {v["b2_best"]}. The LinkedIn lookalike test brought {_more_fewer(v["li_leads"], "leads")} per dollar
and {_more_fewer(v["li_qual"], "qualified ones")}. Bigger point: your team works about {v["b2_capacity"]:.0f} qualified leads a week, and {cap_sentence}"

**BU Director (B2):** "So the constraint is my team, not the ads."

**Head of Analytics:** "Exactly. The model values lifting that limit at up to {_k(v["capacity_value"])} a year. That's
the ceiling for a hiring case, before salaries."

**Data Engineer:** "Before we celebrate, the platform numbers have been unreliable all year."

**Head of Analytics:** "Agreed, and that's why we didn't use them. The checks found {v["n_issues"]} problems. The worst
is the tracking change on {shift_label} from {v["shift_date"]:%d %b %Y}: the platform started reporting
{abs(100 * v["shift_change"]):.0f}% fewer conversions per CRM customer. On platform numbers the channel looked
like it was failing; it wasn't. Budgets now run on the CRM and on tests, so a broken pixel can't move them."

**CFO:** "And if the model is wrong?"

**Head of Analytics:** "Then the plan limits the damage. Channels we've tested move in full. Channels we
haven't move by at most 25%, and the increases we can't yet prove ({_k(v["reserve"])}) stay in reserve until a test
supports them. Even the pessimistic case is {_k(v["plan_down_gain"])} a year better than last year's split.
The guardrail costs {_k(v["guardrail_cost"])} *on paper*, by the model's own reckoning, and that's the paper
we trust least."

**CEO:** "Then the decision is the split, the reserve, the B2 capacity case and the tracking fixes. Owners and
dates, please."

## 5. What each stakeholder needs to know

**Marketing Director.** Your best channels are not the ones the dashboards show.
- Experiment-backed moves to make now: {v["now_moves"]}.
- The new landing page lifts conversion {100 * v["lp_uplift"]:+.1f}% ({_k(v["lp_value"])} a year): launch it.
- Next tests: {v["next_tests"]}. Each one, if positive, releases reserve budget to that channel.

**CFO.** The plan adds {_k(v["plan_gain"])} a year by the model, {_k(v["plan_down_gain"])} in the pessimistic case, with the
reserve held back until tests support it. {pay_sentence}

{pay_show.to_markdown(index=False, floatfmt=",.1f")}

Last year's split was slowest in {worst_pb["business"]} ({worst_pb["payback_months_last_year_split"]:.0f} months). A payback of 0 months
means the first order already covers the acquisition cost. These are model-based CACs (customers the advertising caused),
higher than the blended CACs on the dashboard, which also count customers who came without ads.

**BU Director (B2).** Judge channels on qualified leads and customers per dollar, never leads per dollar.
B2 ad spend changes by {_signed(v["b2_change"])} under the plan, because ads beyond sales capacity buy nothing. The
capacity case is worth up to {_k(v["capacity_value"])} a year by the model.

Last 52 weeks, CRM last-click (attribution, not incremental):

{b2_show.to_markdown(index=False)}

**Data Engineer.**
- {v["n_issues"]} problems were found and flagged in the data, including {100 * v["dup_rate"]:.1f}% duplicate B2 leads and
  the {shift_label} tracking change.
- Platforms claim up to {v["overclaim_max"]:.2f}x the conversions the CRM credits.
- You own the metric framework. The dashboard and the AI commentary read from the same SQL layer, and a test
  fails if a dashboard column changes.

## 6. Objections and responses

{ob.to_markdown(index=False)}

## 7. Reconciled recommendation

| # | Decision | Satisfies | Evidence |
|---|---|---|---|
| 1 | Make the experiment-backed moves now: {v["now_moves"]} | CFO (proven), Marketing (moves money to what works) | Causal |
| 2 | Hold the increases we cannot yet prove ({_k(v["reserve"])}: {v["reserve_lines"]}) as a reserve, released line by line when a test shows the next dollar earns more than it costs. {v["depends_lines"]} stays at last year's level until a part-way cut is tested | Marketing (budget not cut), CFO (cash only on evidence) | Model, to be tested |
| 3 | Keep the total at $2.0M as a ceiling, not a target. Do not increase it: profit peaks near ${v["best_budget"] / 1e6:.1f}M | CFO | Model, sensitivity-tested |
| 4 | B2: no extra advertising until sales capacity grows; prepare a hiring case (worth up to {_k(v["capacity_value"])} a year before cost); keep the job-title LinkedIn audience; judge on qualified leads and customers | BU Director, CFO | Actual, causal and model |
| 5 | Launch the new landing page ({_k(v["lp_value"])} a year) | All | Causal |
| 6 | Fix the {shift_label} conversion tag, de-duplicate B2 forms at entry, close cost data after restatements, adopt the metric framework (Data Engineer owns it) | Data Engineer, everyone downstream | Actual |
| 7 | Review quarterly against: incremental contribution, payback by business, qualified leads within capacity, test read-outs. Triggers: a result below the pessimistic case reopens the plan | CEO, CFO | — |

## 8. Communicating uncertainty without undermining confidence

1. **Lead with the decision, then the range.** "Cut retargeting: it is worth {_k(v["rt_value"])} a year, at least
   {_k(v["rt_value_low"])}", not "the estimate is uncertain, but…".
2. **Label each number once, by where it came from.** Actual, test, model or assumption. People trust a number
   more when they know what kind it is.
3. **Say which conclusions do not depend on the uncertain part.** The no-regret moves hold under every
   assumption we tried; say so. Confidence comes from robustness, not from narrow intervals.
4. **Turn uncertainty into a plan, not a caveat.** The reserve, the guardrail and the next tests are how the
   plan handles what we do not know. Uncertainty becomes a schedule of decisions.
5. **Pre-agree what would change the plan.** Each objection above has a "what would change our view". Agreeing
   these in advance keeps a bad quarter from becoming a debate about the method.
6. **Don't hedge every sentence.** One clear statement of the main limits, in the place they matter, is more
   credible than qualifiers everywhere.
"""
    path = cfg.path("reports_dir") / "stakeholder_simulation.md"
    path.write_text(text, encoding="utf-8")
    return path
