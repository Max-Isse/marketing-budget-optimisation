"""Tableau extracts: tidy CSVs, one or more per dashboard page, built from the SQL layer and the validated outputs
of phases 1-5 (`reports/tables`). Ground-truth validation tables are never exported: a real dashboard would not
have them.

Every extract carries keys Tableau can relate on (`business`, `line` = "B1.search_brand", `week_start`) and a
readable label for each code. Ratios (CAC, cost per lead, conversion rates) are *not* stored: Tableau must compute
them as SUM()/SUM() so they stay correct at any level of aggregation (see docs/dashboard_spec.md).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.analysis.retention import ALL
from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.experiments.results import CHANNEL_NAMES
from marketing_budget.reporting.optimisation import POLICY_NAMES

BUSINESS_NAMES = {"B1": "Hearth Box", "B2": "Ledgerline", "B3": "Atlas Outdoor"}
LAST_52 = "week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK"


def _t(cfg: Config, name: str) -> pd.DataFrame:
    return pd.read_csv(cfg.path("tables_dir") / f"{name}.csv")


def _label_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Add business_name, channel_label and line ("B1.search_brand") from business + channel."""
    df = df.copy()
    df["business_name"] = df["business"].map(BUSINESS_NAMES)
    df["channel_label"] = df["channel"].map(CHANNEL_NAMES).fillna(df["channel"])
    df["line"] = df["business"] + "." + df["channel"]
    df["line_label"] = df["business"] + " " + df["channel_label"]
    return df


def _split_line(df: pd.DataFrame, col: str = "line") -> pd.DataFrame:
    parts = df[col].str.split(".", n=1, expand=True)
    return _label_lines(df.assign(business=parts[0], channel=parts[1]).drop(columns=[col]))


def build_extracts(con: duckdb.DuckDBPyConnection, cfg: Config, tested: set[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}

    # 1. Weekly business KPIs (P&L view)
    bw = query_df(con, "SELECT * FROM business_week_pnl ORDER BY business, week_start")
    bw["business_name"] = bw["business"].map(BUSINESS_NAMES)
    out["synthetic_weekly_business"] = bw.drop(columns=["blended_cac"])

    # 2. Weekly channel metrics with data-quality flags
    lw = query_df(
        con,
        "SELECT week_start, business, channel, spend, impressions, clicks, platform_conversions, "
        "crm_leads, crm_qualified_leads, crm_customers, tracking_outage, cost_restated, attribution_changed, "
        "any_dq_flag FROM line_week ORDER BY business, channel, week_start",
    )
    lw = _label_lines(lw)
    lw["tested_by_experiment"] = lw["line"].isin(tested)
    out["synthetic_weekly_channel"] = lw

    # 3. Forecast: last 52 weeks of actuals + 52 weeks of forecast with the 80% range
    fw = _t(cfg, "forecast_weekly")
    targets = ["spend", "customers", "revenue", "contribution_profit"]
    fw = fw[fw["target"].isin(targets)].assign(series="forecast")
    hist = bw[bw["week_start"] > bw["week_start"].max() - pd.Timedelta(weeks=52)]
    act = hist.melt(id_vars=["week_start", "business"], value_vars=targets, var_name="target", value_name="forecast")
    act = act.assign(
        series="actual", low=np.nan, high=np.nan, model="actual", horizon=0, beyond_validated_horizon=False
    )
    fc = pd.concat([act, fw], ignore_index=True).rename(columns={"forecast": "value"})
    fc["week_start"] = pd.to_datetime(fc["week_start"]).dt.date
    fc["business_name"] = fc["business"].map(BUSINESS_NAMES)
    out["synthetic_forecast"] = fc[
        [
            "week_start",
            "business",
            "business_name",
            "target",
            "series",
            "model",
            "horizon",
            "value",
            "low",
            "high",
            "beyond_validated_horizon",
        ]
    ]
    sc = _t(cfg, "forecast_scenarios")
    sc["business_name"] = sc["business"].map(BUSINESS_NAMES)
    out["synthetic_forecast_scenarios"] = sc

    # 4. Channel lenses: customers per $1,000 four ways
    ly = query_df(
        con,
        "SELECT business, channel, sum(spend) AS spend, "
        "sum(platform_conversions) FILTER (WHERE NOT tracking_outage) AS platform, "
        "sum(spend) FILTER (WHERE NOT tracking_outage) AS spend_tracked, sum(crm_customers) AS last_click "
        f"FROM line_week WHERE {LAST_52} GROUP BY ALL",
    )
    cv = _t(cfg, "customer_value_estimates")
    values = {
        str(b): float(v) for b, s, v in zip(cv["business"], cv["source"], cv["customer_value"], strict=True) if s == ALL
    }
    mr = _t(cfg, "marginal_returns")
    att = _t(cfg, "experiment_attribution_vs_causal")
    att = att[att["causal_per_1000"].notna()].assign(
        business=lambda d: d["line"].str.split(" ").str[0],
        channel=lambda d: d["line"].str.split(" ").str[1],
        b1=lambda d: 1000 * d["causal_ci_low"] / d["spend_change"],
        b2=lambda d: 1000 * d["causal_ci_high"] / d["spend_change"],
    )
    # dividing by a negative spend change (a switch-off test) flips the bounds: order them afterwards
    att = att.assign(lo=att[["b1", "b2"]].min(axis=1), hi=att[["b1", "b2"]].max(axis=1))
    rows = []
    for r in ly.to_dict("records"):
        b, ch = str(r["business"]), str(r["channel"])
        v = float(values[b])
        rows.append(
            {
                "business": b,
                "channel": ch,
                "lens": "1 Platform-reported",
                "evidence": "attribution rule",
                "customers_per_1000": 1000 * r["platform"] / r["spend_tracked"],
                "low": np.nan,
                "high": np.nan,
            }
        )
        rows.append(
            {
                "business": b,
                "channel": ch,
                "lens": "2 CRM last click",
                "evidence": "attribution rule",
                "customers_per_1000": 1000 * r["last_click"] / r["spend"],
                "low": np.nan,
                "high": np.nan,
            }
        )
        e = att[(att["business"] == b) & (att["channel"] == ch)]
        if len(e):
            x = e.iloc[0]
            rows.append(
                {
                    "business": b,
                    "channel": ch,
                    "lens": "3 Randomised test (average)",
                    "evidence": "causal",
                    "customers_per_1000": float(x["causal_per_1000"]),
                    "low": float(x["lo"]),
                    "high": float(x["hi"]),
                }
            )
        m = mr[(mr["allocation"] == "status_quo") & (mr["business"] == b) & (mr["channel"] == ch)].iloc[0]
        rows.append(
            {
                "business": b,
                "channel": ch,
                "lens": "4 Model: next dollar",
                "evidence": "model, calibrated" if f"{b}.{ch}" in tested else "model, history only",
                "customers_per_1000": 1000 * float(m["marginal_return"]) / v,
                "low": 1000 * float(m["marginal_p10"]) / v,
                "high": 1000 * float(m["marginal_p90"]) / v,
            }
        )
    lens = _label_lines(pd.DataFrame(rows))
    lens["annual_spend_last_year"] = lens["line"].map(
        dict(zip(ly["business"] + "." + ly["channel"], ly["spend"], strict=True))
    )
    out["synthetic_channel_lenses"] = lens

    # 5. Allocation: last year's split vs recommended, with the sensitivity verdict
    al = _split_line(_t(cfg, "allocation_by_line"))
    ver = _t(cfg, "sensitivity_line_verdicts").set_index("line")
    mrr = mr.assign(line=mr["business"] + "." + mr["channel"]).pivot(
        index="line", columns="allocation", values="marginal_return"
    )
    al["change"] = al["recommended"] - al["status_quo"]
    al["verdict"] = al["line"].map(ver["verdict"])
    al["evidence"] = al["line"].map(ver["evidence"])
    al["lowest_change_across_scenarios"] = al["line"].map(ver["lowest_change"])
    al["highest_change_across_scenarios"] = al["line"].map(ver["highest_change"])
    al["marginal_return_last_year_split"] = al["line"].map(mrr["status_quo"])
    al["marginal_return_recommended"] = al["line"].map(mrr["recommended"])
    out["synthetic_allocation"] = al.rename(columns={"status_quo": "last_year_split"})

    # 6. Plan summary, policy costs, budget curve, next tests (all model-based)
    ev = _t(cfg, "allocation_evaluation")
    out["synthetic_plan_summary"] = ev[
        ["allocation", "expected_profit", "downside_profit", "p90_profit", "incremental_customers"]
    ]
    pc = _t(cfg, "policy_costs")
    pc["policy"] = pc["policy_removed"].map(POLICY_NAMES)
    out["synthetic_policy_costs"] = pc
    out["synthetic_budget_curve"] = _t(cfg, "sensitivity_budget_curve")
    out["synthetic_next_tests"] = _label_lines(_t(cfg, "next_tests"))

    # 7. Experiments: effect, interval, decision and annual value
    ef = _t(cfg, "experiment_effects")
    dec = _t(cfg, "experiment_decisions").rename(
        columns={
            "estimate": "annual_value_estimate",
            "low": "annual_value_low",
            "high": "annual_value_high",
            "verdict": "rollout_verdict",
            "decision": "rollout_decision",
        }
    )
    out["synthetic_experiments"] = ef.merge(dec, on="experiment", how="left").assign(evidence="causal")

    # 8. Data trust: issues and the weekly platform / CRM ratio
    out["synthetic_dq_issues"] = _t(cfg, "dq_issues")
    ratio = lw[
        [
            "week_start",
            "business",
            "channel",
            "line",
            "line_label",
            "platform_conversions",
            "crm_customers",
            "tracking_outage",
            "attribution_changed",
        ]
    ]
    out["synthetic_attribution_ratio_weekly"] = ratio
    return out


def data_dictionary(extracts: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Every field of every extract with its type; definitions are in docs/metric_definitions.md and the spec."""
    rows = []
    for name, df in extracts.items():
        for col, dt in df.dtypes.items():
            rows.append({"extract": f"{name}.csv", "field": col, "type": str(dt), "rows": len(df)})
    return pd.DataFrame(rows)


def write_extracts(extracts: dict[str, pd.DataFrame], cfg: Config) -> Path:
    out = cfg.path("dashboard_dir") / "data"
    out.mkdir(parents=True, exist_ok=True)
    for name, df in extracts.items():
        df.to_csv(out / f"{name}.csv", index=False, float_format="%.6g")
    data_dictionary(extracts).to_csv(out.parent / "data_dictionary.csv", index=False)
    return out
