"""The CSV columns are the contract between the pipeline and the Tableau workbook. These tests run on the
committed extracts in dashboard/data (rebuilt by `mbo dashboard`)."""

from pathlib import Path

import pandas as pd
import pytest

from marketing_budget.dashboard.tieout import tieout

DATA = Path(__file__).resolve().parents[1] / "dashboard" / "data"

CONTRACT = {
    "synthetic_weekly_business": (["week_start", "business"], ["spend", "customers", "contribution_profit", "revenue"]),
    "synthetic_weekly_channel": (
        ["week_start", "line"],
        ["spend", "crm_customers", "platform_conversions", "any_dq_flag", "tested_by_experiment"],
    ),
    "synthetic_allocation": (["line"], ["last_year_split", "recommended", "change", "verdict", "evidence"]),
    "synthetic_channel_lenses": (["line", "lens"], ["customers_per_1000", "low", "high", "evidence"]),
    "synthetic_forecast": (["week_start", "business", "target", "series"], ["value", "low", "high"]),
    "synthetic_forecast_scenarios": (["business", "target", "period", "scenario"], ["value"]),
    "synthetic_plan_summary": (["allocation"], ["expected_profit", "downside_profit"]),
    "synthetic_policy_costs": (["policy_removed"], ["policy", "expected_profit_gain"]),
    "synthetic_budget_curve": (["budget"], ["expected_profit", "downside_profit", "p90_profit"]),
    "synthetic_experiments": (["experiment", "metric"], ["relative_effect", "ci_low", "ci_high", "decision"]),
    "synthetic_next_tests": (["line"], ["stake"]),
    "synthetic_dq_issues": (["issue", "business", "channel"], ["detail"]),
    "synthetic_attribution_ratio_weekly": (["week_start", "line"], ["platform_conversions", "crm_customers"]),
}

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="dashboard extracts not built")


def _load() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_csv(p) for p in DATA.glob("*.csv")}


@pytest.mark.parametrize("name", list(CONTRACT))
def test_extract_keeps_its_columns_and_unique_keys(name):
    df = pd.read_csv(DATA / f"{name}.csv")
    keys, fields = CONTRACT[name]
    assert set(keys + fields) <= set(df.columns), set(keys + fields) - set(df.columns)
    assert not df[keys].isna().any().any()
    assert not df.duplicated(keys).any()


def test_every_extract_is_named_synthetic_and_carries_no_truth():
    x = _load()
    assert set(x) == set(CONTRACT)
    for name, df in x.items():
        assert name.startswith("synthetic_")
        assert not any(c.startswith("true_") or "truth" in c for c in df.columns), name


def test_weekly_extracts_store_no_ratios():
    """Ratios must be SUM()/SUM() in Tableau; a stored ratio would be averaged wrongly."""
    for name in ("synthetic_weekly_business", "synthetic_weekly_channel"):
        cols = pd.read_csv(DATA / f"{name}.csv").columns
        assert not any("cac" in c or c.endswith("_rate") or c == "cpc" for c in cols), name


def test_tieout_matches_the_committed_file():
    committed = pd.read_csv(DATA.parent / "tieout.csv")
    fresh = tieout(_load())
    assert committed["expected_value"].to_numpy() == pytest.approx(fresh["expected_value"].to_numpy(), rel=1e-5)


def test_allocation_spends_the_budget_and_lenses_ranges_are_ordered():
    al = pd.read_csv(DATA / "synthetic_allocation.csv")
    assert al["recommended"].sum() == pytest.approx(2_000_000, rel=1e-4)
    ln = pd.read_csv(DATA / "synthetic_channel_lenses.csv").dropna(subset=["low", "high"])
    assert (ln["low"] <= ln["high"]).all()
