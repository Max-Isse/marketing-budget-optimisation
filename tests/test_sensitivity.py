import pandas as pd
import pytest

from marketing_budget.analysis.retention import ALL
from marketing_budget.optimisation.inputs import values_and_caps
from marketing_budget.sensitivity.scenarios import SCENARIOS, Scenario, no_regret, scenario_config


def test_scenario_config_sets_nested_and_line_keys_without_touching_the_base(cfg):
    sc = Scenario(
        "x",
        "policy",
        "",
        {
            "valuation.payback_target_months.B3": 6,
            "budget.channel_limits.overrides.B1.search_brand": {},
            "budget.sales_capacity.B2.max_qualified_leads_per_week": 50,
        },
    )
    c = scenario_config(cfg, sc)
    assert c.raw["valuation"]["payback_target_months"]["B3"] == 6
    assert c.raw["budget"]["channel_limits"]["overrides"]["B1.search_brand"] == {}
    assert c.raw["budget"]["sales_capacity"]["B2"]["max_qualified_leads_per_week"] == 50
    assert cfg.raw["valuation"]["payback_target_months"]["B3"] == 9  # base untouched
    assert cfg.raw["budget"]["channel_limits"]["overrides"]["B1.search_brand"] == {"min_multiple": 0.5}


def test_every_scenario_produces_a_valid_config(cfg):
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names)) and names[0] == "base"
    for s in SCENARIOS:
        scenario_config(cfg, s)


def _estimates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"business": "B1", "source": ALL, "survival_first_month": 0.55, "survival_monthly": 0.88},
            {"business": "B2", "source": ALL, "survival_first_month": 0.9865, "survival_monthly": 0.9865},
            {"business": "B3", "source": ALL, "repeat_rate_first_month": 0.05, "repeat_decay_monthly": 0.95},
        ]
    )


def test_payback_limit_does_not_depend_on_the_valuation_horizon(cfg):
    """Regression: a 12-month value horizon with an 18-month payback target used to index past the stream."""
    short = scenario_config(cfg, Scenario("h", "valuation", "", {"valuation.horizon_months": 12}))
    v24, caps24 = values_and_caps(_estimates(), cfg)
    v12, caps12 = values_and_caps(_estimates(), short)
    assert caps12 == pytest.approx(caps24)
    assert all(v12[b] < v24[b] for b in v24)


def test_no_regret_verdicts():
    ch = pd.DataFrame(
        {
            "line": ["a", "b", "c", "d"],
            "base": [0.2, -0.3, 0.1, 0.2],
            "s1": [0.3, -0.2, -0.2, 0.1],
            "s2": [0.1, -0.5, 0.2, 0.2],
            "s3": [0.2, -0.1, 0.0, 0.3],
            "s4": [0.4, -0.4, 0.3, -0.1],
        }
    )
    solved = {c: True for c in ch.columns if c != "line"}
    v = no_regret(ch, solved, 0.05, {"a"}).set_index("line")["verdict"]
    assert v["a"] == "no-regret increase"
    assert v["b"] == "no-regret cut"
    assert v["c"] == "depends on assumptions"
    assert v["d"] == "mostly increase"


def test_unsolved_scenarios_are_ignored_in_verdicts():
    ch = pd.DataFrame({"line": ["a"], "base": [0.2], "s1": [-0.5]})
    v = no_regret(ch, {"base": True, "s1": False}, 0.05)
    assert v["verdict"].iloc[0] == "no-regret increase"


def test_verdicts_say_which_lines_have_an_experiment():
    ch = pd.DataFrame({"line": ["B3.display_retargeting", "B1.search_generic"], "base": [-0.7, 0.2]})
    v = no_regret(ch, {"base": True}, 0.05, {"B3.display_retargeting"}).set_index("line")["evidence"]
    assert v["B3.display_retargeting"] == "experiment"
    assert v["B1.search_generic"] == "history only"
