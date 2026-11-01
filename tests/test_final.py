"""Phase 9: the write-up quotes only computed numbers, keeps the truth out of the memo; the manifest catches drift."""

import inspect
import re

import pandas as pd
import pytest

from marketing_budget.config import with_overrides
from marketing_budget.data.db import connect
from marketing_budget.manifest import compare, hash_outputs, verify, write_manifest
from marketing_budget.reporting import final
from marketing_budget.reporting.stakeholders import _label

QUESTIONS = (
    "## 1. What is happening?",
    "## 2. Why?",
    "## 3. What are the financial consequences?",
    "## 4. What should management do?",
    "## 5. What evidence supports this?",
    "## 6. What could invalidate the recommendation?",
    "## 7. How will success be measured?",
)


@pytest.fixture(scope="module")
def numbers(cfg):
    needed = cfg.path("tables_dir") / "sensitivity_line_verdicts.csv"
    lenses = cfg.path("dashboard_dir") / "data" / "synthetic_channel_lenses.csv"
    if not cfg.path("duckdb").exists() or not needed.exists() or not lenses.exists():
        pytest.skip("pipeline outputs not built")
    con = connect(cfg, read_only=True)
    try:
        return final.final_numbers(con, cfg)
    finally:
        con.close()


def test_management_numbers_never_read_truth_based_tables():
    # the memo and recommendations may use actuals, tests and the model only
    for fn in (final.final_numbers, final.write_executive_memo, final.write_recommendations):
        src = inspect.getsource(fn)
        assert "_SYNTHETIC" not in src and "truth_check" not in src, fn.__name__


def test_memo_answers_the_seven_questions_with_disclaimer_first(numbers, cfg, tmp_path):
    out = with_overrides(cfg, cfg.root, reports_dir=str(tmp_path))
    text = final.write_executive_memo(numbers, out, truth=None).read_text(encoding="utf-8")
    assert "SYNTHETIC" in text[:1500]
    pos = [text.index(q) for q in QUESTIONS]
    assert pos == sorted(pos)
    assert "Annex" not in text  # no truth passed, no truth section
    assert not re.search(r"\bnan\b|\bNone\b|[{}]", text)


def test_memo_labels_every_financial_line(numbers, cfg, tmp_path):
    out = with_overrides(cfg, cfg.root, reports_dir=str(tmp_path))
    text = final.write_executive_memo(numbers, out, truth=None).read_text(encoding="utf-8")
    table = text.split("## 3.")[1].split("## 4.")[0]
    rows = [r for r in table.splitlines() if r.startswith("| ") and "Annual contribution" not in r]
    assert rows and all(r.rstrip(" |").split("|")[-1].strip() in {"Model", "Causal"} for r in rows)


def test_move_now_only_on_tested_no_regret_lines(numbers):
    rec = final.recommendations_table(numbers)
    al = numbers.v["allocation"]
    firm = al["evidence"].eq("experiment") & al["verdict"].str.startswith("no-regret")
    expected = {_label(x) for x in al.loc[firm & (al["change"].abs() > 1000), "line"]}
    assert set(rec.loc[rec["action"] == "move now", "line"]) == expected
    # every unproven increase is in reserve
    up = {_label(x) for x in al.loc[(al["change"] > 1000) & ~firm, "line"]}
    assert set(rec.loc[rec["action"] == "reserve until tested", "line"]) == up


def test_suspicious_lines_are_history_only(numbers):
    al = numbers.v["allocation"]
    tested = {_label(x) for x in al.loc[al["evidence"] == "experiment", "line"]}
    for name, model, platform in numbers.v["suspicious"]:
        assert name not in tested and model > platform


def test_monitoring_thresholds_come_from_config(numbers, cfg):
    mon = final.monitoring_table(numbers, cfg)
    dq = cfg.section("data_quality")
    text = " ".join(mon["fires when"])
    assert f"{dq['shift_min_change']:.0%}" in text and f"{dq['restatement_tolerance']:.0%}" in text
    assert mon["owner"].str.len().gt(0).all()


# ---------------------------------------------------------------------------------------------- manifest


def _tree(tmp_path, cfg):
    c = with_overrides(cfg, tmp_path, reports_dir="r", tables_dir="r/tables", dashboard_dir="d", docs_dir="docs")
    (tmp_path / "r" / "tables").mkdir(parents=True)
    (tmp_path / "d" / "data").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "r" / "a.md").write_bytes(b"line 1\nline 2\n")
    (tmp_path / "r" / "tables" / "t.csv").write_bytes(b"x\r\n1\r\n")
    (tmp_path / "d" / "data" / "e.csv").write_bytes(b"y\n2\n")
    (tmp_path / "docs" / "model_card.md").write_bytes(b"card\n")
    (tmp_path / "docs" / "decisions.md").write_bytes(b"hand-written, not tracked\n")
    return c


def test_manifest_round_trip_and_drift(tmp_path, cfg):
    c = _tree(tmp_path, cfg)
    write_manifest(c)
    assert verify(c).empty
    listed = set(pd.read_csv(tmp_path / "r" / "manifest.csv")["path"])
    assert listed == {"r/a.md", "r/tables/t.csv", "d/data/e.csv", "docs/model_card.md"}

    (tmp_path / "r" / "a.md").write_bytes(b"line 1\nedited\n")
    (tmp_path / "d" / "data" / "e.csv").unlink()
    (tmp_path / "r" / "new.md").write_bytes(b"new\n")
    diff = verify(c).set_index("path")["status"].to_dict()
    assert diff == {"r/a.md": "changed", "d/data/e.csv": "missing", "r/new.md": "not in manifest"}


def test_line_endings_do_not_change_the_hash(tmp_path, cfg):
    c = _tree(tmp_path, cfg)
    before = hash_outputs(c)
    (tmp_path / "r" / "tables" / "t.csv").write_bytes(b"x\n1\n")  # as a Linux checkout would have it
    assert compare(before, hash_outputs(c)).empty
