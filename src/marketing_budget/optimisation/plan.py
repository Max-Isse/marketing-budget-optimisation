"""Phase 4 pipeline (analysis side): fit the curves, compare allocations, price each policy, value the budget,
and say which lines to test next. No ground truth here; validation/phase4.py scores the results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.analysis.retention import estimate_retention
from marketing_budget.config import Config
from marketing_budget.optimisation.inputs import last_year_spend, platform_return_per_dollar, values_and_caps, win_rates
from marketing_budget.optimisation.mmm import FittedBusiness, calibration_check, fit_business, load_business_data
from marketing_budget.optimisation.optimiser import (
    CONSTRAINTS,
    Setting,
    evaluate,
    optimise,
    platform_roas_split,
    status_quo,
)
from marketing_budget.optimisation.response import ResponseModel, from_fits

ALLOCATIONS = ["status_quo", "platform_roas", "uncalibrated_model", "calibrated_point", "recommended"]


@dataclass
class Plan:
    rm: ResponseModel  # calibrated, with uncertainty draws
    rm_uncal: ResponseModel
    setting: Setting
    allocations: dict[str, np.ndarray]
    evaluation: pd.DataFrame  # allocation x metrics under the calibrated model
    policy_costs: pd.DataFrame
    budget_value: dict[str, float]
    marginal: pd.DataFrame  # per line: marginal return at status quo and at the recommendation
    calibration: pd.DataFrame
    next_tests: pd.DataFrame
    values: dict[str, float]
    extras: dict[str, object] = field(default_factory=dict)


def _capacity(cfg: Config, wr: dict[str, float]) -> dict[str, float]:
    cap = cfg.section("budget").get("sales_capacity", {})
    return {b: float(v["max_qualified_leads_per_week"]) * wr[b] for b, v in cap.items()}


def build_plan(con: duckdb.DuckDBPyConnection, cfg: Config) -> Plan:
    rc = cfg.section("response_model")
    n_draws = int(cfg.section("budget")["risk"]["uncertainty_draws"])
    data = load_business_data(con, cfg)
    values, caps = values_and_caps(estimate_retention(con, cfg).estimates, cfg)
    wr = win_rates(con)
    capacity = _capacity(cfg, wr)
    fits: dict[str, FittedBusiness] = {}
    uncal: dict[str, FittedBusiness] = {}
    for i, b in enumerate(cfg.businesses):
        fits[b] = fit_business(data[b], cfg, bool(rc["calibrate"]), n_draws, cfg.seed + 700 + i)
        uncal[b] = fit_business(data[b], cfg, False, 0, 0)
    rm = from_fits(fits, values, capacity)
    rm_point = from_fits(fits, values, capacity, use_point=True)
    rm_uncal = from_fits(uncal, values, capacity, use_point=True)
    cal_path = cfg.path("artifacts_dir") / "experiment_calibration.json"
    tested = {f"{c['business']}.{c['channel']}" for c in json.loads(cal_path.read_text(encoding="utf-8"))}
    s = Setting(last_year_spend(con), caps, tested)
    budget = float(cfg.section("budget")["annual_total"])

    allocations = {
        "status_quo": status_quo(rm, s, budget),
        "platform_roas": platform_roas_split(rm, cfg, s, platform_return_per_dollar(con, rm.lines)),
        "uncalibrated_model": optimise(rm_uncal, cfg, Setting(s.last_year, caps, tested, {"downside"})).x,
        "calibrated_point": optimise(rm_point, cfg, Setting(s.last_year, caps, tested, {"downside"})).x,
    }
    rec = optimise(rm, cfg, s)
    if not rec.success:
        raise RuntimeError(f"recommended plan infeasible: {rec.message}")
    allocations["recommended"] = rec.x
    evaluation = pd.DataFrame([{"allocation": k, **evaluate(rm, x, cfg)} for k, x in allocations.items()])

    base = evaluate(rm, rec.x, cfg)
    pc = []
    for c in CONSTRAINTS:
        sol = optimise(rm, cfg, Setting(s.last_year, caps, tested, {c}))
        # score each plan in the world it was optimised for (without capacity, the extra leads are workable)
        e = evaluate(rm.without_capacity() if c == "sales_capacity" else rm, sol.x, cfg)
        pc.append(
            {
                "policy_removed": c,
                "solved": sol.success,
                "expected_profit_gain": e["expected_profit"] - base["expected_profit"],
                "downside_profit_change": e["downside_profit"] - base["downside_profit"],
            }
        )
    policy_costs = pd.DataFrame(pc)

    step = float(rc["budget_step"])
    bv = {}
    for sign in (+1, -1):
        sol = optimise(rm, cfg, Setting(s.last_year, caps, tested, budget=budget + sign * step))
        bv["plus" if sign > 0 else "minus"] = (
            (evaluate(rm, sol.x, cfg)["expected_profit"] - base["expected_profit"]) / step * sign
        )
    budget_value = {"next_dollar": bv["plus"], "last_dollar": bv["minus"], "step": step}

    rows = []
    for name in ("status_quo", "recommended"):
        x = allocations[name]
        m = rm.effective_marginal(x) * rm.value
        for i, (b, ch) in enumerate(rm.lines):
            rows.append(
                {
                    "allocation": name,
                    "business": b,
                    "channel": ch,
                    "tested": f"{b}.{ch}" in tested,
                    "annual_spend": 52 * x[i],
                    "marginal_return": float(m[:, i].mean()),
                    "marginal_p10": float(np.quantile(m[:, i], 0.1)),
                    "marginal_p90": float(np.quantile(m[:, i], 0.9)),
                }
            )
    marginal = pd.DataFrame(rows)

    # Which untested lines most deserve a test: spend at stake x how uncertain the next dollar's return is
    sq = marginal[marginal["allocation"] == "status_quo"]
    nt = sq[~sq["tested"]].assign(
        uncertainty=lambda d: d["marginal_p90"] - d["marginal_p10"],
        stake=lambda d: d["annual_spend"] * (d["marginal_p90"] - d["marginal_p10"]),
    )
    next_tests = nt.sort_values("stake", ascending=False)[
        ["business", "channel", "annual_spend", "marginal_return", "marginal_p10", "marginal_p90", "stake"]
    ].reset_index(drop=True)

    calibration = pd.concat([calibration_check(fb).assign(business=b) for b, fb in fits.items()], ignore_index=True)
    return Plan(
        rm,
        rm_uncal,
        s,
        allocations,
        evaluation,
        policy_costs,
        budget_value,
        marginal,
        calibration,
        next_tests,
        values,
        {
            "capacity": capacity,
            "win_rates": wr,
            "cac_caps": caps,
            "n_draws": n_draws,
            "n_weeks": len(data[cfg.businesses[0]].y),
            "fits": fits,
        },
    )


def save_fits(plan: Plan, cfg: Config) -> None:
    """Keep the fitted curves so phase 5 can re-optimise without refitting (several minutes)."""
    import pickle

    path = cfg.path("artifacts_dir") / "response_fits.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(plan.extras["fits"], f)


def load_fits(cfg: Config) -> dict[str, FittedBusiness]:
    import pickle

    with (cfg.path("artifacts_dir") / "response_fits.pkl").open("rb") as f:
        fits: dict[str, FittedBusiness] = pickle.load(f)
    return fits
