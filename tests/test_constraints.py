from marketing_budget.config import Config
from marketing_budget.constraints import line_bounds


def _cfg(cfg: Config, **budget) -> Config:
    return Config({**cfg.raw, "budget": {**cfg.raw["budget"], **budget}}, cfg.root)


SPEND = {"B1.a": 500_000.0, "B1.b": 400_000.0, "B2.a": 500_000.0, "B3.a": 600_000.0}


def test_reasonable_policy_is_feasible(cfg):
    b = line_bounds(cfg, SPEND)
    assert b.feasible, b.problems
    assert (b.lines["min"] <= b.lines["max"]).all()


def test_line_cap_limits_the_maximum(cfg):
    b = line_bounds(cfg, SPEND)
    cap = cfg.raw["budget"]["concentration"]["max_line_share"] * cfg.raw["budget"]["annual_total"]
    assert b.lines["max"].max() <= cap


def test_business_minimums_above_budget_are_flagged(cfg):
    limits = {k: {"min": 900_000, "max": 1_000_000} for k in ("B1", "B2", "B3")}
    b = line_bounds(_cfg(cfg, business_limits=limits), SPEND)
    assert any("above the budget" in p for p in b.problems)


def test_channel_floor_above_business_ceiling_is_flagged(cfg):
    limits = {**cfg.raw["budget"]["business_limits"], "B2": {"min": 100_000, "max": 100_000}}
    b = line_bounds(_cfg(cfg, business_limits=limits), SPEND)
    assert any(p.startswith("B2:") for p in b.problems)
