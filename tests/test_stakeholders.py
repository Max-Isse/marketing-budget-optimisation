"""The stakeholder pack quotes only computed numbers, and its recommendations agree with phases 3-5."""

import pandas as pd
import pytest

from marketing_budget.data.db import connect
from marketing_budget.reporting.stakeholders import (
    _label,
    compute_numbers,
    metric_framework,
    objections,
    requirements_matrix,
)


@pytest.fixture(scope="module")
def numbers(cfg):
    if not cfg.path("duckdb").exists() or not (cfg.path("tables_dir") / "allocation_evaluation.csv").exists():
        pytest.skip("pipeline outputs not built")
    con = connect(cfg, read_only=True)
    try:
        return compute_numbers(con, cfg)
    finally:
        con.close()


def test_now_moves_are_only_experiment_backed_no_regret_lines(numbers):
    al = numbers.v["allocation"]
    firm = al["evidence"].eq("experiment") & al["verdict"].str.startswith("no-regret")
    named = {_label(line) for line in al["line"] if _label(line) in numbers.v["now_moves"]}
    assert named == {_label(line) for line in al.loc[firm & (al["change"].abs() > 1000), "line"]}
    assert "brand search" not in numbers.v["now_moves"]  # direction depends on assumptions (phase 5)


def test_reserve_is_every_increase_not_yet_proven(numbers):
    al = numbers.v["allocation"]
    firm = al["evidence"].eq("experiment") & al["verdict"].str.startswith("no-regret")
    assert numbers.v["reserve"] == pytest.approx(al.loc[(al["change"] > 0) & ~firm, "change"].sum())


def test_budget_figures_are_consistent_with_the_curve(numbers, cfg):
    bc = pd.read_csv(cfg.path("tables_dir") / "sensitivity_budget_curve.csv")
    bc = bc[bc["solved"].astype(bool)]
    assert numbers.v["best_budget"] == bc.loc[bc["expected_profit"].idxmax(), "budget"]
    assert numbers.v["next_200k_back"] < numbers.v["last_200k_back"]  # diminishing returns


def test_b2_example_is_the_worst_converting_channel(numbers):
    b2 = numbers.v["b2_lines"]
    assert numbers.v["b2_worst_conv"] == pytest.approx(b2["lead_to_customer"].min())
    assert numbers.v["b2_worst_cpc"] > numbers.v["b2_best_cpc"]


def test_tables_are_complete(numbers):
    assert set(requirements_matrix(numbers)["stakeholder"]) >= {"Marketing Director", "CFO", "Data Engineer"}
    assert metric_framework()["evidence type"].isin(["Actual", "Attribution", "Causal", "Model"]).all()
    ob = objections(numbers)
    assert ob["what would change our view"].str.len().gt(10).all()
    assert not ob["response"].str.contains("nan|None").any()
