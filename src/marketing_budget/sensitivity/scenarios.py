"""Re-optimise the plan under alternative assumptions and compare.

Three kinds of scenario:
* valuation - how customers are valued (horizon, discount rate, customer value): recompute values and payback
  limits, keep the curves
* policy    - management choices (payback targets, floors, guardrail, capacity, budget): change the constraints,
  keep the curves
* model     - how the curves were estimated (experiment results at their 95% limits, curve shape, the organic
  floor, prior strength): refit with fewer draws (`sensitivity.refit_draws`)

Each scenario's plan is scored under its own assumptions and under the base assumptions. The second is the
regret: what the plan would cost if the scenario's assumption were wrong.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.analysis.retention import estimate_retention
from marketing_budget.config import Config
from marketing_budget.optimisation.inputs import last_year_spend, values_and_caps, win_rates
from marketing_budget.optimisation.mmm import FittedBusiness, fit_business, load_business_data
from marketing_budget.optimisation.optimiser import Setting, evaluate, optimise, status_quo
from marketing_budget.optimisation.plan import _capacity
from marketing_budget.optimisation.response import ResponseModel, from_fits


@dataclass
class Scenario:
    name: str
    group: str  # valuation | policy | model
    description: str
    changes: dict[str, Any] = field(default_factory=dict)  # dotted config path -> value
    value_scale: dict[str, float] = field(default_factory=dict)  # business -> multiplier on customer value
    calibration_shift: float = 0.0  # move each experiment result by this many standard errors (+ = worth more)
    refit: bool = False


SCENARIOS = [
    Scenario("base", "base", "The recommended plan (phase 4)"),
    Scenario(
        "horizon_12m", "valuation", "Value customers over 12 months instead of 24", {"valuation.horizon_months": 12}
    ),
    Scenario("horizon_36m", "valuation", "Value customers over 36 months", {"valuation.horizon_months": 36}),
    Scenario("discount_5pct", "valuation", "Discount rate 5% instead of 10%", {"valuation.annual_discount_rate": 0.05}),
    Scenario("discount_15pct", "valuation", "Discount rate 15%", {"valuation.annual_discount_rate": 0.15}),
    Scenario("b2_value_minus_20", "valuation", "B2 customers worth 20% less", value_scale={"B2": 0.8}),
    Scenario(
        "all_values_minus_20",
        "valuation",
        "Every customer worth 20% less",
        value_scale={"B1": 0.8, "B2": 0.8, "B3": 0.8},
    ),
    Scenario(
        "b3_payback_6m",
        "policy",
        "B3 payback within 6 months (the CFO's original target, D-011)",
        {"valuation.payback_target_months.B3": 6},
    ),
    Scenario(
        "no_brand_floor",
        "policy",
        "No 50% floor on B1 brand search",
        {"budget.channel_limits.overrides.B1.search_brand": {}},
    ),
    Scenario(
        "min_acquisition_100",
        "policy",
        "Keep 100% of each business's customer volume",
        {"budget.min_acquisition": {"B1": 1.0, "B2": 1.0, "B3": 1.0}},
    ),
    Scenario(
        "min_acquisition_75",
        "policy",
        "Keep only 75% of customer volume",
        {"budget.min_acquisition": {"B1": 0.75, "B2": 0.75, "B3": 0.75}},
    ),
    Scenario("guardrail_10", "policy", "Untested lines move at most 10%", {"budget.untested_line_guardrail": 0.10}),
    Scenario("guardrail_50", "policy", "Untested lines move up to 50%", {"budget.untested_line_guardrail": 0.50}),
    Scenario("no_guardrail", "policy", "No limit on untested lines", {"budget.untested_line_guardrail": 1e6}),
    Scenario(
        "b2_capacity_50",
        "policy",
        "B2 sales capacity 50 qualified leads a week (one more hire)",
        {"budget.sales_capacity.B2.max_qualified_leads_per_week": 50},
    ),
    Scenario(
        "tests_optimistic",
        "model",
        "Every experiment at the end of its 95% range where channels are worth more",
        calibration_shift=1.96,
        refit=True,
    ),
    Scenario(
        "tests_pessimistic",
        "model",
        "Every experiment at the end where channels are worth less",
        calibration_shift=-1.96,
        refit=True,
    ),
    Scenario(
        "curve_shape_0.7",
        "model",
        "Sharper diminishing returns (curve shape 0.7)",
        {"response_model.shape": 0.7},
        refit=True,
    ),
    Scenario(
        "curve_shape_1.5",
        "model",
        "S-shaped curves (shape 1.5): weak at low spend",
        {"response_model.shape": 1.5},
        refit=True,
    ),
    Scenario(
        "no_organic_floor",
        "model",
        "No floor on organic demand",
        {"response_model.organic_floor_sd_log": 1e6},
        refit=True,
    ),
    Scenario(
        "prior_tight",
        "model",
        "Half-saturation held close to average spend (prior sd 0.5)",
        {"response_model.half_sat_prior_sd_log": 0.5},
        refit=True,
    ),
    Scenario(
        "prior_loose",
        "model",
        "Half-saturation left nearly free (prior sd 3)",
        {"response_model.half_sat_prior_sd_log": 3.0},
        refit=True,
    ),
]


def _set(raw: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    node = raw
    # line keys contain a dot ("B1.search_brand"): rejoin the tail under `overrides`
    if keys[:3] == ["budget", "channel_limits", "overrides"] and len(keys) > 4:
        keys = [*keys[:3], ".".join(keys[3:])]
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def scenario_config(cfg: Config, sc: Scenario) -> Config:
    raw = copy.deepcopy(cfg.raw)
    for path, value in sc.changes.items():
        _set(raw, path, value)
    return Config(raw, cfg.root)


@dataclass
class Context:
    """What every scenario needs, loaded once."""

    base_cfg: Config
    estimates: pd.DataFrame
    last_year: dict[str, float]
    tested: set[str]
    wr: dict[str, float]
    fits: dict[str, FittedBusiness]
    data: dict[str, Any]
    base_rm: ResponseModel


def build_context(con: duckdb.DuckDBPyConnection, cfg: Config, fits: dict[str, FittedBusiness]) -> Context:
    import json

    est = estimate_retention(con, cfg).estimates
    values, _ = values_and_caps(est, cfg)
    wr = win_rates(con)
    cal = json.loads((cfg.path("artifacts_dir") / "experiment_calibration.json").read_text(encoding="utf-8"))
    tested = {f"{c['business']}.{c['channel']}" for c in cal}
    data = load_business_data(con, cfg)
    return Context(cfg, est, last_year_spend(con), tested, wr, fits, data, from_fits(fits, values, _capacity(cfg, wr)))


def _refit(ctx: Context, scfg: Config, sc: Scenario) -> dict[str, FittedBusiness]:
    n = int(ctx.base_cfg.section("sensitivity")["refit_draws"])
    out = {}
    for i, (b, d) in enumerate(ctx.data.items()):
        d2 = copy.copy(d)
        cal = []
        for c in d.calibration:
            # "worth more" = a bigger loss when switched off, a bigger gain when increased
            direction = -1.0 if float(c["spend_multiplier"]) < 1 else 1.0
            cal.append(
                {
                    **c,
                    "relative_effect": float(c["relative_effect"]) + direction * sc.calibration_shift * float(c["se"]),
                }
            )
        d2.calibration = cal
        out[b] = fit_business(d2, scfg, True, n, scfg.seed + 900 + i)
    return out


@dataclass
class ScenarioResult:
    scenario: Scenario
    cfg: Config
    rm: ResponseModel
    setting: Setting
    x: np.ndarray
    success: bool


def run_scenario(ctx: Context, sc: Scenario, budget: float | None = None) -> ScenarioResult:
    scfg = scenario_config(ctx.base_cfg, sc)
    values, caps = values_and_caps(ctx.estimates, scfg)
    values = {b: v * sc.value_scale.get(b, 1.0) for b, v in values.items()}
    fits = _refit(ctx, scfg, sc) if sc.refit else ctx.fits
    rm = from_fits(fits, values, _capacity(scfg, ctx.wr))
    s = Setting(ctx.last_year, caps, ctx.tested, budget=budget)
    sol = optimise(rm, scfg, s)
    return ScenarioResult(sc, scfg, rm, s, sol.x, sol.success)


def summarise(ctx: Context, results: list[ScenarioResult], move_threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per scenario, and a line x scenario table of spend changes from last year."""
    base = next(r for r in results if r.scenario.name == "base")
    rows, changes = [], {}
    last = np.array([ctx.last_year[f"{b}.{c}"] for b, c in base.rm.lines])
    for r in results:
        cfg = r.cfg
        sq = status_quo(r.rm, r.setting, 52 * r.x.sum())
        own, own_sq = evaluate(r.rm, r.x, cfg), evaluate(r.rm, sq, cfg)
        under_base = evaluate(ctx.base_rm, r.x, ctx.base_cfg)
        base_sq = evaluate(ctx.base_rm, status_quo(ctx.base_rm, r.setting, 52 * r.x.sum()), ctx.base_cfg)
        rel = 52 * r.x / (last / last.sum() * 52 * r.x.sum()) - 1  # change vs last year's split at this budget
        changes[r.scenario.name] = rel
        moved_base = np.abs(52 * base.x / last * last.sum() / (52 * base.x.sum()) - 1) > move_threshold
        same_dir = np.sign(rel[moved_base]) == np.sign(
            (52 * base.x / (last / last.sum() * 52 * base.x.sum()) - 1)[moved_base]
        )
        rows.append(
            {
                "scenario": r.scenario.name,
                "group": r.scenario.group,
                "description": r.scenario.description,
                "solved": r.success,
                "gain_own_assumptions": own["expected_profit"] - own_sq["expected_profit"],
                "downside_gain_own": own["downside_profit"] - own_sq["downside_profit"],
                "gain_under_base_assumptions": under_base["expected_profit"] - base_sq["expected_profit"],
                "share_of_budget_moved_vs_base": float(np.abs(r.x - base.x).sum() / (2 * base.x.sum())),
                "base_moves_kept": float(same_dir.mean()) if len(same_dir) else np.nan,
                **{f"spend_{b}": own[f"spend_{b}"] for b in r.rm.businesses},
            }
        )
    ch = pd.DataFrame(changes, index=pd.Index([f"{b}.{c}" for b, c in base.rm.lines], name="line")).reset_index()
    return pd.DataFrame(rows), ch


def no_regret(
    changes: pd.DataFrame, solved: dict[str, bool], threshold: float, tested: set[str] | None = None
) -> pd.DataFrame:
    """Per line: does every (solved) scenario move it the same way? Budget-size scenarios are excluded.

    For a line with no experiment, agreement across scenarios is weak evidence: every scenario reuses the same
    history, so they can all share its bias. The `evidence` column says which kind of line it is."""
    cols = [c for c in changes.columns if c != "line" and solved.get(c, False)]
    out = []
    for _, r in changes.iterrows():
        v = r[cols].to_numpy(float)
        up, down = (v > threshold).mean(), (v < -threshold).mean()
        verdict = (
            "no-regret increase"
            if up == 1
            else "no-regret cut"
            if down == 1
            else "mostly increase"
            if up >= 0.75
            else "mostly cut"
            if down >= 0.75
            else "depends on assumptions"
        )
        out.append(
            {
                "line": r["line"],
                "base_change": float(r["base"]),
                "lowest_change": float(v.min()),
                "highest_change": float(v.max()),
                "share_increase": float(up),
                "share_cut": float(down),
                "verdict": verdict,
                "evidence": "experiment" if tested is not None and r["line"] in tested else "history only",
            }
        )
    return pd.DataFrame(out)


def budget_curve(
    ctx: Context, budgets: list[float], progress: Callable[[str], None] | None = None
) -> tuple[pd.DataFrame, dict[float, np.ndarray]]:
    base = SCENARIOS[0]
    rows, plans = [], {}
    for b in budgets:
        r = run_scenario(ctx, base, budget=float(b))
        if progress:
            progress(f"budget {b:,.0f}: {'solved' if r.success else 'infeasible'}")
        e = evaluate(r.rm, r.x, r.cfg) if r.success else {}
        rows.append(
            {
                "budget": b,
                "solved": r.success,
                "expected_profit": e.get("expected_profit", np.nan),
                "downside_profit": e.get("downside_profit", np.nan),
                "p90_profit": e.get("p90_profit", np.nan),
                "incremental_customers": e.get("incremental_customers", np.nan),
            }
        )
        if r.success:
            plans[float(b)] = r.x
    return pd.DataFrame(rows), plans
