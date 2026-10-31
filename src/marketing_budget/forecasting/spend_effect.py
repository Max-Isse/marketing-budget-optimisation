"""What historical data alone says about the effect of spend, and why it should not be trusted as causal.

Regress log weekly customers on log spend (this week and last) with and without trend and seasonality
controls. The sum of the two spend coefficients is the implied elasticity: % change in customers for a 1%
sustained change in spend. Budgets rose in high-demand months, so without controls the regression credits
spend with the demand it followed. With controls the bias shrinks, but it only disappears if the controls
capture *everything* that moved both spend and sales, and nothing in observational data can prove that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from marketing_budget.config import Config
from marketing_budget.forecasting.models import fourier


def observational_elasticity(series: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    f = cfg.section("forecasting")
    rows = []
    for biz, g in series.groupby("business"):
        g = g.reset_index(drop=True)
        t = np.arange(len(g), dtype=float)
        y = np.log(np.maximum(g["customers"].to_numpy(float), 0.5))
        ls = np.log(g["spend"].to_numpy(float))
        ll = np.concatenate([[ls[0]], ls[:-1]])
        specs = {
            "spend only": np.column_stack([ls, ll]),
            "spend + trend + seasonality": np.column_stack(
                [ls, ll, t / 52, fourier(t, float(f["season_weeks"]), int(f["fourier_terms"]))]
            ),
        }
        for name, X in specs.items():
            fit = sm.OLS(y, sm.add_constant(X)).fit()
            p, c = np.asarray(fit.params), np.asarray(fit.cov_params())
            est = p[1] + p[2]
            se = float(np.sqrt(c[1, 1] + c[2, 2] + 2 * c[1, 2]))
            rows.append(
                {
                    "business": biz,
                    "specification": name,
                    "elasticity": est,
                    "ci_low": est - 1.96 * se,
                    "ci_high": est + 1.96 * se,
                    "r_squared": float(fit.rsquared),
                }
            )
    return pd.DataFrame(rows)
