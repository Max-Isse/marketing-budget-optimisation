"""Experiment analysis. Every estimate here is *causal* evidence: the treatment was randomised.

* landing page   two-proportion test on conversion; relative uplift with a log-ratio CI; device segments with
                 a Holm correction (several looks at the same experiment inflate false positives)
* ad creative    click-through rate is a ratio of sums over users, and clicks of one user are correlated.
                 The delta method on user-level totals gives the right standard error; the naive
                 impression-level one is shown alongside to show how much it understates
* audience       Poisson rate ratios: leads, qualified leads and customers per dollar
* region tests   ANCOVA: test-period customers ~ treated + pre-period customers, region level, HC2 robust
                 errors with t critical values; p-value from randomisation inference (re-assigning treatment
                 within the same blocks)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


def two_proportions(x_a: float, n_a: float, x_b: float, n_b: float, alpha: float = 0.05) -> dict[str, float]:
    """B vs A. Relative uplift p_b / p_a - 1 with a CI on the log ratio."""
    pa, pb = x_a / n_a, x_b / n_b
    z = stats.norm.ppf(1 - alpha / 2)
    pool = (x_a + x_b) / (n_a + n_b)
    zstat = (pb - pa) / np.sqrt(pool * (1 - pool) * (1 / n_a + 1 / n_b))
    se_log = np.sqrt((1 - pa) / x_a + (1 - pb) / x_b)
    rr = pb / pa
    return {
        "rate_a": pa,
        "rate_b": pb,
        "n_a": n_a,
        "n_b": n_b,
        "relative_effect": rr - 1,
        "ci_low": float(rr * np.exp(-z * se_log) - 1),
        "ci_high": float(rr * np.exp(z * se_log) - 1),
        "p_value": float(2 * stats.norm.sf(abs(zstat))),
    }


def ratio_delta(num: np.ndarray, den: np.ndarray) -> tuple[float, float]:
    """Ratio of sums and the delta-method variance of that ratio, from per-unit (user) totals."""
    n = len(num)
    mx, my = den.mean(), num.mean()
    r = my / mx
    vx, vy = den.var(ddof=1), num.var(ddof=1)
    cxy = np.cov(num, den, ddof=1)[0, 1]
    var = (vy - 2 * r * cxy + r**2 * vx) / (mx**2 * n)
    return float(r), float(var)


def ctr_test(users: pd.DataFrame, alpha: float = 0.05) -> dict[str, float]:
    z = stats.norm.ppf(1 - alpha / 2)
    a, b = users[users["arm"] == "creative_a"], users[users["arm"] == "creative_b"]
    ra, va = ratio_delta(a["clicks"].to_numpy(float), a["impressions"].to_numpy(float))
    rb, vb = ratio_delta(b["clicks"].to_numpy(float), b["impressions"].to_numpy(float))
    se_log = np.sqrt(va / ra**2 + vb / rb**2)
    rr = rb / ra
    naive = two_proportions(a["clicks"].sum(), a["impressions"].sum(), b["clicks"].sum(), b["impressions"].sum())
    return {
        "rate_a": ra,
        "rate_b": rb,
        "n_a": float(a["impressions"].sum()),
        "n_b": float(b["impressions"].sum()),
        "relative_effect": rr - 1,
        "ci_low": float(rr * np.exp(-z * se_log) - 1),
        "ci_high": float(rr * np.exp(z * se_log) - 1),
        "p_value": float(2 * stats.norm.sf(abs(np.log(rr)) / se_log)),
        "naive_ci_low": naive["ci_low"],
        "naive_ci_high": naive["ci_high"],
        "naive_p_value": naive["p_value"],
        "se_ratio_delta_vs_naive": float(se_log / np.sqrt(1 / a["clicks"].sum() + 1 / b["clicks"].sum())),
    }


def rate_ratio(x_a: float, e_a: float, x_b: float, e_b: float, alpha: float = 0.05) -> dict[str, float]:
    """Poisson rates x / exposure, B vs A; exact conditional (binomial) p-value."""
    z = stats.norm.ppf(1 - alpha / 2)
    rr = (x_b / e_b) / (x_a / e_a)
    se = np.sqrt(1 / x_a + 1 / x_b)
    p = stats.binomtest(int(x_b), int(x_a + x_b), e_b / (e_a + e_b)).pvalue
    return {
        "rate_a": x_a / e_a,
        "rate_b": x_b / e_b,
        "n_a": x_a,
        "n_b": x_b,
        "relative_effect": rr - 1,
        "ci_low": float(rr * np.exp(-z * se) - 1),
        "ci_high": float(rr * np.exp(z * se) - 1),
        "p_value": float(p),
    }


def holm(p: list[float]) -> list[float]:
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(running, 1.0)
    return adj.tolist()


def cumulative_p(df: pd.DataFrame, arm_col: str, a: str, b: str, num: str, den: str | None) -> pd.DataFrame:
    """Naive two-proportion p-value at the end of each day, as an analyst who peeks daily would see it."""
    rows = []
    for d in sorted(df["day"].unique()):
        s = df[df["day"] <= d]
        sa, sb = s[s[arm_col] == a], s[s[arm_col] == b]
        if den is None:
            r = two_proportions(sa[num].sum(), len(sa), sb[num].sum(), len(sb))
        else:
            r = two_proportions(sa[num].sum(), sa[den].sum(), sb[num].sum(), sb[den].sum())
        rows.append({"day": int(d), "relative_effect": r["relative_effect"], "p_value": r["p_value"]})
    return pd.DataFrame(rows)


@dataclass
class GeoResult:
    summary: dict[str, Any]
    by_metric: pd.DataFrame


def _ancova(region: pd.DataFrame, outcome: str) -> tuple[float, float, float]:
    X = sm.add_constant(np.column_stack([region["treated"].astype(float), region[f"{outcome}_pre"]]))
    fit = sm.OLS(region[f"{outcome}_test"].to_numpy(float), X).fit(cov_type="HC2")
    return float(fit.params[1]), float(fit.bse[1]), float(fit.params[2])


def geo_test(panel: pd.DataFrame, blocks: pd.Series, permutations: int, seed: int, alpha: float = 0.05) -> GeoResult:
    """ANCOVA per outcome; effect per treated region over the test period, scaled to all treated regions.
    Intervals use t critical values (residual df = regions - 3): with 40 regions the normal value is too small."""
    metrics = ["customers", "line_last_click_customers", "line_platform_conversions", "line_spend"]
    g = pd.DataFrame(panel.groupby(["region", "period"])[metrics].sum().unstack("period"))
    g.columns = ["_".join(map(str, col)) for col in g.columns]
    region = g.join(panel.groupby("region")["treated"].first()).join(blocks.rename("block"))
    z = float(stats.t.ppf(1 - alpha / 2, df=len(region) - 3))
    n_t = int(region["treated"].sum())
    rows = []
    for m in metrics:
        eff, se, _ = _ancova(region, m)
        ctrl_mean = float(region.loc[~region["treated"], f"{m}_test"].mean())
        rows.append(
            {
                "metric": m,
                "effect_per_treated_region": eff,
                "ci_low": eff - z * se,
                "ci_high": eff + z * se,
                "total_effect": eff * n_t,
                "total_ci_low": (eff - z * se) * n_t,
                "total_ci_high": (eff + z * se) * n_t,
                "control_mean_per_region": ctrl_mean,
            }
        )
    by_metric = pd.DataFrame(rows)

    # randomisation inference on customers: re-draw treatment within blocks, recompute the ANCOVA effect
    rng = np.random.default_rng(seed)
    obs = float(by_metric.loc[by_metric["metric"] == "customers", "effect_per_treated_region"].iloc[0])
    perm = np.empty(permutations)
    blk = region["block"].to_numpy()
    tr = region["treated"].to_numpy()
    for i in range(permutations):
        new = tr.copy()
        for b in np.unique(blk):
            idx = np.nonzero(blk == b)[0]
            new[idx] = rng.permutation(tr[idx])
        perm[i] = _ancova(region.assign(treated=new), "customers")[0]
    p_ri = float((np.abs(perm) >= abs(obs)).mean())

    c = by_metric.set_index("metric").to_dict("index")
    pred_treated = float(region.loc[region["treated"], "customers_test"].sum() - c["customers"]["total_effect"])
    summary = {
        "n_regions": len(region),
        "n_treated": n_t,
        "incremental_customers": float(c["customers"]["total_effect"]),
        "incremental_ci_low": float(c["customers"]["total_ci_low"]),
        "incremental_ci_high": float(c["customers"]["total_ci_high"]),
        "relative_effect": float(c["customers"]["total_effect"]) / pred_treated,
        "relative_ci_low": float(c["customers"]["total_ci_low"]) / pred_treated,
        "relative_ci_high": float(c["customers"]["total_ci_high"]) / pred_treated,
        "p_value_randomisation": p_ri,
        "spend_change": float(c["line_spend"]["total_effect"]),
        "last_click_change": float(c["line_last_click_customers"]["total_effect"]),
        "platform_change": float(c["line_platform_conversions"]["total_effect"]),
    }
    return GeoResult(summary, by_metric)


def decide(ci_low: float, ci_high: float, threshold: float, higher_is_better: bool = True) -> str:
    """Statistical vs practical significance, in plain words. `threshold` is the smallest effect worth acting on."""
    lo, hi = (ci_low, ci_high) if higher_is_better else (-ci_high, -ci_low)
    if lo >= threshold:
        return "adopt: the effect is real and large enough to matter"
    if hi < 0:
        return "reject: it makes things worse"
    if lo > 0:
        return "real but possibly too small to be worth it"
    if hi < threshold:
        return "no worthwhile effect: even the best case is below the threshold"
    return "inconclusive: the test cannot tell; extend it or decide on other grounds"
