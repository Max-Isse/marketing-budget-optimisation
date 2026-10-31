"""Tie-out values: the number every headline tile must show, computed from the extracts with the same formula the
workbook uses. After building the workbook, compare each tile with this table (docs/dashboard_spec.md, QA)."""

from __future__ import annotations

import pandas as pd


def tieout(x: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def add(page: str, tile: str, filt: str, value: float, formula: str) -> None:
        rows.append({"page": page, "tile": tile, "filter": filt, "expected_value": value, "tableau_formula": formula})

    bw = x["synthetic_weekly_business"].copy()
    bw["week_start"] = pd.to_datetime(bw["week_start"])
    last = bw[bw["week_start"] > bw["week_start"].max() - pd.Timedelta(weeks=52)]
    for scope, d in [("all businesses", last), *[(f"business = {b}", g) for b, g in last.groupby("business")]]:
        add("1 Executive summary", "Ad spend, last 52 weeks", scope, float(d["spend"].sum()), "SUM([spend])")
        add(
            "1 Executive summary",
            "New customers, last 52 weeks",
            scope,
            float(d["customers"].sum()),
            "SUM([customers])",
        )
        add(
            "1 Executive summary",
            "Blended CAC, last 52 weeks",
            scope,
            float(d["spend"].sum() / d["customers"].sum()),
            "SUM([spend]) / SUM([customers])",
        )
        add(
            "1 Executive summary",
            "Contribution profit, last 52 weeks",
            scope,
            float(d["contribution_profit"].sum()),
            "SUM([contribution_profit])",
        )

    ps: dict[object, dict[object, float]] = x["synthetic_plan_summary"].set_index("allocation").to_dict("index")
    gain = float(ps["recommended"]["expected_profit"]) - float(ps["status_quo"]["expected_profit"])
    down = float(ps["recommended"]["downside_profit"]) - float(ps["status_quo"]["downside_profit"])
    add("1 Executive summary", "Plan: expected gain a year (model)", "", gain, "[Plan gain] (see spec)")
    add("1 Executive summary", "Plan: pessimistic-case gain a year (model)", "", down, "[Plan downside gain]")

    al = x["synthetic_allocation"]
    for b, g in al.groupby("business"):
        add(
            "2 Budget plan", "Recommended spend", f"business = {b}", float(g["recommended"].sum()), "SUM([recommended])"
        )
        add(
            "2 Budget plan", "Change vs last year's split", f"business = {b}", float(g["change"].sum()), "SUM([change])"
        )
    add(
        "2 Budget plan",
        "Budget moved between lines",
        "",
        float(al.loc[al["change"] > 0, "change"].sum()),
        "SUM(IF [change] > 0 THEN [change] END)",
    )

    sc = x["synthetic_forecast_scenarios"]
    q = sc[(sc["period"] == "next quarter") & (sc["target"] == "customers")]
    for r in q.to_dict("records"):
        add(
            "4 Forecast",
            f"New customers next quarter ({r['scenario']})",
            f"business = {r['business']}",
            float(r["value"]),
            "SUM([value]) with [scenario] filter",
        )

    ex = x["synthetic_experiments"]
    lp = ex[(ex["experiment"] == "landing_page")].iloc[0]
    add("5 Experiments", "Landing page uplift", "", float(lp["relative_effect"]), "[relative_effect]")
    add("6 Data trust", "Data issues found", "", float(len(x["synthetic_dq_issues"])), "COUNT([issue])")
    return pd.DataFrame(rows)
