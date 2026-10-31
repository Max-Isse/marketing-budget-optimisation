import copy

import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.proportion import proportions_ztest

from marketing_budget.experiments.analyze import decide, geo_test, holm, rate_ratio, ratio_delta, two_proportions
from marketing_budget.experiments.design import (
    assign_regions,
    choose_geo_design,
    mde_two_proportions,
    n_two_proportions,
    peeking_false_positive_rate,
    poisson_events_needed,
)
from marketing_budget.synthetic import experiments as sx
from marketing_budget.synthetic.generate import generate
from marketing_budget.synthetic.truth import load_ground_truth

ZA, ZB = 1.959964, 0.841621


def test_sample_size_matches_the_textbook_value():
    # p = 10% -> 11%: (1.96 + 0.84)^2 (0.09 + 0.0979) / 0.01^2 = 14,749 per arm
    assert n_two_proportions(0.10, 0.10, ZA, ZB) == pytest.approx(14_749, abs=2)


def test_mde_inverts_the_sample_size():
    n = n_two_proportions(0.024, 0.06, ZA, ZB)
    assert mde_two_proportions(0.024, n, ZA, ZB) == pytest.approx(0.06, abs=1e-3)


def test_smaller_poisson_effects_need_more_events():
    assert poisson_events_needed(0.9, ZA, ZB) > poisson_events_needed(0.7, ZA, ZB)


def test_peeking_inflates_false_positives():
    r = peeking_false_positive_rate(500, 0.05, 30, 0.05, 1000, 1)
    assert r["false_positive_rate_final_look_only"] == pytest.approx(0.05, abs=0.025)
    assert r["false_positive_rate_any_daily_look"] > 2 * r["false_positive_rate_final_look_only"]


def test_two_proportions_agrees_with_statsmodels():
    r = two_proportions(240, 10_000, 275, 10_000)
    _, p = proportions_ztest([275, 240], [10_000, 10_000])
    assert r["p_value"] == pytest.approx(p, rel=1e-6)
    assert r["relative_effect"] == pytest.approx(275 / 240 - 1)
    assert r["ci_low"] < r["relative_effect"] < r["ci_high"]


def test_ratio_delta_is_binomial_variance_with_one_impression_per_user():
    rng = np.random.default_rng(0)
    clicks = rng.binomial(1, 0.02, 50_000).astype(float)
    r, var = ratio_delta(clicks, np.ones_like(clicks))
    assert var == pytest.approx(r * (1 - r) / len(clicks), rel=1e-3)


def test_rate_ratio_and_holm():
    r = rate_ratio(100, 1000.0, 150, 1000.0)
    assert r["relative_effect"] == pytest.approx(0.5)
    assert r["p_value"] < 0.01
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (0.03, 0.08, "adopt"),
        (-0.08, -0.02, "reject"),
        (0.005, 0.08, "real but"),
        (-0.01, 0.01, "no worthwhile"),
        (-0.03, 0.09, "inconclusive"),
    ],
)
def test_decision_rule(lo, hi, expected):
    assert decide(lo, hi, threshold=0.02).startswith(expected)


def test_region_assignment_is_balanced_within_blocks():
    pre = pd.DataFrame({"region": np.repeat(np.arange(40), 2), "customers": np.repeat(np.arange(40) * 10, 2)})
    a = assign_regions(pre, 0.25, seed=1)
    assert a["treated"].sum() == 10
    order = pre.groupby("region")["customers"].sum().sort_values().index
    blocks = pd.Series({r: j // 4 for j, r in enumerate(order)})
    assert a.set_index("region")["treated"].groupby(blocks).sum().eq(1).all()  # one treated region per block


def test_design_choice_prefers_the_cheapest_powered_option():
    c = [
        {"treated_share": 0.5, "test_weeks": 16, "mde": 0.05},
        {"treated_share": 0.25, "test_weeks": 8, "mde": 0.09},
        {"treated_share": 0.25, "test_weeks": 16, "mde": 0.07},
    ]
    assert choose_geo_design(c, 0.08)["test_weeks"] == 16 and choose_geo_design(c, 0.08)["treated_share"] == 0.25
    weak = choose_geo_design(c, 0.01)
    assert weak["powered"] is False and weak["mde"] == 0.05


def _toy_panel(rng: np.random.Generator, effect: float) -> pd.DataFrame:
    regions = np.arange(40)
    size = rng.uniform(50, 150, 40)
    treated = np.isin(regions, regions[::2])
    rows = []
    for period in ("pre", "test"):
        y = rng.poisson(size) + np.where(treated & (period == "test"), effect, 0.0)
        rows.append(
            pd.DataFrame(
                {
                    "region": regions,
                    "period": period,
                    "treated": treated,
                    "customers": y,
                    "line_spend": rng.uniform(900, 1100, 40),
                    "line_last_click_customers": rng.poisson(20, 40),
                    "line_platform_conversions": rng.poisson(30, 40),
                }
            )
        )
    return pd.concat(rows)


def test_geo_ancova_is_unbiased_with_honest_intervals():
    """Across many simulated tests with a known effect (-20 per treated region, 20 treated regions), the
    estimate averages out to the truth and the 95% interval covers it about 95% of the time."""
    rng = np.random.default_rng(3)
    blocks = pd.Series(np.arange(40) // 2, index=np.arange(40))
    est, cover = [], []
    for _ in range(200):
        s = geo_test(_toy_panel(rng, -20.0), blocks, 1, 0).summary
        est.append(s["incremental_customers"])
        cover.append(s["incremental_ci_low"] <= -400 <= s["incremental_ci_high"])
    assert np.mean(est) == pytest.approx(-400, abs=3 * np.std(est) / np.sqrt(200))
    assert 0.90 <= np.mean(cover) <= 0.99


def test_randomisation_inference_detects_a_large_effect():
    s = geo_test(_toy_panel(np.random.default_rng(4), -40.0), pd.Series(np.arange(40) // 2), 500, 0).summary
    assert s["p_value_randomisation"] < 0.01


@pytest.fixture(scope="module")
def small_world(cfg):
    t = copy.deepcopy(load_ground_truth())
    t["calendar"]["n_weeks"] = 60
    t["calendar"]["legacy_weeks"] = 0
    t["historical_spend_policy"]["budget_shifts"] = []
    t["data_issues"] = {
        "tracking_outages": [],
        "attribution_signal_loss": [],
        "duplicate_lead_rate": {"B2": 0.03},
        "late_cost_corrections": [],
    }
    return t, generate(t, cfg).truth["synthetic_truth_weekly"]


def test_pre_period_does_not_depend_on_the_assignment(small_world):
    truth, tw = small_world
    spec = {"business": "B3", "channel": "display_retargeting", "treatment": "spend", "spend_multiplier": 0.0}
    shares = sx.regions(truth, 5)
    pre, _ = sx.simulate_geo(truth, tw, "t", spec, shares, None, 11)
    a = assign_regions(pre, 0.5, 2)
    full, true = sx.simulate_geo(truth, tw, "t", spec, shares, a, 11, 12)
    after = full[full["period"] == "pre"].drop(columns="treated").reset_index(drop=True)
    pd.testing.assert_frame_equal(pre.drop(columns="treated"), after)
    assert true["true_incremental_customers"] < 0  # switching retargeting off loses some customers
    assert full.loc[(full["period"] == "test") & full["treated"], "line_spend"].eq(0).all()


def test_landing_page_simulation_keeps_the_baseline(small_world):
    truth, _ = small_world
    lp = sx.simulate_landing_page(truth, 4, 1)
    base = lp.loc[lp["arm"] == "current_page", "converted"].mean()
    assert base == pytest.approx(truth["experiments"]["landing_page"]["baseline_conversion"], rel=0.1)
