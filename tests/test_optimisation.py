import numpy as np
import pandas as pd
import pytest

from marketing_budget.config import Config
from marketing_budget.optimisation.mmm import MMM, BusinessData, fit_business
from marketing_budget.optimisation.optimiser import Setting, evaluate, line_limits, optimise, status_quo
from marketing_budget.optimisation.response import ResponseModel

LINES = [
    ("B1", "affiliates"),
    ("B1", "search_brand"),
    ("B1", "search_generic"),
    ("B1", "social_prospecting"),
    ("B2", "linkedin"),
    ("B2", "programmatic_display"),
    ("B2", "review_sites"),
    ("B2", "search_generic"),
    ("B3", "affiliates"),
    ("B3", "display_retargeting"),
    ("B3", "shopping"),
    ("B3", "social_prospecting"),
]
LAST = dict(
    zip(
        [f"{b}.{c}" for b, c in LINES],
        [77e3, 163e3, 311e3, 341e3, 138e3, 107e3, 79e3, 178e3, 39e3, 173e3, 242e3, 153e3],
        strict=True,
    )
)


def _rm(draws: int = 1, capacity: dict | None = None, seed: int = 0) -> ResponseModel:
    rng = np.random.default_rng(seed)
    last = np.array(list(LAST.values())) / 52
    vmax = np.tile(np.array([20, 60, 300, 400, 10, 4, 6, 6, 15, 30, 300, 350], float), (draws, 1))
    vmax *= np.exp(rng.normal(0, 0.1, vmax.shape)) if draws > 1 else 1
    value = np.array([87.0] * 4 + [5000.0] * 4 + [59.0] * 4)
    organic = {"B1": np.full(draws, 140.0), "B2": np.full(draws, 3.0), "B3": np.full(draws, 220.0)}
    return ResponseModel(LINES, vmax, np.tile(1.5 * last, (draws, 1)), np.ones(12), organic, value, capacity or {})


def _setting(**kw) -> Setting:
    return Setting(LAST, {"B1": 1e6, "B2": 1e7, "B3": 1e6}, {"B3.display_retargeting"}, **kw)


def test_profit_gradient_matches_finite_differences_including_at_capacity():
    for cap in ({}, {"B2": 4.0}):
        rm = _rm(capacity=cap)
        x = np.array(list(LAST.values())) / 52
        g = rm.profit_gradient(x)[0]
        h = 1e-3
        fd = [(rm.annual_profit(x + h * e)[0] - rm.annual_profit(x - h * e)[0]) / (2 * h) for e in np.eye(12)]
        np.testing.assert_allclose(g, fd, rtol=1e-4, atol=1e-3)


def test_capacity_caps_paid_customers_at_the_room_left():
    rm = _rm(capacity={"B2": 4.0})
    x = np.array(list(LAST.values())) / 52 * 3
    paid = rm.effective_customers(x)[0, rm.idx("B2")].sum()
    assert paid == pytest.approx(4.0 - 3.0)


def test_optimiser_spends_the_budget_within_every_limit(cfg):
    rm, s = _rm(), _setting(drop={"downside", "min_acquisition", "payback"})
    sol = optimise(rm, cfg, s)
    assert sol.success
    assert 52 * sol.x.sum() == pytest.approx(cfg.raw["budget"]["annual_total"], rel=1e-6)
    lo, hi = line_limits(rm, cfg, s, 2e6)
    assert np.all(52 * sol.x >= lo - 1) and np.all(52 * sol.x <= hi + 1)
    last = np.array(list(LAST.values()))
    untested = np.array([f"{b}.{c}" != "B3.display_retargeting" for b, c in LINES])
    assert np.all(np.abs(52 * sol.x[untested] / last[untested] - 1) <= 0.25 + 1e-6)  # guardrail


def test_free_lines_within_a_business_end_with_equal_marginal_returns(cfg):
    """Optimality: lines not held at a limit earn the same from their next dollar. Business floors and ceilings
    bind here, so returns equalise within each business, not across them."""
    rm = _rm()
    s = _setting(drop={"downside", "min_acquisition", "payback", "untested_guardrail"})
    sol = optimise(rm, cfg, s)
    lo, hi = line_limits(rm, cfg, s, 2e6)
    free = (52 * sol.x > lo + 100) & (52 * sol.x < hi - 100)
    g = rm.profit_gradient(sol.x)[0]
    checked = 0
    for b in rm.businesses:
        i = rm.idx(b)
        gb = g[i][free[i]]
        if len(gb) >= 2:
            assert np.ptp(gb) < 0.05 * 52  # within 5 cents per dollar
            checked += 1
    assert checked >= 1


def test_optimised_plan_is_at_least_as_good_as_status_quo(cfg):
    rm = _rm(draws=50, seed=3)
    s = _setting()
    sol = optimise(rm, cfg, s)
    assert sol.success
    e, e0 = evaluate(rm, sol.x, cfg), evaluate(rm, status_quo(rm, s, 2e6), cfg)
    assert e["expected_profit"] >= e0["expected_profit"] - 1
    assert e["downside_profit"] >= e0["downside_profit"] - 1  # the downside constraint holds


def _simulated_business(cfg: Config, beta, k_mult, decay, seed: int = 0) -> tuple[BusinessData, MMM]:
    rng = np.random.default_rng(seed)
    n, channels = 156, ["a", "b"]
    spend = np.column_stack([3000 * np.exp(rng.normal(0, 0.3, n)), 5000 * np.exp(rng.normal(0, 0.3, n))])
    d = BusinessData(
        "B9",
        channels,
        pd.Series(pd.date_range("2023-10-30", periods=n, freq="7D")),
        np.zeros(n),
        spend,
        spend.mean(axis=0),
        [],
        50.0,
    )
    m = MMM(d, cfg)
    th = np.r_[np.log(200), 0.05, 0.1, 0, 0, 0.05, 0, 0, np.log(beta), np.log(k_mult), decay]
    d.y = rng.poisson(m.mean(m.unpack(th))).astype(float)
    return d, m


def test_mmm_recovers_its_own_curves(cfg):
    d, _ = _simulated_business(cfg, beta=[0.5, 0.8], k_mult=[1.0, 1.0], decay=[0.2, 0.3])
    fb = fit_business(d, cfg, calibrate=False, n_draws=0, seed=0)
    p = fb.model.unpack(fb.point)
    x = d.mean_spend
    est = p.beta * p.half_sat / (x + p.half_sat) ** 2
    true = np.array([0.5, 0.8]) * x / (x + x) ** 2
    np.testing.assert_allclose(est, true, rtol=0.35)


def test_calibration_pulls_the_fit_towards_the_experiment(cfg):
    d, _ = _simulated_business(cfg, beta=[0.5, 0.8], k_mult=[1.0, 1.0], decay=[0.2, 0.3], seed=1)
    d.calibration = [
        {
            "experiment": "x",
            "business": "B9",
            "channel": "a",
            "spend_multiplier": 0.0,
            "test_start": str(d.weeks.iloc[140].date()),
            "test_weeks": 12,
            "relative_effect": -0.02,
            "se": 0.005,
        }
    ]
    raw = fit_business(d, cfg, calibrate=False, n_draws=0, seed=0)
    cal = fit_business(d, cfg, calibrate=True, n_draws=0, seed=0)
    c = d.calibration[0]
    e_raw = raw.model.predicted_test_effect(raw.model.unpack(raw.point), c)
    e_cal = cal.model.predicted_test_effect(cal.model.unpack(cal.point), c)
    assert abs(e_cal - (-0.02)) < abs(e_raw - (-0.02))
