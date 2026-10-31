"""Data-quality checks on the SQL layer.

* structural checks: completeness, no negatives, funnel order, reconciliation between tables
* issue detection: tracking outages, cost restatements, duplicate leads (all flagged in SQL), and
  attribution changes, detected here as a change point in the platform-to-CRM conversion ratio

Every check uses observable data only. Scoring against the injected issues is in validation/data_quality.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from marketing_budget.config import Config
from marketing_budget.data.db import query_df, table_count


def _best_split(y: np.ndarray, min_seg: int) -> tuple[int, float]:
    """Index that splits y into two segments with the smallest total squared error; returns (k, p-value)."""
    n = len(y)
    best_k, best_sse = -1, np.inf
    for k in range(min_seg, n - min_seg + 1):
        a, b = y[:k], y[k:]
        sse = float(((a - a.mean()) ** 2).sum() + ((b - b.mean()) ** 2).sum())
        if sse < best_sse:
            best_k, best_sse = k, sse
    a, b = y[:best_k], y[best_k:]
    if a.std() == 0 and b.std() == 0:
        return best_k, 1.0 if a.mean() == b.mean() else 0.0
    return best_k, float(stats.ttest_ind(a, b, equal_var=False).pvalue)


def detect_attribution_shifts(con: duckdb.DuckDBPyConnection, cfg: Config) -> pd.DataFrame:
    """For each line, test for one lasting change in platform conversions / CRM customers.

    The ratio is computed on 4-week sums to steady small counts, excluding outage weeks. A line is flagged when
    the change point is significant after a Bonferroni correction across lines *and* the ratio moves by more
    than `shift_min_change`. The search for the best split inflates significance, so the size threshold
    matters as much as the p-value.
    """
    dq = cfg.section("data_quality")
    df = query_df(
        con,
        "SELECT business, channel, week_start, platform_conversions, crm_customers, tracking_outage "
        "FROM line_week_base ORDER BY business, channel, week_start",
    )
    lines = df.groupby(["business", "channel"])
    alpha = float(dq["shift_alpha"]) / lines.ngroups
    min_seg = max(int(dq["shift_min_segment_weeks"]) // 4, 2)
    rows = []
    for (biz, ch), g in lines:
        g = g[~g["tracking_outage"]].reset_index(drop=True)
        block = np.arange(len(g)) // 4
        agg = g.groupby(block).agg(
            week_start=("week_start", "first"), plat=("platform_conversions", "sum"), crm=("crm_customers", "sum")
        )
        y = np.log((agg["plat"].to_numpy() + 0.5) / (agg["crm"].to_numpy() + 0.5))
        kb, p = _best_split(y, min_seg)
        # Refine the date at weekly resolution within one block either side of the 4-week split.
        yw = np.log((g["platform_conversions"].to_numpy() + 0.5) / (g["crm_customers"].to_numpy() + 0.5))
        cand = range(max((kb - 1) * 4, 1), min((kb + 1) * 4, len(g) - 1) + 1)
        k = min(
            cand, key=lambda i: float(((yw[:i] - yw[:i].mean()) ** 2).sum() + ((yw[i:] - yw[i:].mean()) ** 2).sum())
        )
        plat, crm = g["platform_conversions"].to_numpy(), g["crm_customers"].to_numpy()
        before = plat[:k].sum() / max(crm[:k].sum(), 1)
        after = plat[k:].sum() / max(crm[k:].sum(), 1)
        change = after / before - 1 if before > 0 else np.nan
        rows.append(
            {
                "business": biz,
                "channel": ch,
                "shift_week_start": g["week_start"].iloc[k],
                "ratio_before": before,
                "ratio_after": after,
                "change": change,
                "p_value": p,
                "detected": bool(p < alpha and abs(change) > float(dq["shift_min_change"])),
            }
        )
    out = pd.DataFrame(rows)
    out["shift_week_start"] = pd.to_datetime(out["shift_week_start"]).dt.date
    return out


@dataclass
class QualityReport:
    checks: pd.DataFrame  # check, passed, detail
    issues: pd.DataFrame  # issue, business, channel, first_week, last_week, n_weeks, detail
    lineage: pd.DataFrame  # table, layer, rows
    shifts: pd.DataFrame


def _flag_runs(df: pd.DataFrame, flag: str, issue: str, detail: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (biz, ch), g in df[df[flag]].groupby(["business", "channel"]):
        rows.append(
            {
                "issue": issue,
                "business": biz,
                "channel": ch,
                "first_week": g["week_start"].min(),
                "last_week": g["week_start"].max(),
                "n_weeks": len(g),
                "detail": detail,
            }
        )
    return rows


def build_quality_report(con: duckdb.DuckDBPyConnection, cfg: Config) -> QualityReport:
    meta = query_df(con, "SELECT * FROM synthetic_data_meta").iloc[0]
    n_weeks = int(meta["n_weeks"])
    n_lines = int(query_df(con, "SELECT count(DISTINCT business || channel) AS n FROM line_week")["n"].iloc[0])

    def check(name: str, sql: str, detail: str) -> dict[str, object]:
        bad = int(query_df(con, sql).to_numpy()[0, 0])
        return {"check": name, "passed": bad == 0, "failing_rows": bad, "detail": detail}

    checks = [
        {
            "check": "every line has every week",
            "passed": table_count(con, "line_week") == n_lines * n_weeks,
            "failing_rows": abs(table_count(con, "line_week") - n_lines * n_weeks),
            "detail": f"{n_lines} lines x {n_weeks} weeks",
        },
        check(
            "no negative spend or counts",
            "SELECT count(*) FROM line_week WHERE spend < 0 OR clicks < 0 OR impressions < 0 "
            "OR crm_leads < 0 OR platform_conversions < 0",
            "media and CRM",
        ),
        check(
            "funnel order: customers <= qualified <= leads",
            "SELECT count(*) FROM crm_clean WHERE qualified_leads > leads OR customers > qualified_leads",
            "CRM, by source and week (B2 on de-duplicated leads)",
        ),
        check(
            "clicks <= impressions",
            "SELECT count(*) FROM line_week WHERE clicks > impressions",
            "platform reports",
        ),
        check(
            "customer table reconciles to CRM counts",
            "SELECT count(*) FROM (SELECT business, count(*) AS n FROM synthetic_customers "
            "WHERE acquisition_date >= (SELECT first_week FROM synthetic_data_meta) GROUP BY 1) a "
            "JOIN (SELECT business, sum(customers) AS n FROM crm_clean GROUP BY 1) b USING (business) "
            "WHERE a.n <> b.n",
            "new customers per business",
        ),
        check(
            "every customer is active in their acquisition month",
            "SELECT count(*) FROM synthetic_customers c LEFT JOIN synthetic_customer_activity a "
            "ON a.customer_id = c.customer_id AND a.month_index = 0 WHERE a.customer_id IS NULL "
            "AND c.acquisition_date >= (SELECT first_week FROM synthetic_data_meta)",
            "activity month 0 (customers acquired in the window)",
        ),
        check(
            "no activity after the end of the data",
            "SELECT count(*) FROM synthetic_customer_activity a JOIN customer_lifetimes l USING (customer_id) "
            "WHERE a.month_index >= l.observable_months",
            "right-censoring respected",
        ),
        check(
            "B2 won leads reconcile to CRM customers",
            "SELECT count(*) FROM (SELECT week_start, source, count(*) FILTER (WHERE is_won) AS n "
            "FROM b2_leads_clean GROUP BY ALL) l JOIN crm_clean c USING (week_start, source) "
            "WHERE c.business = 'B2' AND l.n <> c.customers",
            "lead-level vs weekly",
        ),
    ]

    lw = query_df(con, "SELECT * FROM line_week ORDER BY business, channel, week_start")
    issues = _flag_runs(lw, "tracking_outage", "tracking_outage", "platform reports 0 conversions, CRM does not")
    issues += _flag_runs(lw, "cost_restated", "cost_restated", "spend changed after first report")
    # Duplicates across all CRM sources, organic included.
    dup = query_df(
        con,
        "SELECT business, week_start, sum(duplicate_leads) AS dups, sum(leads_recorded) AS recorded "
        "FROM crm_clean GROUP BY ALL",
    )
    for biz, g in dup.groupby("business"):
        hit = g[g["dups"] > 0]
        if len(hit):
            rate = g["dups"].sum() / g["recorded"].sum()
            issues.append(
                {
                    "issue": "duplicate_leads",
                    "business": biz,
                    "channel": "all",
                    "first_week": pd.Timestamp(hit["week_start"].min()),
                    "last_week": pd.Timestamp(hit["week_start"].max()),
                    "n_weeks": len(hit),
                    "detail": f"{int(g['dups'].sum())} duplicates, {rate:.1%} of recorded leads",
                }
            )
    shifts = query_df(con, "SELECT * FROM dq_attribution_shift ORDER BY business, channel")
    for r in shifts[shifts["detected"]].to_dict("records"):
        shift_start = pd.Timestamp(str(r["shift_week_start"]))
        issues.append(
            {
                "issue": "attribution_change",
                "business": r["business"],
                "channel": r["channel"],
                "first_week": shift_start,
                "last_week": lw["week_start"].max(),
                "n_weeks": int((lw["week_start"] >= shift_start).sum() / n_lines),
                "detail": (
                    f"platform/CRM ratio {r['ratio_before']:.2f} -> {r['ratio_after']:.2f} (p = {r['p_value']:.1e})"
                ),
            }
        )

    lineage = pd.DataFrame(
        [
            {"table": t, "layer": layer, "rows": table_count(con, t)}
            for t, layer in [
                ("synthetic_weekly_media", "raw"),
                ("synthetic_weekly_crm", "raw"),
                ("synthetic_b2_leads", "raw"),
                ("synthetic_customers", "raw"),
                ("synthetic_customer_activity", "raw"),
                ("media_clean", "clean"),
                ("b2_leads_clean", "clean"),
                ("crm_clean", "clean"),
                ("line_week", "metric"),
                ("business_week", "metric"),
                ("customer_lifetimes", "metric"),
                ("repeat_orders_by_month", "metric"),
                ("business_week_pnl", "metric"),
            ]
        ]
    )
    issues_df = pd.DataFrame(issues)
    for c in ("first_week", "last_week"):
        issues_df[c] = pd.to_datetime(issues_df[c]).dt.date
    return QualityReport(pd.DataFrame(checks), issues_df, lineage, shifts)
