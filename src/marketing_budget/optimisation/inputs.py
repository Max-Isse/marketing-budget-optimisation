"""Inputs the optimiser needs from earlier phases: last year's spend, customer values, payback limits, win rates
and platform-reported returns. All from the SQL layer and phase 1 estimates."""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.analysis.retention import ALL
from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.economics import customer_value

LAST_52 = "week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK"


def last_year_spend(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    d = query_df(con, f"SELECT business, channel, sum(spend) AS s FROM line_week WHERE {LAST_52} GROUP BY ALL")
    return {f"{b}.{c}": float(v) for b, c, v in zip(d["business"], d["channel"], d["s"], strict=True)}


def platform_return_per_dollar(con: duckdb.DuckDBPyConnection, lines: list[tuple[str, str]]) -> np.ndarray:
    """Platform-reported customers per dollar over the last year, outage weeks excluded."""
    d = query_df(
        con,
        f"SELECT business, channel, sum(platform_conversions) / sum(spend) AS r FROM line_week "
        f"WHERE {LAST_52} AND NOT tracking_outage GROUP BY ALL",
    )
    r = {(str(b), str(c)): float(v) for b, c, v in zip(d["business"], d["channel"], d["r"], strict=True)}
    return np.array([r[line] for line in lines])


def values_and_caps(estimates: pd.DataFrame, cfg: Config) -> tuple[dict[str, float], dict[str, float]]:
    """24-month value per customer and the highest CAC that pays back within the target, per business, from
    phase 1's retention estimates and finance's contribution figures."""
    v = cfg.section("valuation")
    ue = cfg.section("unit_economics")
    horizon, rate = int(v["horizon_months"]), float(v["annual_discount_rate"])
    values, caps = {}, {}
    for r in estimates[estimates["source"] == ALL].to_dict("records"):
        biz = str(r["business"])
        econ = {k: float(x) for k, x in ue[biz].items() if k != "model"}
        keys = ("survival_first_month", "survival_monthly", "repeat_rate_first_month", "repeat_decay_monthly")
        econ |= {k: float(r[k]) for k in keys if k in r and pd.notna(r[k])}
        cv = customer_value(str(ue[biz]["model"]), econ, horizon, rate)
        values[biz] = cv.value
        months = int(v["payback_target_months"][biz])
        caps[biz] = float(np.cumsum(cv.stream * cv.discount)[months] - cv.acquisition_cost)
    return values, caps


def win_rates(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    d = query_df(con, "SELECT business, sum(customers) / sum(qualified_leads) AS w FROM business_week GROUP BY 1")
    return {str(b): float(w) for b, w in zip(d["business"], d["w"], strict=True)}
