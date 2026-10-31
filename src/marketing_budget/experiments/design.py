"""Experiment design: sample size, duration, minimum detectable effect, region assignment, and the cost of
peeking. Inputs are historical data from the SQL layer and the assumptions in config `experiments`.

Formulas (two-sided alpha, power 1 - beta, z = standard normal quantiles):
* two proportions, relative MDE d on baseline p:  n per arm = (z_a + z_b)^2 (p1 q1 + p2 q2) / (p2 - p1)^2
* clustered rate (impressions within users): multiply by the design effect 1 + (m - 1) ICC
* two Poisson rates with equal exposure, rate ratio r: control events = (z_a + z_b)^2 (1 + 1/r) / (ln r)^2
* region tests: MDE from the pre-period's own noise, by treating its first half as "pre" and its second
  half as "test" (an A/A rehearsal before launch)
"""

from __future__ import annotations

import math
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from marketing_budget.config import Config
from marketing_budget.data.db import query_df


def _z(cfg: Config) -> tuple[float, float]:
    e = cfg.section("experiments")
    return float(stats.norm.ppf(1 - float(e["alpha"]) / 2)), float(stats.norm.ppf(float(e["power"])))


def n_two_proportions(p: float, rel_mde: float, za: float, zb: float) -> int:
    p2 = p * (1 + rel_mde)
    return math.ceil((za + zb) ** 2 * (p * (1 - p) + p2 * (1 - p2)) / (p2 - p) ** 2)


def mde_two_proportions(p: float, n_per_arm: float, za: float, zb: float) -> float:
    """Smallest relative uplift detectable with n per arm (normal approximation, solved numerically)."""
    lo, hi = 1e-6, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if n_two_proportions(p, mid, za, zb) > n_per_arm:
            lo = mid
        else:
            hi = mid
    return hi


def poisson_events_needed(rate_ratio: float, za: float, zb: float) -> float:
    return (za + zb) ** 2 * (1 + 1 / rate_ratio) / math.log(rate_ratio) ** 2


def poisson_mde(control_events: float, za: float, zb: float) -> float:
    """Smallest relative *decrease* detectable given expected control events."""
    lo, hi = 1e-4, 0.999
    for _ in range(100):
        mid = (lo + hi) / 2
        if poisson_events_needed(1 - mid, za, zb) > control_events:
            lo = mid
        else:
            hi = mid
    return hi


def peeking_false_positive_rate(
    n_per_day: int, p: float, days: int, alpha: float, sims: int, seed: int
) -> dict[str, float]:
    """A/A tests (no true difference) checked every day: how often does *some* daily look reach p < alpha?"""
    rng = np.random.default_rng(seed)
    za = stats.norm.ppf(1 - alpha / 2)
    a = rng.binomial(n_per_day, p, (sims, days)).cumsum(axis=1)
    b = rng.binomial(n_per_day, p, (sims, days)).cumsum(axis=1)
    n = n_per_day * np.arange(1, days + 1)
    pool = (a + b) / (2 * n)
    z = (a - b) / n / np.sqrt(pool * (1 - pool) * 2 / n)
    return {
        "days": days,
        "false_positive_rate_final_look_only": float((np.abs(z[:, -1]) > za).mean()),
        "false_positive_rate_any_daily_look": float((np.abs(z) > za).any(axis=1).mean()),
    }


def design_user_tests(con: duckdb.DuckDBPyConnection, cfg: Config) -> dict[str, dict[str, Any]]:
    e = cfg.section("experiments")
    za, zb = _z(cfg)
    plan: dict[str, dict[str, Any]] = {}

    lp = e["landing_page"]
    p = float(lp["baseline_conversion"])
    n = n_two_proportions(p, float(lp["min_detectable_uplift"]), za, zb)
    weeks = min(math.ceil(2 * n / float(lp["weekly_visitors"])), int(lp["max_weeks"]))
    n_run = weeks * float(lp["weekly_visitors"]) / 2
    plan["landing_page"] = {
        "unit": "visitor",
        "metric": "conversion rate (first paid box)",
        "baseline": p,
        "baseline_source": "assumption: web analytics",
        "min_worthwhile_effect": float(lp["min_detectable_uplift"]),
        "n_per_arm_required": n,
        "weeks": weeks,
        "n_per_arm_planned": int(n_run),
        "mde_at_planned_n": mde_two_proportions(p, n_run, za, zb),
    }

    cr = e["ad_creative"]
    d = query_df(
        con,
        "SELECT sum(clicks) / sum(impressions) AS ctr, avg(impressions) AS imps FROM line_week "
        "WHERE business = ? AND channel = ? "
        "AND week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK",
        [cr["business"], cr["channel"]],
    ).iloc[0]
    ctr, weekly_imps = float(d["ctr"]), float(d["imps"])
    deff = 1 + (float(cr["impressions_per_user"]) - 1) * float(cr["icc"])
    n_imps = math.ceil(n_two_proportions(ctr, float(cr["min_worthwhile_uplift"]), za, zb) * deff)
    weeks = min(math.ceil(2 * n_imps / weekly_imps), int(cr["max_weeks"]))
    plan["ad_creative"] = {
        "unit": "user",
        "metric": "click-through rate",
        "baseline": ctr,
        "baseline_source": "line_week, last 52 weeks",
        "min_worthwhile_effect": float(cr["min_worthwhile_uplift"]),
        "design_effect": deff,
        "n_per_arm_required": n_imps,
        "weeks": weeks,
        "n_per_arm_planned": int(weeks * weekly_imps / 2),
        "mde_at_planned_n": mde_two_proportions(ctr, weeks * weekly_imps / 2 / deff, za, zb),
        "weekly_users": weekly_imps / float(cr["impressions_per_user"]),
    }

    au = e["audience_targeting"]
    q = query_df(
        con,
        "SELECT avg(crm_qualified_leads) AS ql, avg(crm_leads) AS leads, avg(spend) AS spend FROM line_week "
        "WHERE business = ? AND channel = ? "
        "AND week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK",
        [au["business"], au["channel"]],
    ).iloc[0]
    per_arm_week = float(q["ql"]) / 2
    rr = 1 - float(au["min_worthwhile_change"])
    events = poisson_events_needed(rr, za, zb)
    weeks_needed = math.ceil(events / per_arm_week)
    weeks = min(weeks_needed, int(au["max_weeks"]))
    plan["audience_targeting"] = {
        "unit": "lead (budget split 50/50 between audiences)",
        "metric": "qualified leads per dollar",
        "baseline": float(q["ql"]) / float(q["spend"]),
        "baseline_source": "line_week, last 52 weeks",
        "min_worthwhile_effect": float(au["min_worthwhile_change"]),
        "qualified_leads_per_arm_week": per_arm_week,
        "n_per_arm_required": math.ceil(events),
        "weeks_required": weeks_needed,
        "weeks": weeks,
        "n_per_arm_planned": int(per_arm_week * weeks),
        "mde_at_planned_n": poisson_mde(per_arm_week * weeks, za, zb),
        "weekly_spend": float(q["spend"]),
        "weekly_leads": float(q["leads"]),
    }
    return plan


def assign_regions(pre: pd.DataFrame, treated_share: float, seed: int) -> pd.DataFrame:
    """Stratified randomisation: rank regions by pre-period customers, cut into blocks of 1/share, treat one
    region per block at random. Balances region size between arms."""
    rng = np.random.default_rng(seed)
    size = pre.groupby("region")["customers"].sum().sort_values()
    k = round(1 / treated_share)
    treated = []
    regions = size.index.to_numpy()
    for i in range(0, len(regions), k):
        block = regions[i : i + k]
        n_treat = max(1, round(len(block) * treated_share))
        treated += list(rng.choice(block, n_treat, replace=False))
    return pd.DataFrame({"region": regions, "treated": np.isin(regions, treated)})


def geo_mde(pre: pd.DataFrame, assignment: pd.DataFrame, test_weeks: int, za: float, zb: float) -> float:
    """Minimum detectable effect on total business customers in treated regions, as a share of their
    expected total: an A/A rehearsal on the pre-period (first half as baseline, second half as outcome)."""
    w = sorted(pre["week"].unique())
    half = len(w) // 2
    g = pre.assign(part=np.where(pre["week"].isin(w[:half]), "a", "b"))
    y = g.pivot_table(index="region", columns="part", values="customers", aggfunc="sum").join(
        assignment.set_index("region")
    )
    X = np.column_stack([np.ones(len(y)), y["treated"].astype(float), y["a"]])
    beta, *_ = np.linalg.lstsq(X, y["b"].to_numpy(float), rcond=None)
    resid = y["b"].to_numpy(float) - X @ beta
    sd = float(np.sqrt(resid @ resid / (len(y) - 3)))
    nt, nc = int(y["treated"].sum()), int((~y["treated"]).sum())
    se = sd * np.sqrt(1 / nt + 1 / nc)
    rel = (za + zb) * se / float(y.loc[y["treated"], "b"].mean())
    return float(rel * np.sqrt((len(w) - half) / test_weeks))  # longer test: noise of a sum grows as sqrt(weeks)


def choose_geo_design(candidates: list[dict[str, Any]], target: float) -> dict[str, Any]:
    """Cheapest design (fewest treated region-weeks) whose MDE reaches the target; if none does, the most
    sensitive one, flagged as underpowered."""
    ok = [c for c in candidates if c["mde"] <= target]
    if ok:
        best = min(ok, key=lambda c: (c["treated_share"] * c["test_weeks"], c["mde"]))
        return {**best, "powered": True}
    return {**min(candidates, key=lambda c: c["mde"]), "powered": False}
