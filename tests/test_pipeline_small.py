"""End-to-end on a smaller simulated world (80 weeks): generate -> build -> data-quality checks -> scoring."""

import copy

import pandas as pd
import pytest

from marketing_budget.analysis.retention import ALL, estimate_retention
from marketing_budget.config import with_overrides
from marketing_budget.data.build import build_database
from marketing_budget.data.quality import build_quality_report
from marketing_budget.synthetic.generate import generate, write_generated
from marketing_budget.synthetic.truth import load_ground_truth
from marketing_budget.validation.phase1 import score_quality

TRUTH_COLUMNS = {"true_source", "incremental_leads", "expected_incremental_leads", "adstock", "demand_index"}


@pytest.fixture(scope="module")
def small_truth():
    t = copy.deepcopy(load_ground_truth())
    t["calendar"]["n_weeks"] = 80
    t["historical_spend_policy"]["budget_shifts"] = [
        {"business": "B3", "channel": "shopping", "from_week": 10, "to_week": 25, "multiplier": 1.4}
    ]
    t["data_issues"] = {
        "tracking_outages": [{"business": "B3", "channel": "display_retargeting", "from_week": 20, "to_week": 21}],
        "attribution_signal_loss": [
            {"business": "B1", "channel": "social_prospecting", "from_week": 45, "retained_share": 0.7}
        ],
        "duplicate_lead_rate": {"B2": 0.03},
        "late_cost_corrections": [
            {"business": "B2", "channel": "programmatic_display", "week": 30, "multiplier": 1.25}
        ],
    }
    return t


@pytest.fixture(scope="module")
def built(small_truth, cfg, tmp_path_factory):
    c = with_overrides(cfg, tmp_path_factory.mktemp("small"))
    gen = generate(small_truth, c)
    write_generated(gen, c)
    con = build_database(c)
    yield gen, con, c
    con.close()


def test_observable_tables_carry_no_truth(built):
    gen, _, _ = built
    for name, df in gen.observable.items():
        assert not TRUTH_COLUMNS & set(df.columns), name
        assert name.startswith("synthetic_")


def test_generation_is_deterministic(small_truth, cfg, tmp_path):
    c = with_overrides(cfg, tmp_path)
    a = generate(small_truth, c).observable["synthetic_weekly_media"]
    b = generate(small_truth, c).observable["synthetic_weekly_media"]
    pd.testing.assert_frame_equal(a, b)


def test_structural_checks_pass(built):
    _, con, c = built
    q = build_quality_report(con, c)
    assert q.checks["passed"].all(), q.checks[~q.checks["passed"]]


def test_every_injected_issue_found_and_no_false_flags(built, small_truth):
    _, con, c = built
    score, false_flags = score_quality(build_quality_report(con, c).issues, small_truth)
    assert score["detected"].all(), score
    assert len(false_flags) == 0, false_flags
    assert (score["start_error_weeks"].abs() <= 1).all()


def test_retention_close_to_truth(built, small_truth):
    _, con, c = built
    est = estimate_retention(con, c).estimates.set_index(["business", "source"])
    e = small_truth["businesses"]["B1"]["economics"]
    assert est.loc[("B1", ALL), "survival_first_month"] == pytest.approx(e["survival_first_month"], abs=0.02)
    assert est.loc[("B1", ALL), "survival_monthly"] == pytest.approx(e["survival_monthly"], abs=0.02)
