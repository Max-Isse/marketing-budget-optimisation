"""Score phase 5 against the SYNTHETIC ground truth.

* the true gain of every scenario's plan over last year's split (same budget)
* the true budget curve: what the model's plan really earns at each budget, and the best achievable
* whether the "no-regret" verdicts point the same way as the true optimum
* true payback of each business under the recommended plan, against its target
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.economics import customer_value
from marketing_budget.optimisation.optimiser import Setting, evaluate, optimise, status_quo
from marketing_budget.validation.phase4 import true_cac_caps, true_model, true_win_rates


def _truth(truth: dict[str, Any], cfg: Config, lines: list[tuple[str, str]], n_weeks: int) -> Any:
    tr = true_model(truth, cfg, lines, n_weeks)
    win = true_win_rates(truth)
    tr.capacity = {
        b: float(v["max_qualified_leads_per_week"]) * win[b]
        for b, v in cfg.section("budget").get("sales_capacity", {}).items()
    }
    return tr


def score_sensitivity(
    results: list[Any],
    curve: pd.DataFrame,
    curve_plans: dict[float, np.ndarray],
    verdicts: pd.DataFrame,
    truth: dict[str, Any],
    cfg: Config,
    n_weeks: int,
) -> dict[str, pd.DataFrame]:
    base = next(r for r in results if r.scenario.name == "base")
    tr = _truth(truth, cfg, base.rm.lines, n_weeks)
    caps = true_cac_caps(truth, cfg)

    rows = []
    for r in results:
        b = 52 * r.x.sum()
        sq = status_quo(tr, r.setting, b)
        rows.append(
            {
                "scenario": r.scenario.name,
                "true_gain": evaluate(tr, r.x, cfg)["expected_profit"] - evaluate(tr, sq, cfg)["expected_profit"],
            }
        )
    scen = pd.DataFrame(rows)

    crow = []
    for b in curve["budget"]:
        s = Setting(base.setting.last_year, caps, base.setting.tested, {"downside", "untested_guardrail"}, float(b))
        best = optimise(tr, cfg, s)
        x = curve_plans.get(float(b))
        crow.append(
            {
                "budget": b,
                "true_profit_of_model_plan": evaluate(tr, x, cfg)["expected_profit"] if x is not None else np.nan,
                "true_profit_of_last_years_split": evaluate(tr, status_quo(tr, s, float(b)), cfg)["expected_profit"],
                "true_best_achievable": evaluate(tr, best.x, cfg)["expected_profit"] if best.success else np.nan,
            }
        )
    tcurve = pd.DataFrame(crow)

    best = optimise(
        tr, cfg, Setting(base.setting.last_year, caps, base.setting.tested, {"downside", "untested_guardrail"})
    )
    last = np.array([base.setting.last_year[f"{b}.{c}"] for b, c in base.rm.lines])
    true_change = 52 * best.x / (last / last.sum() * 52 * best.x.sum()) - 1
    v = verdicts.copy()
    v["true_optimum_change"] = true_change
    v["direction_right"] = np.select(
        [v["verdict"].str.contains("increase"), v["verdict"].str.contains("cut")],
        [v["true_optimum_change"] > 0, v["true_optimum_change"] < 0],
        default=np.nan,
    )

    pay = []
    eff = tr.effective_customers(base.x)[0]
    for b in tr.businesses:
        i = tr.idx(b)
        cac = float(base.x[i].sum() / eff[i].sum())
        model_eff = base.rm.effective_customers(base.x)[:, i].sum(axis=1).mean()
        bt = truth["businesses"][b]
        cv = customer_value(bt["model"], bt["economics"], 60, float(cfg.section("valuation")["annual_discount_rate"]))
        pay.append(
            {
                "business": b,
                "true_payback_months": cv.payback_months(cac),
                "target_months": int(cfg.section("valuation")["payback_target_months"][b]),
                "true_incremental_cac": cac,
                "model_incremental_cac": float(base.x[i].sum() / model_eff),
                "true_cac_limit_for_target": caps[b],
                "meets_target_in_truth": cac <= caps[b],
            }
        )
    return {"scenarios": scen, "budget_curve": tcurve, "verdicts": v, "payback": pd.DataFrame(pay)}
