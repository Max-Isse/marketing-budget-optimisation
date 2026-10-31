"""Human sign-off. A review record is tied to the exact draft text it approved (SHA-256): if the draft is
regenerated, an earlier approval no longer applies and the draft shows as unreviewed again."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from marketing_budget.config import Config

DECISIONS = ("approved", "approved with edits", "rejected")
BODY_MARKER = "<!-- body -->"


def draft_path(cfg: Config) -> Path:
    return cfg.path("reports_dir") / "ai_commentary_draft.md"


def review_path(cfg: Config) -> Path:
    return cfg.path("reports_dir") / "ai_commentary_reviews.json"


def body_hash(markdown: str) -> str:
    """Hash of the draft below the status banner, so recording a review does not change the hash."""
    body = markdown.split(BODY_MARKER, 1)[-1]
    return hashlib.sha256(body.encode()).hexdigest()


def load_reviews(cfg: Config) -> list[dict[str, Any]]:
    p = review_path(cfg)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def record_review(cfg: Config, reviewer: str, decision: str, notes: str = "") -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    if not reviewer.strip():
        raise ValueError("a named reviewer is required")
    md = draft_path(cfg).read_text(encoding="utf-8")
    rec = {
        "draft_sha256": body_hash(md),
        "reviewer": reviewer,
        "decision": decision,
        "notes": notes,
        "reviewed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    reviews = [*load_reviews(cfg), rec]
    review_path(cfg).write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    return rec


def current_status(cfg: Config, body_sha: str) -> str:
    matching = [r for r in load_reviews(cfg) if r["draft_sha256"] == body_sha]
    if not matching:
        return "NOT REVIEWED: do not circulate"
    r = matching[-1]
    return f"{r['decision'].upper()} by {r['reviewer']} on {r['reviewed_at']}" + (
        f" ({r['notes']})" if r["notes"] else ""
    )
