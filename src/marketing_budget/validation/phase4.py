"""Score phase 4 against the SYNTHETIC ground truth.

* The true response model: the simulation's own curves at next year's average demand, true customer values
  (including the lower value of affiliate and programmatic customers) and true payback limits.
* Curve recovery: for each line, the model's incremental customers and marginal return at last year's spend
  against the truth, and whether the truth lies inside the model's 80% band.
* Allocation scoring: what each allocation would really earn, and the best that was achievable under the same
  policies (the true optimum).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.economics import customer_value
from marketing_budget.optimisation.optimiser import Setting, evaluate, optimise
from marketing_budget.optimisation.response import ResponseModel


def true_model(truth: dict[str, Any], cfg: Config, lines: list[tuple[str, str]], n_weeks: int) -> ResponseModel:
    v = cfg.section("valuation")
    horizon, rate = int(v["horizon_months"]), float(v["annual_discount_rate"])
    t_mid = n_weeks + 26  # middle of the planning year
    vmax, k, s, value, organic = [], [], [], [], {}
    for biz, ch in lines:
        b = truth["businesses"][biz]
        p = b["channels"][ch]
        demand = (1 + float(b["trend_per_year"])) ** (t_mid / 52)  # seasonality averages 1 over a year
        organic[biz] = np.array([demand * float(b["organic_customers_per_week"])])
        vmax.append(demand * float(p["vmax_leads"]) * float(p["lead_to_qualified"]) * float(b["qualified_to_customer"]))
        k.append(float(p["half_sat"]))
        s.append(float(p["shape"]))
        cv = customer_value(b["model"], b["economics"], horizon, rate).value
        value.append(cv * float(p["value_multiplier"]))
    return ResponseModel(lines, np.array([vmax]), np.array([k]), np.array(s), organic, np.array(value))


def true_cac_caps(truth: dict[str, Any], cfg: Config) -> dict[str, float]:
    v = cfg.section("valuation")
    out = {}
    for biz, months in v["payback_target_months"].items():
        b = truth["businesses"][biz]
        cv = customer_value(b["model"], b["economics"], int(v["horizon_months"]), float(v["annual_discount_rate"]))
        out[biz] = float(np.cumsum(cv.stream * cv.discount)[int(months)] - cv.acquisition_cost)
    return out


def true_win_rates(truth: dict[str, Any]) -> dict[str, float]:
    return {biz: float(b["qualified_to_customer"]) for biz, b in truth["businesses"].items()}


def curve_recovery(est: ResponseModel, tru: ResponseModel, x: np.ndarray) -> pd.DataFrame:
    rows = []
    c_e, m_e = est.customers(x), est.marginal(x)
    c_t, m_t = tru.customers(x)[0], tru.marginal(x)[0]
    for i, (b, ch) in enumerate(est.lines):
        lo, hi = np.quantile(m_e[:, i], [0.1, 0.9])
        rows.append(
            {
                "business": b,
                "channel": ch,
                "weekly_spend": x[i],
                "model_customers": float(c_e[:, i].mean()),
                "true_customers": float(c_t[i]),
                "model_marginal_per_1000": 1000 * float(m_e[:, i].mean()),
                "model_p10": 1000 * float(lo),
                "model_p90": 1000 * float(hi),
                "true_marginal_per_1000": 1000 * float(m_t[i]),
                "true_in_80pct_band": bool(lo <= m_t[i] <= hi),
            }
        )
    return pd.DataFrame(rows)


def score_plan(plan: Any, truth: dict[str, Any], cfg: Config, n_weeks: int) -> dict[str, Any]:
    """True profit of every allocation, the true optimum under the same policies, and curve recovery."""
    rm = plan.rm
    tr = true_model(truth, cfg, rm.lines, n_weeks)
    win = true_win_rates(truth)
    tr.capacity = {
        b: float(v["max_qualified_leads_per_week"]) * win[b]
        for b, v in cfg.section("budget").get("sales_capacity", {}).items()
    }
    s = plan.setting
    best = optimise(
        tr, cfg, Setting(s.last_year, true_cac_caps(truth, cfg), s.tested, {"downside", "untested_guardrail"})
    )
    allocs = {**plan.allocations, "true_optimum": best.x}
    sq = evaluate(tr, allocs["status_quo"], cfg)["expected_profit"]
    opt = evaluate(tr, best.x, cfg)["expected_profit"]
    rows = []
    for k, x in allocs.items():
        t = evaluate(tr, x, cfg)
        m = evaluate(rm, x, cfg) if k != "true_optimum" else {"expected_profit": float("nan")}
        rows.append(
            {
                "allocation": k,
                "model_expected_profit": m["expected_profit"],
                "true_profit": t["expected_profit"],
                "true_gain_vs_status_quo": t["expected_profit"] - sq,
                "share_of_achievable_gain": (t["expected_profit"] - sq) / (opt - sq) if opt > sq else float("nan"),
            }
        )
    guard = optimise(rm, cfg, Setting(s.last_year, s.cac_max, s.tested, {"untested_guardrail"}))
    rows.append(
        {
            "allocation": "recommended_without_guardrail",
            "model_expected_profit": evaluate(rm, guard.x, cfg)["expected_profit"],
            "true_profit": evaluate(tr, guard.x, cfg)["expected_profit"],
            "true_gain_vs_status_quo": evaluate(tr, guard.x, cfg)["expected_profit"] - sq,
            "share_of_achievable_gain": (evaluate(tr, guard.x, cfg)["expected_profit"] - sq) / (opt - sq),
        }
    )
    return {
        "allocations": pd.DataFrame(rows),
        "true_optimum": best.x,
        "recovery": curve_recovery(rm, tr, allocs["status_quo"]),
        "recovery_uncalibrated": curve_recovery(plan.rm_uncal, tr, allocs["status_quo"]),
    }
