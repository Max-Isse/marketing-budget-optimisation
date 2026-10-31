"""Constrained budget optimisation over response-curve draws.

Decision: sustained weekly spend per line (annual = 52 x weekly). Objective: expected annual incremental
contribution (24-month customer value x incremental customers the business can serve - spend), averaged over
the curve draws.

Constraints (config `budget`, `valuation`):
* total budget, exactly
* line floors and ceilings (multiples of last year's spend; concentration cap per line)
* business floors and ceilings (incl. the 50% concentration cap)
* untested-line guardrail (D-023): lines with no experiment move at most +/- `untested_line_guardrail` of last
  year's spend, because the model cannot reliably rank them
* minimum acquisition: each business keeps at least `min_acquisition` x the customers last year's split would
  serve next year, capped at what its sales team can handle (D-022)
* payback: each business's average incremental CAC must pay back within its target months
* downside (D-006): the mean of the worst `downside_quantile` of draws (CVaR) must be no worse than last year's
* sales capacity is not a constraint but part of the response: leads beyond it earn nothing (response.py)

Solved with SLSQP and analytic gradients from several starting points. Every constraint can be switched off
(`drop`) to price it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

from marketing_budget.config import Config
from marketing_budget.constraints import line_bounds
from marketing_budget.optimisation.response import ResponseModel

CONSTRAINTS = [
    "untested_guardrail",
    "brand_search_floor",
    "channel_limits",
    "business_limits",
    "concentration",
    "min_acquisition",
    "payback",
    "sales_capacity",
    "downside",
]


@dataclass
class Setting:
    """Everything the optimiser needs besides the response model."""

    last_year: dict[str, float]  # annual spend by "B1.search_brand"
    cac_max: dict[str, float]  # business -> highest incremental CAC that pays back in target months
    tested: set[str] = field(default_factory=set)  # lines with a budget experiment, "B3.display_retargeting"
    drop: set[str] = field(default_factory=set)
    budget: float | None = None


def _cfg_without(cfg: Config, drop: set[str]) -> Config:
    raw = copy.deepcopy(cfg.raw)
    b = raw["budget"]
    total = float(b["annual_total"])
    if "brand_search_floor" in drop:
        b["channel_limits"]["overrides"].pop("B1.search_brand", None)
    if "channel_limits" in drop:
        b["channel_limits"]["default"] = {"min_multiple": 0.0, "max_multiple": 1e6}
        b["channel_limits"]["overrides"] = {}
    if "concentration" in drop:
        b["concentration"] = {"max_line_share": 1.0, "max_business_share": 1.0}
    if "business_limits" in drop:
        b["business_limits"] = {k: {"min": 0.0, "max": total} for k in b["business_limits"]}
    return Config(raw, cfg.root)


def line_limits(rm: ResponseModel, cfg: Config, s: Setting, budget: float) -> tuple[np.ndarray, np.ndarray]:
    """Annual floor and ceiling per line after every active policy, incl. the untested-line guardrail."""
    bounds = line_bounds(_cfg_without(cfg, s.drop), s.last_year)
    lb = bounds.lines.set_index("line").loc[[f"{b}.{c}" for b, c in rm.lines]]
    lo, hi = lb["min"].to_numpy(float), np.minimum(lb["max"].to_numpy(float), budget)
    g = float(cfg.section("budget").get("untested_line_guardrail", np.inf))
    if "untested_guardrail" not in s.drop and np.isfinite(g):
        last = lb["last_year"].to_numpy(float)
        untested = np.array([f"{b}.{c}" not in s.tested for b, c in rm.lines])
        lo = np.where(untested, np.maximum(lo, (1 - g) * last), lo)
        hi = np.where(untested, np.minimum(hi, (1 + g) * last), hi)
    return lo, np.maximum(hi, lo)


def status_quo(rm: ResponseModel, s: Setting, budget: float) -> np.ndarray:
    """Last year's split, scaled to the budget, as weekly spend."""
    x = np.array([s.last_year[f"{b}.{c}"] for b, c in rm.lines])
    return x / x.sum() * budget / 52


def cvar(v: np.ndarray, q: float) -> tuple[float, np.ndarray]:
    k = max(int(np.ceil(q * len(v))), 1)
    worst = np.argsort(v)[:k]
    return float(v[worst].mean()), worst


@dataclass
class Solution:
    x: np.ndarray  # weekly spend per line
    success: bool
    message: str


def optimise(rm: ResponseModel, cfg: Config, s: Setting, x_ref: np.ndarray | None = None) -> Solution:
    bcfg = cfg.section("budget")
    budget = float(s.budget if s.budget is not None else bcfg["annual_total"])
    if "sales_capacity" in s.drop:
        rm = rm.without_capacity()
    lo, hi = line_limits(rm, cfg, s, budget)
    biz = rm.businesses
    idx = {b: rm.idx(b) for b in biz}
    biz_lim: dict[Any, dict[Any, Any]] = (
        line_bounds(_cfg_without(cfg, s.drop), s.last_year).business.set_index("business").to_dict("index")
    )
    x_ref = status_quo(rm, s, budget) if x_ref is None else x_ref
    scale = np.maximum(x_ref, 1.0)  # optimise in units of last year's spend: well conditioned
    q = float(bcfg["risk"]["downside_quantile"])
    cvar_ref, _ = cvar(rm.annual_profit(x_ref), q)
    eff_ref = rm.effective_customers(x_ref)
    cust_ref = {b: float((rm.organic[b] + eff_ref[:, idx[b]].sum(axis=1)).mean()) for b in biz}
    min_acq = bcfg["min_acquisition"]
    payback = cfg.section("valuation")["payback_target_months"]

    def X(u: np.ndarray) -> np.ndarray:
        return u * scale

    def obj(u: np.ndarray) -> float:
        return -float(rm.annual_profit(X(u)).mean()) / 1e6

    def obj_jac(u: np.ndarray) -> np.ndarray:
        return -rm.profit_gradient(X(u)).mean(axis=0) * scale / 1e6

    cons: list[dict[str, Any]] = [
        {"type": "eq", "fun": lambda u: (52 * X(u).sum() - budget) / 1e6, "jac": lambda u: 52 * scale / 1e6}
    ]
    for b in biz:
        i = idx[b]
        mask = np.zeros(len(scale))
        mask[i] = 1.0
        lo_b, hi_b = float(biz_lim[b]["min"]), min(float(biz_lim[b]["max"]), budget)
        cons.append(
            {
                "type": "ineq",
                "fun": lambda u, m=mask, lo_b=lo_b: (52 * (X(u) * m).sum() - lo_b) / 1e6,
                "jac": lambda u, m=mask: 52 * m * scale / 1e6,
            }
        )
        cons.append(
            {
                "type": "ineq",
                "fun": lambda u, m=mask, hi_b=hi_b: (hi_b - 52 * (X(u) * m).sum()) / 1e6,
                "jac": lambda u, m=mask: -52 * m * scale / 1e6,
            }
        )
        if "min_acquisition" not in s.drop and b in min_acq:
            floor = float(min_acq[b]) * cust_ref[b]
            if b in rm.capacity:
                # a physical limit outranks a target: never require more customers than sales can serve (D-022)
                floor = min(floor, 0.995 * rm.capacity[b])

            def f_acq(u: np.ndarray, i: np.ndarray = i, b: str = b, floor: float = floor) -> float:
                eff = rm.effective_customers(X(u))[:, i].sum(axis=1)
                return float((rm.organic[b] + eff).mean() - floor) / floor

            def j_acq(u: np.ndarray, m: np.ndarray = mask, floor: float = floor) -> np.ndarray:
                return rm.effective_marginal(X(u)).mean(axis=0) * m * scale / floor

            cons.append({"type": "ineq", "fun": f_acq, "jac": j_acq})
        if "payback" not in s.drop and b in payback:
            cap = s.cac_max[b]

            def f_pb(u: np.ndarray, i: np.ndarray = i, cap: float = cap, m: np.ndarray = mask) -> float:
                inc = rm.effective_customers(X(u))[:, i].sum(axis=1).mean()
                return float(cap * inc - (X(u) * m).sum()) / 1e4

            def j_pb(u: np.ndarray, cap: float = cap, m: np.ndarray = mask) -> np.ndarray:
                return (cap * rm.effective_marginal(X(u)).mean(axis=0) * m - m) * scale / 1e4

            cons.append({"type": "ineq", "fun": f_pb, "jac": j_pb})
    if "downside" not in s.drop and rm.vmax.shape[0] > 1:

        def f_risk(u: np.ndarray) -> float:
            return (cvar(rm.annual_profit(X(u)), q)[0] - cvar_ref) / 1e6

        def j_risk(u: np.ndarray) -> np.ndarray:
            _, worst = cvar(rm.annual_profit(X(u)), q)
            return rm.profit_gradient(X(u))[worst].mean(axis=0) * scale / 1e6

        cons.append({"type": "ineq", "fun": f_risk, "jac": j_risk})

    lbu, ubu = lo / 52 / scale, hi / 52 / scale
    starts = [
        np.clip(x_ref / scale, lbu, ubu),
        np.clip(np.full(len(scale), budget / 52 / len(scale)) / scale, lbu, ubu),
        (lbu + ubu) / 2,
    ]
    best: Any = None
    for u0 in starts:
        r = minimize(
            obj,
            u0,
            jac=obj_jac,
            bounds=list(zip(lbu, ubu, strict=True)),
            constraints=cons,
            method="SLSQP",
            options={"maxiter": 500, "ftol": 1e-10},
        )
        ok = all((c["fun"](r.x) >= -1e-6) if c["type"] == "ineq" else abs(c["fun"](r.x)) <= 1e-6 for c in cons)
        if ok and (best is None or r.fun < best.fun):
            best = r
    if best is None:
        return Solution(x_ref, False, "no feasible solution from any start")
    return Solution(X(best.x), True, str(best.message))


def platform_roas_split(rm: ResponseModel, cfg: Config, s: Setting, platform_per_dollar: np.ndarray) -> np.ndarray:
    """What a dashboard-driven team would do: put money where platform-reported return per dollar is highest,
    within the same budget, line and business limits (a linear programme; no response model involved)."""
    budget = float(cfg.section("budget")["annual_total"])
    bounds = line_bounds(cfg, s.last_year)
    lb = bounds.lines.set_index("line").loc[[f"{b}.{c}" for b, c in rm.lines]]
    biz_lim: dict[Any, dict[Any, Any]] = bounds.business.set_index("business").to_dict("index")
    A_ub, b_ub = [], []
    for b in rm.businesses:
        m = np.zeros(len(rm.lines))
        m[rm.idx(b)] = 1.0
        A_ub += [m, -m]
        b_ub += [float(biz_lim[b]["max"]), -float(biz_lim[b]["min"])]
    res = linprog(
        -(platform_per_dollar * rm.value),
        A_ub=np.array(A_ub),
        b_ub=np.array(b_ub),
        A_eq=np.ones((1, len(rm.lines))),
        b_eq=[budget],
        bounds=list(zip(lb["min"], lb["max"], strict=True)),
    )
    return np.asarray(res.x) / 52


def evaluate(rm: ResponseModel, x: np.ndarray, cfg: Config) -> dict[str, float]:
    q = float(cfg.section("budget")["risk"]["downside_quantile"])
    p = rm.annual_profit(x)
    eff = rm.effective_customers(x)
    out = {
        "expected_profit": float(p.mean()),
        "downside_profit": cvar(p, q)[0],
        "p90_profit": float(np.quantile(p, 0.9)) if len(p) > 1 else float(p[0]),
        "incremental_customers": float(52 * eff.sum(axis=1).mean()),
    }
    for b in rm.businesses:
        i = rm.idx(b)
        out[f"spend_{b}"] = float(52 * x[i].sum())
        out[f"incremental_customers_{b}"] = float(52 * eff[:, i].sum(axis=1).mean())
    return out


def allocation_table(rm: ResponseModel, allocations: dict[str, np.ndarray]) -> pd.DataFrame:
    return pd.DataFrame(
        {k: 52 * v for k, v in allocations.items()}, index=pd.Index([f"{b}.{c}" for b, c in rm.lines], name="line")
    ).reset_index()
