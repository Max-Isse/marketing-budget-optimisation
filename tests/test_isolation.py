"""Only the generator, the validation package and the CLI orchestration may touch the sealed ground truth."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "marketing_budget"
ALLOWED = {"synthetic", "validation"}
MARKERS = ("ground_truth_SYNTHETIC", "synthetic.truth", "load_ground_truth", "GROUND_TRUTH")


def test_models_cannot_read_ground_truth():
    offenders = []
    for f in ROOT.rglob("*.py"):
        rel = f.relative_to(ROOT)
        if rel.parts[0] in ALLOWED or rel == Path("cli.py"):
            continue
        text = f.read_text(encoding="utf-8")
        offenders += [f"{rel}: {m}" for m in MARKERS if m in text]
    assert not offenders, offenders
