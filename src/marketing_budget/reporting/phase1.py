"""Phase 1 reports: data quality (reports/data_quality.md) and customer value (reports/customer_value.md)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from marketing_budget.analysis.retention import ALL, RetentionResults
from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.data.quality import QualityReport


def _md(df: pd.DataFrame, floatfmt: str = ",.3f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def _money(x: object) -> str:
    x = float(x)  # type: ignore[arg-type]
    return f"${x:,.0f}" if abs(x) >= 1000 else f"${x:,.2f}"


def _write(cfg: Config, name: str, text: str) -> Path:
    path = cfg.path("reports_dir") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_quality_report(
    q: QualityReport,
    con: duckdb.DuckDBPyConnection,
    cfg: Config,
    score: pd.DataFrame | None = None,
    false_flags: pd.DataFrame | None = None,
) -> Path:
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    q.checks.to_csv(tables / "dq_checks.csv", index=False)
    q.issues.to_csv(tables / "dq_issues.csv", index=False)
    q.lineage.to_csv(tables / "lineage.csv", index=False)

    ratios = query_df(
        con,
        "SELECT business, channel, sum(platform_conversions) FILTER (WHERE NOT attribution_changed "
        "AND NOT tracking_outage) / sum(crm_customers) FILTER (WHERE NOT attribution_changed AND NOT tracking_outage) "
        "AS platform_to_crm_ratio, sum(spend) / sum(crm_customers) AS last_click_cac, "
        "sum(spend) / sum(platform_conversions) FILTER (WHERE NOT tracking_outage) AS platform_cac "
        "FROM line_week GROUP BY ALL ORDER BY business, channel",
    )
    ratios.to_csv(tables / "dq_platform_vs_crm.csv", index=False)

    shift = q.shifts[q.shifts["detected"]]
    shift_text = ""
    if len(shift):
        s = shift.iloc[0]
        cac = query_df(
            con,
            "SELECT week_start >= ? AS after, sum(spend) / sum(crm_customers) AS last_click_cac, "
            "sum(spend) / sum(platform_conversions) AS platform_cac FROM line_week "
            "WHERE business = ? AND channel = ? AND NOT tracking_outage GROUP BY 1 ORDER BY 1",
            [s["shift_week_start"], s["business"], s["channel"]],
        )
        before, after = cac.iloc[0], cac.iloc[1]
        shift_text = (
            f"From the week of {s['shift_week_start']:%d %b %Y}, the ad platform for {s['business']} "
            f"{s['channel'].replace('_', ' ')} reports {abs(s['change']):.0%} fewer conversions per customer "
            f"the CRM credits to it. On platform numbers its cost per customer rose from "
            f"${before['platform_cac']:,.0f} to ${after['platform_cac']:,.0f} "
            f"({after['platform_cac'] / before['platform_cac'] - 1:+.0%}). On the CRM's own last-click numbers "
            f"it moved from ${before['last_click_cac']:,.0f} to ${after['last_click_cac']:,.0f} "
            f"({after['last_click_cac'] / before['last_click_cac'] - 1:+.0%}). Most of the "
            "apparent decline is the tracking, not the channel."
        )
    min_ratio, max_ratio = ratios["platform_to_crm_ratio"].min(), ratios["platform_to_crm_ratio"].max()
    n_pass = int(q.checks["passed"].sum())

    validation = ""
    if score is not None:
        found = int(score["detected"].sum())
        validation = f"""
## Validation against the SYNTHETIC ground truth

The checks above use observable data only. Scoring them against the issues deliberately injected into the
simulation: **{found} of {len(score)} injected issues detected**, {0 if false_flags is None else len(false_flags)}
flags raised where nothing was injected.

{_md(score)}
"""

    text = f"""# Data quality and lineage (SYNTHETIC data)

## Summary for management

1. **Business question.** Can the marketing numbers be trusted for budget decisions, and if not, which ones
   are wrong, where and since when?
2. **Why it matters.** Budgets follow the numbers. A broken tracking tag looks exactly like a channel losing
   performance, and duplicate leads look like growth. If the inputs are wrong, every later analysis is
   precisely wrong.
3. **What this establishes.** {n_pass} of {len(q.checks)} structural checks pass (completeness, funnel order,
   reconciliation between tables). The issue scan found {len(q.issues)} problems: {", ".join(sorted(set(q.issues["issue"].str.replace("_", " "))))}.
4. **In business terms.** {shift_text} Separately, ad platforms routinely claim more conversions than the
   company's own CRM credits to them: between {min_ratio:.2f}x and {max_ratio:.2f}x across channels, highest
   for display and social, where platforms count people who only saw an ad.
5. **Action to consider.** Judge channels on the CRM's numbers, not the platforms'. Repair the
   {", ".join(sorted(set(shift["business"] + " " + shift["channel"].str.replace("_", " "))))} conversion tag.
   De-duplicate B2 demo requests at the point of entry. Close each week's media costs only after
   restatements have arrived.
6. **Assumptions and limits.** The checks only find problems they have a rule for. A problem inside the CRM
   itself would not be found here. CRM last-click credit is more honest than platform credit but still not
   causal: it includes customers who would have bought anyway. That gap is measured in phases 3 and 4.

## Lineage (row counts at each layer)

Raw tables are the generated Parquet files. Clean tables remove duplicates and add flags; metric tables are
what forecasts, the optimiser, the dashboard and the AI commentary read (D-007).

{_md(q.lineage, ",.0f")}

## Structural checks

{_md(q.checks)}

## Issues found

{_md(q.issues)}

Flagged weeks stay in the data. `line_week.any_dq_flag` lets each later step decide whether to exclude them.

## Platform-reported vs CRM last-click conversions

Platform-to-CRM ratio outside the flagged weeks. A ratio above 1 means the platform claims customers the CRM
credits to another source, or to none.

{_md(ratios, ",.2f")}

## Attribution change test (all lines)

Change point in log(platform / CRM) on 4-week sums, refined to the week. Bonferroni-adjusted significance
across {len(q.shifts)} lines, plus a minimum size of change. Only lines meeting both are flagged.

{_md(q.shifts[["business", "channel", "shift_week_start", "ratio_before", "ratio_after", "change", "p_value", "detected"]])}
{validation}"""
    return _write(cfg, "data_quality.md", text)


def write_customer_value_report(res: RetentionResults, cfg: Config, score: pd.DataFrame | None = None) -> Path:
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    res.estimates.to_csv(tables / "customer_value_estimates.csv", index=False, float_format="%.6g")
    res.empirical.to_csv(tables / "customer_value_empirical_check.csv", index=False, float_format="%.6g")
    ue, v = cfg.section("unit_economics"), cfg.section("valuation")

    est = res.estimates
    allsrc = est[est["source"] == ALL].set_index("business")
    b1, b2, b3 = allsrc.loc["B1"], allsrc.loc["B2"], allsrc.loc["B3"]
    first_order = ue["B3"]["order_contribution"] - ue["B3"]["acquisition_cost"]
    repeat_share = 1 - first_order / b3["customer_value"]
    b2_annual = b2["survival_monthly"] ** 12
    aff = est[(est["business"] == "B1") & (est["source"] == "affiliates")].iloc[0]
    aff_gap = aff["customer_value"] / b1["customer_value"] - 1

    sub_cols = [
        "business",
        "source",
        "n_customers",
        "survival_first_month",
        "survival_monthly",
        "customer_value",
        "value_ci_low",
        "value_ci_high",
    ]
    ecom_cols = [
        "business",
        "source",
        "n_customers",
        "repeat_rate_first_month",
        "repeat_decay_monthly",
        "dispersion",
        "customer_value",
        "value_ci_low",
        "value_ci_high",
    ]
    validation = ""
    if score is not None:
        miss = score[~score["true_in_ci"]]
        miss_text = (
            "Intervals that miss: "
            + "; ".join(f"{r.business} {r.source} (error {r.error_pct:+.1%})" for r in miss.itertuples())
            + ". The intervals cover sampling error only, not the simplification of fitting one retention curve"
            " to a group whose customers behave differently (a CRM source mixes customers the channel caused with organic ones), and roughly 1 interval in 20 misses by chance."
            if len(miss)
            else ""
        )
        validation = f"""
## Validation against the SYNTHETIC ground truth

`true_value` is the true average value of the customers in each CRM source, a mix of customers the channel
caused and organic customers it was credited with. `true_incremental_value` is the value of the caused
customers alone: what a budget decision needs. {int(score["true_in_ci"].sum())} of {len(score)} intervals
contain the true value. Where the two true values differ (affiliates), the CRM-source estimate overstates
what the channel's own customers are worth, because the source mixes in organic buyers. {miss_text}

{_md(score)}
"""

    text = f"""# Customer value (SYNTHETIC data)

## Summary for management

1. **Business question.** What is a new customer worth to each business over {v["horizon_months"]} months, and does
   it depend on where the customer came from?
2. **Why it matters.** Customer value is the most a business can pay to acquire a customer and still profit.
   Every return figure in later phases is customers × this value ÷ spend, so an error here scales every
   recommendation.
3. **What this establishes.** Discounted contribution per new customer, after one-off acquisition costs:
   **B1 {_money(b1["customer_value"])}** (95% interval {_money(b1["value_ci_low"])}–{_money(b1["value_ci_high"])}),
   **B2 {_money(b2["customer_value"])}** ({_money(b2["value_ci_low"])}–{_money(b2["value_ci_high"])}),
   **B3 {_money(b3["customer_value"])}** ({_money(b3["value_ci_low"])}–{_money(b3["value_ci_high"])}).
   Customers acquired long enough ago to be watched for the full {v["horizon_months"]} months confirm these
   figures (table below).
4. **In business terms.** B1 loses {1 - b1["survival_first_month"]:.0%} of new subscribers after the first
   box; the customers who stay drive the value. B2 keeps {b2_annual:.0%} of customers a year, so one
   customer is worth as much as about {b2["customer_value"] / b1["customer_value"]:,.0f} B1 customers.
   For B3, {repeat_share:.0%} of a customer's value comes from repeat orders after the first. B1 customers
   credited to affiliates are worth {abs(aff_gap):.0%} {"less" if aff_gap < 0 else "more"} than average. Because the CRM also
   credits affiliates with organic buyers who clicked a coupon link last, the customers affiliates actually
   bring are probably worth less still.
5. **Action to consider.** Use these values as the ceiling on what each business pays for a customer *the
   advertising actually caused*. Don't compare them with platform-reported CAC: that would set a lower bar
   for channels that claim customers who would have come anyway.
6. **Assumptions and limits.** Contribution per box, licence and order is a finance input (assumption);
   retention is estimated from the data. Monthly churn after the first period is assumed constant; the
   full-horizon check supports this for the early cohorts. Values by acquisition source use the CRM's
   last-click source, which mixes in organic customers.

## How the estimates handle customers who have not finished their lifetime

Customers acquired recently are still active, and their future is unknown (right-censored). Each customer
counts only for the months actually observed: survival is estimated from observed month-to-month
transitions, and repeat orders from observed customer-months. Ignoring censoring would understate
retention, because only the early, already-ended lifetimes would count.

## Subscriptions (B1, B2): survival after the first month and monthly thereafter

{_md(est[est["model"] == "subscription"][sub_cols])}

## E-commerce (B3): repeat orders

Repeat order rate in month 1 and its monthly decay, from a Poisson model of orders per observable customer.
`dispersion` above 1 means order counts vary more than a Poisson model assumes; standard errors are widened
by that factor.

{_md(est[est["model"] == "ecommerce"][ecom_cols])}

## Check without the truth: fully observed cohorts

Customers acquired {res.empirical["cohorts_from"].min():%b %Y}–{res.empirical["cohorts_to"].max():%b %Y} were watched for the
full horizon. Their actual average discounted contribution is compared with the model's value for all cohorts.

{_md(res.empirical)}
{validation}"""
    return _write(cfg, "customer_value.md", text)
