"""Score phase 2 against the SYNTHETIC ground truth: the true elasticity of weekly customers to spend.

True elasticity in week t = sum over lines of spend x d(incremental customers)/d(spend), divided by all
customers that week, at sustained spend (adstock steady state, so d adstock / d spend = 1). Averaged over the
156 weeks. Comparable with the observational regression's elasticity.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.curves import hill_marginal


def true_elasticity(truth: dict[str, Any], truth_weekly: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for biz, b in truth["businesses"].items():
        close = float(b["qualified_to_customer"])
        cust = series[series["business"] == biz].sort_values("week_start")["customers"].to_numpy(float)
        num = np.zeros(len(cust))
        w = truth_weekly[truth_weekly["business"] == biz]
        for ch, p in b["channels"].items():
            x = w[w["channel"] == ch].sort_values("week_start")
            marg = hill_marginal(x["adstock"].to_numpy(), p["vmax_leads"], p["half_sat"], p["shape"])
            num += x["spend"].to_numpy() * x["demand_index"].to_numpy() * marg * float(p["lead_to_qualified"]) * close
        rows.append({"business": biz, "true_elasticity": float(np.mean(num / np.maximum(cust, 0.5)))})
    return pd.DataFrame(rows)
