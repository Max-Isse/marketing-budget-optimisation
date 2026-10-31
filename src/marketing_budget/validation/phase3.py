"""Score phase 3 against the SYNTHETIC ground truth.

1. Did each experiment's confidence interval contain the true effect?
2. Is the region-test method itself sound? Re-run each region test as designed with fresh random draws many
   times: the average estimate should match the average true effect, and the 95% intervals should contain
   the truth about 95% of the time. One experiment cannot show this; repetition can.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.experiments.analyze import geo_test
from marketing_budget.experiments.design import assign_regions
from marketing_budget.experiments.results import ExperimentResults
from marketing_budget.synthetic import experiments as sx

USER_TESTS = {
    ("landing_page", "conversion rate"): "landing_page",
    ("ad_creative", "click-through rate"): "ad_creative",
    ("audience_targeting", "leads per $"): "audience_targeting_leads",
    ("audience_targeting", "qualified leads per $"): "audience_targeting_qualified",
}


def score_experiments(res: ExperimentResults, truth_table: pd.DataFrame) -> pd.DataFrame:
    t = truth_table.set_index(["experiment", "metric"])["true_value"]
    rows = []
    for r in res.effects.to_dict("records"):
        key = USER_TESTS.get((r["experiment"], r["metric"]))
        if key is not None:
            true = float(t[(key, "relative_effect")])
            rows.append(
                {
                    "experiment": r["experiment"],
                    "metric": r["metric"],
                    "estimate": r["relative_effect"],
                    "ci_low": r["ci_low"],
                    "ci_high": r["ci_high"],
                    "true_value": true,
                }
            )
    for name, g in res.geo.items():
        s = g.summary
        rows.append(
            {
                "experiment": name,
                "metric": "incremental customers in treated regions",
                "estimate": s["incremental_customers"],
                "ci_low": s["incremental_ci_low"],
                "ci_high": s["incremental_ci_high"],
                "true_value": float(t[(name, "true_incremental_customers")]),
            }
        )
    out = pd.DataFrame(rows)
    out["true_in_ci"] = (out["true_value"] >= out["ci_low"]) & (out["true_value"] <= out["ci_high"])
    return out


def geo_monte_carlo(
    truth: dict[str, Any],
    tw: pd.DataFrame,
    tests: dict[str, dict[str, Any]],
    design: pd.DataFrame,
    shares: np.ndarray,
    reps: int,
    seed: int,
) -> pd.DataFrame:
    rows = []
    d: dict[Any, dict[Any, Any]] = design.set_index("experiment").to_dict("index")
    for name, spec in tests.items():
        share, weeks = float(d[name]["treated_share"]), int(d[name]["weeks_test"])
        est, tru, cov = [], [], []
        for k in range(reps):
            s_ = seed + 1000 * k
            pre, _ = sx.simulate_geo(truth, tw, name, spec, shares, None, s_)
            a = assign_regions(pre, share, s_ + 50)
            order = pre.groupby("region")["customers"].sum().sort_values().index
            blocks = pd.Series({r: j // round(1 / share) for j, r in enumerate(order)})
            panel, true = sx.simulate_geo(truth, tw, name, spec, shares, a, s_, weeks)
            summ = geo_test(panel, blocks, 1, s_).summary
            est.append(summ["incremental_customers"])
            tru.append(true["true_incremental_customers"])
            cov.append(summ["incremental_ci_low"] <= true["true_incremental_customers"] <= summ["incremental_ci_high"])
        rows.append(
            {
                "experiment": name,
                "repetitions": reps,
                "mean_estimate": float(np.mean(est)),
                "mean_true_effect": float(np.mean(tru)),
                "bias_in_standard_errors": float((np.mean(est) - np.mean(tru)) / (np.std(est, ddof=1) / np.sqrt(reps))),
                "ci_coverage": float(np.mean(cov)),
            }
        )
    return pd.DataFrame(rows)
