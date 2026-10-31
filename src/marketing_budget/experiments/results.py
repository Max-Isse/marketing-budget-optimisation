"""Turn experiment data into results tables: effects, decisions, attribution vs causation and economics.

Evidence labels: the measured effects are *causal*; scaling them to a year and to the whole business, and
valuing customers, rests on *assumptions* (stated in each row).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.experiments.analyze import (
    GeoResult,
    ctr_test,
    cumulative_p,
    decide,
    geo_test,
    holm,
    rate_ratio,
    two_proportions,
)

CHANNEL_NAMES = {
    "search_brand": "brand search",
    "search_generic": "generic search",
    "social_prospecting": "social prospecting",
    "display_retargeting": "retargeting",
    "affiliates": "affiliates",
    "shopping": "shopping ads",
    "linkedin": "LinkedIn",
    "review_sites": "review sites",
    "programmatic_display": "programmatic display",
}


@dataclass
class ExperimentResults:
    effects: pd.DataFrame  # one row per experiment x metric
    segments: pd.DataFrame
    geo: dict[str, GeoResult]
    attribution: pd.DataFrame
    economics: pd.DataFrame
    peeking: dict[str, pd.DataFrame] = field(default_factory=dict)


def _annual_line(con: duckdb.DuckDBPyConnection, biz: str, ch: str) -> dict[str, float]:
    r: dict[Any, Any] = query_df(
        con,
        "SELECT sum(spend) AS spend, sum(crm_customers) AS last_click, sum(crm_qualified_leads) AS ql "
        "FROM line_week WHERE business = ? AND channel = ? "
        "AND week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK",
        [biz, ch],
    ).to_dict("records")[0]
    return {str(k): float(v) for k, v in r.items()}


def _historical_slope(con: duckdb.DuckDBPyConnection, biz: str, ch: str) -> float:
    """Correlation view: weekly business customers regressed on this line's spend, no controls."""
    d = query_df(
        con,
        "SELECT l.spend, b.customers FROM line_week l JOIN business_week b USING (week_start, business) "
        "WHERE l.business = ? AND l.channel = ?",
        [biz, ch],
    )
    return float(np.polyfit(d["spend"], d["customers"], 1)[0])


def analyse(
    con: duckdb.DuckDBPyConnection,
    plan: dict[str, Any],
    blocks: dict[str, pd.Series],
    geo_weeks: dict[str, int],
    values: dict[str, float],
    cfg: Config,
) -> ExperimentResults:
    e = cfg.section("experiments")
    alpha = float(e["alpha"])
    rows: list[dict[str, Any]] = []
    seg_rows: list[dict[str, Any]] = []
    econ: list[dict[str, Any]] = []

    # Landing page
    lp = query_df(con, "SELECT * FROM synthetic_exp_landing_page")
    g = lp.groupby("arm")["converted"].agg(["sum", "size"]).to_dict("index")
    r = two_proportions(
        g["current_page"]["sum"], g["current_page"]["size"], g["new_page"]["sum"], g["new_page"]["size"]
    )
    lpc = e["landing_page"]
    conv_year = float(lpc["weekly_visitors"]) * 52 * float(lpc["baseline_conversion"])
    v1 = values[str(lpc["business"])]
    thr = float(lpc["build_cost"]) / (conv_year * v1)  # break-even uplift: pays back the build cost in a year
    rows.append({"experiment": "landing_page", "metric": "conversion rate", **r, "threshold": thr})
    seg_p, seg = [], []
    for dev, dev_df in lp.groupby("device"):
        gs = dev_df.groupby("arm")["converted"].agg(["sum", "size"]).to_dict("index")
        rs = two_proportions(
            gs["current_page"]["sum"], gs["current_page"]["size"], gs["new_page"]["sum"], gs["new_page"]["size"]
        )
        seg.append({"experiment": "landing_page", "segment": f"device = {dev}", **rs})
        seg_p.append(rs["p_value"])
    for s_, adj in zip(seg, holm(seg_p), strict=True):
        seg_rows.append({**s_, "p_value_holm": adj})
    for case, eff in (("estimate", r["relative_effect"]), ("ci_low", r["ci_low"]), ("ci_high", r["ci_high"])):
        econ.append(
            {
                "experiment": "landing_page",
                "decision": "launch the new B1 landing page",
                "case": case,
                "extra_customers_per_year": eff * conv_year,
                "contribution_per_year": eff * conv_year * v1 - float(lpc["build_cost"]),
                "basis": (
                    f"uplift x {conv_year:,.0f} paid-landing conversions a year x ${v1:,.0f}"
                    f" - ${float(lpc['build_cost']):,.0f} build cost"
                ),
            }
        )

    # Ad creative
    cr = query_df(con, "SELECT * FROM synthetic_exp_creative")
    rc = ctr_test(cr, alpha)
    rows.append(
        {
            "experiment": "ad_creative",
            "metric": "click-through rate",
            **{k: rc[k] for k in ("rate_a", "rate_b", "n_a", "n_b", "relative_effect", "ci_low", "ci_high", "p_value")},
            "threshold": 0.0,  # switching creatives costs nothing, so any real gain is worth having
        }
    )
    naive_row = {
        "experiment": "ad_creative",
        "segment": "naive impression-level analysis (wrong)",
        "relative_effect": rc["relative_effect"],
        "ci_low": rc["naive_ci_low"],
        "ci_high": rc["naive_ci_high"],
        "p_value": rc["naive_p_value"],
        "p_value_holm": np.nan,
    }
    seg_rows.append(naive_row)

    # Audience targeting
    au = query_df(con, "SELECT * FROM synthetic_exp_audience")
    spend = au.groupby(["arm", "week"])["arm_week_spend"].first().groupby("arm").sum().to_dict()
    counts = (
        au.groupby("arm")
        .agg(leads=("lead_id", "size"), qualified=("is_qualified", "sum"), won=("is_won", "sum"))
        .to_dict("index")
    )
    thr_a = float(e["audience_targeting"]["min_worthwhile_change"])
    for metric, col in (("leads per $", "leads"), ("qualified leads per $", "qualified"), ("customers per $", "won")):
        ra = rate_ratio(
            counts["job_title"][col], spend["job_title"], counts["lookalike"][col], spend["lookalike"], alpha
        )
        rows.append({"experiment": "audience_targeting", "metric": metric, **ra, "threshold": thr_a})
    aud_q = rows[-2]
    ann = _annual_line(con, "B2", "linkedin")
    close_b2 = float(
        query_df(con, "SELECT sum(customers) / sum(qualified_leads) AS r FROM business_week WHERE business = 'B2'")[
            "r"
        ].iloc[0]
    )
    for case in ("estimate", "ci_low", "ci_high"):
        eff = aud_q["relative_effect" if case == "estimate" else case]
        extra_q = eff * ann["spend"] * aud_q["rate_a"]
        econ.append(
            {
                "experiment": "audience_targeting",
                "decision": "switch B2 LinkedIn to the lookalike audience",
                "case": case,
                "extra_customers_per_year": extra_q * close_b2,
                "contribution_per_year": extra_q * close_b2 * values["B2"],
                "basis": (
                    f"change in qualified leads per $ x ${ann['spend']:,.0f} a year x {close_b2:.0%} win rate"
                    f" x ${values['B2']:,.0f}"
                ),
            }
        )

    # Region tests
    geo: dict[str, GeoResult] = {}
    attrib = []
    for name, spec in e["geo_tests"].items():
        weeks_test = geo_weeks[name]
        panel = query_df(con, "SELECT * FROM synthetic_exp_geo WHERE experiment = ?", [name])
        res = geo_test(panel, blocks[name], int(e["geo"]["permutations"]), cfg.seed + 7, alpha)
        geo[name] = res
        s = res.summary
        biz, ch = spec["business"], spec["channel"]
        line = _annual_line(con, biz, ch)
        pre = panel[panel["period"] == "pre"]
        treated_frac = float(pre.loc[pre["treated"], "customers"].sum() / pre["customers"].sum())
        to_year = 52 / weeks_test / treated_frac
        rows.append(
            {
                "experiment": name,
                "metric": "total business customers (region test)",
                "relative_effect": s["relative_effect"],
                "ci_low": s["relative_ci_low"],
                "ci_high": s["relative_ci_high"],
                "p_value": s["p_value_randomisation"],
                "n_a": s["n_regions"] - s["n_treated"],
                "n_b": s["n_treated"],
                "threshold": np.nan,
            }
        )
        v = values[biz]
        moves_spend = abs(s["spend_change"]) > 0.01 * line["spend"] * weeks_test / 52

        def per_k(x: float, change: float = s["spend_change"], ok: bool = moves_spend) -> float:
            return 1000 * x / change if ok else float("nan")

        attrib.append(
            {
                "experiment": name,
                "line": f"{biz} {ch}",
                "annual_line_spend": line["spend"],
                "spend_change": s["spend_change"],
                "platform_reported_change": s["platform_change"],
                "last_click_change": s["last_click_change"],
                "causal_change": s["incremental_customers"],
                "causal_ci_low": s["incremental_ci_low"],
                "causal_ci_high": s["incremental_ci_high"],
                "correlation_per_1000": 1000 * _historical_slope(con, biz, ch),
                "platform_per_1000": per_k(s["platform_change"]),
                "last_click_per_1000": per_k(s["last_click_change"]),
                "causal_per_1000": per_k(s["incremental_customers"]),
            }
        )
        for case, inc in (
            ("estimate", s["incremental_customers"]),
            ("ci_low", s["incremental_ci_low"]),
            ("ci_high", s["incremental_ci_high"]),
        ):
            cust_year = inc * to_year
            spend_year = s["spend_change"] * to_year
            label = f"{biz} {CHANNEL_NAMES.get(ch, ch)}"
            if spec["treatment"] == "tcpa":
                decision, contrib = f"switch {label} to target-CPA bidding", cust_year * v
            elif float(spec["spend_multiplier"]) == 0:
                decision, contrib = f"switch off {label}", cust_year * v - spend_year
            else:
                decision = f"raise {label} spend by {float(spec['spend_multiplier']) - 1:.0%}"
                contrib = cust_year * v - spend_year
            econ.append(
                {
                    "experiment": name,
                    "decision": decision,
                    "case": case,
                    "extra_customers_per_year": cust_year,
                    "contribution_per_year": contrib,
                    "basis": (
                        f"test effect scaled to 52 weeks and all regions (treated regions = {treated_frac:.0%} of"
                        f" customers) x ${v:,.0f}; annual line spend ${line['spend']:,.0f}"
                    ),
                }
            )

    effects = pd.DataFrame(rows)
    effects["decision"] = [
        decide(lo, hi, t) if not np.isnan(t) else ""
        for lo, hi, t in zip(effects["ci_low"], effects["ci_high"], effects["threshold"], strict=True)
    ]
    peeking = {
        "landing_page": cumulative_p(
            lp.assign(converted=lp["converted"].astype(int)), "arm", "current_page", "new_page", "converted", None
        ),
        "ad_creative": cumulative_p(cr, "arm", "creative_a", "creative_b", "clicks", "impressions"),
    }
    return ExperimentResults(effects, pd.DataFrame(seg_rows), geo, pd.DataFrame(attrib), pd.DataFrame(econ), peeking)
