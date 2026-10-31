"""The simulated world must contain the features the brief tests; if a config edit removes one, fail loudly."""

import numpy as np
import pytest

from marketing_budget.constraints import line_bounds
from marketing_budget.synthetic.truth import business_summary, load_ground_truth, planned_annual_spend, world_summary


@pytest.fixture(scope="module")
def truth():
    return load_ground_truth()


@pytest.fixture(scope="module")
def lines(truth, cfg):
    return world_summary(truth, cfg)


def test_seasonality_normalised_to_mean_one(truth):
    for b in truth["businesses"].values():
        assert np.mean(b["seasonality"]) == pytest.approx(1.0)


def test_paid_media_is_profitable_overall(truth, lines, cfg):
    assert business_summary(truth, lines, cfg)["annual_net_contribution"].sum() > 0


def test_some_channels_are_dashboard_traps(lines):
    trap = lines[(lines["last_click_return"] > 1.2) & (lines["marginal_return"] < 0.6)]
    assert len(trap) >= 2


def test_platform_overstates_last_click_which_overstates_incremental(lines):
    assert (lines["platform_return"] >= lines["last_click_return"]).all()
    assert (lines["last_click_return"] > lines["incremental_return"]).all()


def test_some_channels_are_underfunded(lines):
    assert (lines["marginal_return"] > 1.2).sum() >= 2


def test_average_return_overstates_marginal_return_for_concave_lines(lines):
    concave = lines[lines["channel"] != "social_prospecting"]  # S-shaped lines can have marginal > average
    assert (concave["incremental_return"] > concave["marginal_return"]).all()


def test_an_s_shaped_line_has_marginal_above_average(lines):
    assert (lines["marginal_return"] > lines["incremental_return"]).any()


def test_cheapest_b2_leads_lose_money_at_the_margin(lines):
    b2 = lines[lines["business"] == "B2"].set_index("channel")
    assert b2["cost_per_lead"].idxmin() == b2["marginal_return"].idxmin()
    assert b2["marginal_return"].min() < 1


def test_budget_policies_feasible_at_planned_spend(truth, cfg):
    b = line_bounds(cfg, planned_annual_spend(truth))
    assert b.feasible, b.problems


def test_planned_spend_matches_the_budget(truth, cfg):
    total = sum(planned_annual_spend(truth).values())
    assert total == pytest.approx(cfg.raw["budget"]["annual_total"], rel=0.01)
