"""Run the designed experiments in the SYNTHETIC world.

The analyst's plan (sample sizes, durations, region assignment) comes from experiments/design.py; how the
world responds comes from the ground truth. Region tests use the last 24 weeks of the data window
(8 pre-period weeks, then a test of up to 16 weeks). Each region is a scaled copy of the national business:
its share times the national response curve at the region's national-equivalent spend. Experiment results are
not fed back into the national weekly tables (a simplification: tests touch a minority of regions for a few
weeks).

Also returns the true effects, which only validation/ may read.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.curves import adstock, hill
from marketing_budget.synthetic.generate import _lognormal_unit, _nb

PRE, MAX_TEST = 8, 16
WINDOW = PRE + MAX_TEST  # region tests use the last 24 weeks: 8 pre-period weeks, then up to 16 test weeks


def regions(truth: dict[str, Any], seed: int) -> np.ndarray:
    g = truth["experiments"]["geo"]
    rng = np.random.default_rng(seed)
    return rng.dirichlet(np.full(int(g["n_regions"]), float(g["region_concentration"])))


def _line_expected(
    truth: dict[str, Any], tw: pd.DataFrame, biz: str, ch: str, mult_test: float, inc_change: float, test_weeks: int
) -> np.ndarray:
    """National-equivalent expected incremental customers for one line over the 24-week window."""
    b = truth["businesses"][biz]
    p = b["channels"][ch]
    x = tw[(tw["business"] == biz) & (tw["channel"] == ch)].sort_values("week_start")
    n = len(x)
    test = slice(n - WINDOW + PRE, n - WINDOW + PRE + test_weeks)
    spend = x["spend"].to_numpy(float).copy()
    spend[test] *= mult_test
    ad = adstock(spend, p["decay"])
    leads = x["demand_index"].to_numpy() * hill(ad, p["vmax_leads"], p["half_sat"], p["shape"])
    cust = leads * float(p["lead_to_qualified"]) * float(b["qualified_to_customer"])
    cust[test] *= 1 + inc_change
    return cust[n - WINDOW :]


def geo_expected(
    truth: dict[str, Any], tw: pd.DataFrame, biz: str, ch: str, spec: dict[str, Any], treated: bool, test_weeks: int
) -> dict[str, np.ndarray]:
    """National-equivalent expected weekly values over the 24-week window, for one arm of a region test."""
    b = truth["businesses"][biz]
    p = b["channels"][ch]
    bid = truth["experiments"]["bidding"]
    tcpa = spec["treatment"] == "tcpa" and treated
    mult = float(spec.get("spend_multiplier", 1.0)) if treated and spec["treatment"] == "spend" else 1.0
    inc_change = float(bid["incremental_customer_change"]) if tcpa else 0.0
    x = tw[(tw["business"] == biz) & (tw["channel"] == ch)].sort_values("week_start")
    weeks = x["week_start"].to_numpy()[-WINDOW:]
    demand = x["demand_index"].to_numpy()[-WINDOW:]
    organic = float(b["organic_customers_per_week"]) * demand
    line = _line_expected(truth, tw, biz, ch, mult, inc_change, test_weeks)
    others = np.zeros(WINDOW)
    for other in b["channels"]:
        if other != ch:
            others += _line_expected(truth, tw, biz, other, 1.0, 0.0, test_weeks)
    spend = x["spend"].to_numpy(float)[-WINDOW:].copy()
    test = slice(PRE, PRE + test_weeks)
    spend[test] *= mult
    on = spend > 0
    last_click = (line + float(p["attribution_capture"]) * organic) * on
    platform = last_click * float(p["platform_overclaim"])
    if tcpa:
        platform[test] = platform[test] / (1 + float(bid["platform_cpa_change"]))
    return {
        "week_start": weeks,
        "customers": organic + line + others,
        "line_spend": spend,
        "line_last_click": last_click,
        "line_platform": platform,
    }


def simulate_geo(
    truth: dict[str, Any],
    tw: pd.DataFrame,
    name: str,
    spec: dict[str, Any],
    shares: np.ndarray,
    assignment: pd.DataFrame | None,
    seed: int,
    test_weeks: int = MAX_TEST,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Region x week panel for one test (pre-period + test weeks). With assignment=None only the pre-period
    is returned, to design the assignment; it is identical whatever is assigned later, because the pre and
    test periods are drawn from separate random streams."""
    g = truth["experiments"]["geo"]
    rng = np.random.default_rng(seed)
    rng_pre, rng_test = np.random.default_rng(seed + 1), np.random.default_rng(seed + 2)
    biz, ch = spec["business"], spec["channel"]
    ctrl = geo_expected(truth, tw, biz, ch, spec, treated=False, test_weeks=test_weeks)
    trt = geo_expected(truth, tw, biz, ch, spec, treated=True, test_weeks=test_weeks)
    n_r = len(shares)
    region_factor = _lognormal_unit(rng, 0.10, n_r)
    shock = _lognormal_unit(rng, float(g["region_week_sd"]), n_r * WINDOW).reshape(n_r, WINDOW)
    size = float(truth["noise"]["count_dispersion"])
    is_t = np.zeros(n_r, bool) if assignment is None else assignment.set_index("region")["treated"].to_numpy()
    scale = (shares * region_factor)[:, None] * shock
    span = PRE + test_weeks

    def draw(key: str, count: str) -> np.ndarray:
        mean = np.where(is_t[:, None], trt[key][None, :], ctrl[key][None, :]) * scale
        out = np.zeros(mean.shape, dtype=int)
        for part, r in ((slice(0, PRE), rng_pre), (slice(PRE, WINDOW), rng_test)):
            m = mean[:, part].ravel()
            out[:, part] = (_nb(r, m, size) if count == "nb" else r.poisson(m)).reshape(n_r, -1)
        return out[:, :span]

    cust, lc, plat = draw("customers", "nb"), draw("line_last_click", "pois"), draw("line_platform", "pois")
    spend = np.where(is_t[:, None], trt["line_spend"][None, :], ctrl["line_spend"][None, :])
    spend = (spend * (shares * region_factor)[:, None])[:, :span]
    panel = pd.concat(
        [
            pd.DataFrame(
                {
                    "experiment": name,
                    "business": biz,
                    "channel": ch,
                    "region": r,
                    "week": np.arange(span),
                    "week_start": ctrl["week_start"][:span],
                    "period": np.where(np.arange(span) < PRE, "pre", "test"),
                    "treated": bool(is_t[r]),
                    "line_spend": np.round(spend[r], 2),
                    "customers": cust[r],
                    "line_last_click_customers": lc[r],
                    "line_platform_conversions": plat[r],
                }
            )
            for r in range(n_r)
        ],
        ignore_index=True,
    )
    if assignment is None:
        return panel[panel["period"] == "pre"].reset_index(drop=True), {}
    t_idx = np.nonzero(is_t)[0]
    w = (shares * region_factor)[t_idx]
    test = slice(PRE, span)
    true_inc = float(w.sum() * (trt["customers"][test] - ctrl["customers"][test]).sum())
    base = float(w.sum() * ctrl["customers"][test].sum())
    dspend = float(w.sum() * (trt["line_spend"][test] - ctrl["line_spend"][test]).sum())
    return panel, {
        "true_incremental_customers": true_inc,
        "true_relative_effect": true_inc / base,
        "true_spend_change": dspend,
    }


def simulate_landing_page(truth: dict[str, Any], weeks: int, seed: int) -> pd.DataFrame:
    t = truth["experiments"]["landing_page"]
    rng = np.random.default_rng(seed)
    n = int(rng.poisson(float(t["weekly_visitors"]) * weeks))
    devices = list(t["device_mix"])
    mix = np.array([t["device_mix"][d] for d in devices])
    ratio = np.array([t["device_conversion_ratio"][d] for d in devices])
    ratio = ratio / (mix * ratio).sum()  # overall baseline stays at baseline_conversion
    dev = rng.choice(len(devices), n, p=mix)
    arm = rng.integers(0, 2, n)
    p = float(t["baseline_conversion"]) * ratio[dev] * np.where(arm == 1, 1 + float(t["true_relative_uplift"]), 1.0)
    return pd.DataFrame(
        {
            "visitor_id": np.arange(n),
            "day": rng.integers(0, weeks * 7, n),
            "arm": np.where(arm == 1, "new_page", "current_page"),
            "device": np.array(devices)[dev],
            "converted": rng.random(n) < p,
        }
    ).sort_values(["day", "visitor_id"], ignore_index=True)


def simulate_creative(truth: dict[str, Any], weeks: int, weekly_users: float, seed: int) -> pd.DataFrame:
    t = truth["experiments"]["ad_creative"]
    rng = np.random.default_rng(seed)
    n = int(rng.poisson(weekly_users * weeks))
    arm = rng.integers(0, 2, n)
    imps = 1 + rng.poisson(float(t["extra_impressions_per_user"]), n)
    mean = float(t["baseline_ctr"]) * np.where(arm == 1, 1 + float(t["true_relative_uplift"]), 1.0)
    k = float(t["ctr_concentration"])
    user_ctr = rng.beta(mean * k, (1 - mean) * k)
    return pd.DataFrame(
        {
            "user_id": np.arange(n),
            "day": rng.integers(0, weeks * 7, n),
            "arm": np.where(arm == 1, "creative_b", "creative_a"),
            "impressions": imps,
            "clicks": rng.binomial(imps, user_ctr),
        }
    )


def simulate_audience(truth: dict[str, Any], plan: dict[str, Any], seed: int) -> pd.DataFrame:
    t = truth["experiments"]["audience_targeting"]
    b = truth["businesses"]["B2"]
    p = b["channels"]["linkedin"]
    rng = np.random.default_rng(seed)
    weeks = int(plan["weeks"])
    leads_per_arm = float(plan["weekly_leads"]) / 2
    q = float(p["lead_to_qualified"])
    close = float(b["qualified_to_customer"])
    rows = []
    for arm, vol, qual in (
        ("job_title", 1.0, 1.0),
        ("lookalike", 1 + float(t["lead_volume_change"]), 1 + float(t["qualification_change"])),
    ):
        for w in range(weeks):
            k = int(rng.poisson(leads_per_arm * vol))
            qualified = rng.random(k) < q * qual
            won = qualified & (rng.random(k) < close)
            rows.append(
                pd.DataFrame(
                    {
                        "arm": arm,
                        "week": w,
                        "arm_week_spend": float(plan["weekly_spend"]) / 2,
                        "is_qualified": qualified,
                        "is_won": won,
                    }
                )
            )
    out = pd.concat(rows, ignore_index=True)
    out.insert(0, "lead_id", np.arange(len(out)))
    return out


def true_user_effects(truth: dict[str, Any]) -> dict[str, float]:
    e = truth["experiments"]
    a = e["audience_targeting"]
    return {
        "landing_page": float(e["landing_page"]["true_relative_uplift"]),
        "ad_creative": float(e["ad_creative"]["true_relative_uplift"]),
        "audience_targeting_leads": float(a["lead_volume_change"]),
        "audience_targeting_qualified": (1 + float(a["lead_volume_change"])) * (1 + float(a["qualification_change"]))
        - 1,
    }
