"""Forward forecasts and optimistic / baseline / pessimistic scenarios.

The spend plan for the forecast is last year's weekly spend rolled forward: the "do what we did last year"
allocation that phase 4 compares against. Spend is a decision, so it is the same in every scenario. What
varies is how the market responds to it.

Scenario bands come from the backtest: the 10th, 50th and 90th percentiles of log(actual / forecast) for
13-week *totals* of the selected model. For the annual plan the same quarter-level band is applied to the
year's total. That is an assumption: a level error that persists for a quarter is assumed not to average
out over four.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.forecasting.backtest import HORIZON_BUCKETS, Intervals
from marketing_budget.forecasting.models import MODELS

SCENARIO_Q = {"pessimistic": 0.10, "baseline": 0.50, "optimistic": 0.90}
LOWER_IS_BETTER = {"cac"}


def spend_plan(df: pd.DataFrame, weeks: int) -> pd.DataFrame:
    """Future weeks with last year's spend in the same week (week t uses t - 52)."""
    n = len(df)
    t = np.arange(n, n + weeks)
    spend = df.set_index("t")["spend"]
    last = df["week_start"].iloc[-1]
    return pd.DataFrame(
        {
            "t": t,
            "week_start": [last + pd.Timedelta(weeks=int(k - n + 1)) for k in t],
            "spend": [float(spend[k - 52]) if k - 52 in spend.index else float(spend.iloc[-1]) for k in t],
        }
    )


@dataclass
class ForwardForecast:
    weekly: pd.DataFrame  # business, target, model, week_start, horizon, forecast, low, high
    scenarios: pd.DataFrame  # business, target, period, scenario, value
    plan: pd.DataFrame  # business, week_start, spend


def forward(
    series: pd.DataFrame, selected: pd.DataFrame, intervals: Intervals, totals: pd.DataFrame, cfg: Config
) -> ForwardForecast:
    f = cfg.section("forecasting")
    h = int(f["horizon_weeks"])
    pick = selected.set_index(["business", "target"])["selected"]
    q = intervals.quantiles.set_index(["business", "target", "model", "horizon_bucket"])
    weekly, scen, plans = [], [], []
    for biz, df in series.groupby("business"):
        df = df.reset_index(drop=True)
        plan = spend_plan(df, 52)
        plans.append(plan.assign(business=biz))
        fc: dict[str, np.ndarray] = {}
        for target in f["targets"]:
            model = str(pick[(biz, target)])
            pred = MODELS[model](df, plan, target, cfg) if target != "spend" else plan["spend"].to_numpy(float)
            fc[target] = pred
            horizon = np.arange(1, len(plan) + 1)
            bucket = [next((f"{lo}-{hi}" for lo, hi in HORIZON_BUCKETS if lo <= k <= hi), "9-13") for k in horizon]
            lo = np.array([q.loc[(biz, target, model, b), "q_low"] for b in bucket])
            hi = np.array([q.loc[(biz, target, model, b), "q_high"] for b in bucket])
            weekly.append(
                pd.DataFrame(
                    {
                        "business": biz,
                        "target": target,
                        "model": model if target != "spend" else "plan",
                        "week_start": plan["week_start"],
                        "horizon": horizon,
                        "forecast": pred,
                        "low": pred * np.exp(lo) if target != "spend" else pred,
                        "high": pred * np.exp(hi) if target != "spend" else pred,
                        "beyond_validated_horizon": horizon > h,
                    }
                )
            )
        for period, weeks in (("next quarter", h), ("next 52 weeks", 52)):
            spend_total = float(plan["spend"].iloc[:weeks].sum())
            cust: dict[str, float] = {}
            for target in f["targets"]:
                base = float(fc[target][:weeks].sum())
                model = str(pick[(biz, target)])
                errs = totals[(totals["business"] == biz) & (totals["target"] == target) & (totals["model"] == model)]
                for name, qq in SCENARIO_Q.items():
                    scale = 1.0 if target == "spend" else float(np.exp(np.quantile(errs["log_err"], qq)))
                    val = spend_total if target == "spend" else base * scale
                    if target == "customers":
                        cust[name] = val
                    scen.append({"business": biz, "target": target, "period": period, "scenario": name, "value": val})
            for name in SCENARIO_Q:
                scen.append(
                    {
                        "business": biz,
                        "target": "cac",
                        "period": period,
                        "scenario": name,
                        "value": spend_total / cust[name],
                    }
                )
    return ForwardForecast(
        pd.concat(weekly, ignore_index=True), pd.DataFrame(scen), pd.concat(plans, ignore_index=True)
    )
