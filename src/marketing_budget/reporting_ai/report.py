"""Write the management draft (reports/ai_commentary_draft.md), its audit record, and the phase 7 report
(reports/ai_reporting.md) with a red-team demonstration of the checks."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from marketing_budget.config import Config
from marketing_budget.reporting_ai.draft import DraftResult
from marketing_budget.reporting_ai.facts import Fact, fact_table
from marketing_budget.reporting_ai.review import BODY_MARKER, body_hash, current_status, draft_path
from marketing_budget.reporting_ai.validate import validate_draft


def _cite(ids: list[str]) -> str:
    return " " + " ".join(f"[{i}]" for i in ids)


def render_body(res: DraftResult, facts: list[Fact], periods: dict[str, str]) -> str:
    d = res.draft
    used = sorted(
        {i for p in d["paragraphs"] for s in p["sentences"] for i in s["fact_ids"]}
        | {i for q in d["questions"] for i in q["fact_ids"]}
        | set(d["headline"]["fact_ids"])
    )
    by_id = {f.fact_id: f for f in facts}
    paras = "\n\n".join(
        f"**{p['topic']}.** " + " ".join(s["text"] + _cite(s["fact_ids"]) for s in p["sentences"])
        for p in d["paragraphs"]
    )
    qs = "\n".join(
        f"{n}. {q['question']}{_cite(q['fact_ids'])}" + (f" *{q['why_it_matters']}*" if q.get("why_it_matters") else "")
        for n, q in enumerate(d["questions"], 1)
    )
    appendix = fact_table([by_id[i] for i in used if i in by_id])
    for c in ("change_vs_previous", "change_vs_last_year"):
        if c in appendix:
            appendix[c] = appendix[c].map(lambda v: "" if pd.isna(v) else f"{100 * v:+.1f}%")
    return f"""
## {d["headline"]["text"]}{_cite(d["headline"]["fact_ids"])}

{paras}

### Questions for the analysts

{qs}

### Fact appendix (every number above traces to one of these rows)

Evidence: *actual* = recorded; *attribution* = what the CRM or an ad platform credits (not proof of cause);
*causal* = randomised test; *model* = estimate from the calibrated model.

{appendix.to_markdown(index=False, floatfmt=",.4g")}
"""


def write_draft(res: DraftResult, facts: list[Fact], periods: dict[str, str], cfg: Config) -> Path:
    body = render_body(res, facts, periods)
    sha = body_hash(BODY_MARKER + body)
    status = current_status(cfg, sha)
    src = "Claude (structured output), checked" if res.source == "llm" else "deterministic template (no LLM)"
    head = f"""# Marketing performance commentary: DRAFT

> **Review status: {status}.**
> Generated from validated SQL outputs by: {src}. Checks passed: {"yes" if not res.findings else "NO"}.
> SYNTHETIC data. Bracketed IDs cite the fact appendix. A reviewer signs off with
> `uv run mbo review --reviewer "Name" --decision approved`.

**Reviewer checklist**
- [ ] Every number matches the fact appendix (the checker verifies this; spot-check two).
- [ ] No sentence claims a cause unless it cites a *causal* fact.
- [ ] Data-quality notes are mentioned where they apply.
- [ ] The questions are worth an analyst's time.
- [ ] Nothing here should not go to the CEO, CFO and Marketing Director.
"""
    path = draft_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(head + BODY_MARKER + body, encoding="utf-8")
    audit = {
        "draft_sha256": sha,
        "source": res.source,
        "attempts": res.attempts,
        "findings_on_final_draft": [f.__dict__ for f in res.findings],
        "fact_sheet_sha256": res.fact_sheet_sha256,
        "facts_cited": sorted(
            {i for p in res.draft["paragraphs"] for s in p["sentences"] for i in s["fact_ids"]}
            | {i for q in res.draft["questions"] for i in q["fact_ids"]}
        ),
        "period": periods["current"],
        "draft": res.draft,
    }
    (cfg.path("artifacts_dir")).mkdir(parents=True, exist_ok=True)
    (cfg.path("artifacts_dir") / "ai_commentary_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return path


def red_team(facts: list[Fact]) -> pd.DataFrame:
    """Deliberately bad sentences, each built from a real fact, and what the checker says about them."""
    by_id = {f.fact_id: f for f in facts}
    cust = by_id.get("B1.customers") or facts[0]
    attr = next((f for f in facts if f.evidence == "attribution"), facts[0])
    exp = next((f for f in facts if f.evidence == "causal"), facts[0])
    cases = [
        ("invented number", f"{cust.scope} won 9,999 new customers.", [cust.fact_id]),
        ("invented metric", f"{cust.scope} ROAS improved to 4.2x.", [cust.fact_id]),
        ("causal claim from attribution", f"{attr.scope} drove the change in customers.", [attr.fact_id]),
        ("no citation", "Performance was strong across the board.", []),
        ("unknown fact ID", f"{cust.scope} grew.", ["B9.customers"]),
        (
            "causal claim from a randomised test (allowed)",
            "The new landing page caused the conversion change.",
            [exp.fact_id],
        ),
    ]
    rows = []
    for name, text, ids in cases:
        draft = {"headline": {"text": text, "fact_ids": ids}, "paragraphs": [], "questions": []}
        found = validate_draft(draft, by_id)
        rows.append(
            {
                "case": name,
                "sentence": text,
                "cited": ", ".join(ids) or "(none)",
                "checker": "; ".join(f"{f.check}: {f.detail}" for f in found) or "passes",
            }
        )
    return pd.DataFrame(rows)


def write_phase_report(res: DraftResult, facts: list[Fact], periods: dict[str, str], cfg: Config) -> Path:
    tables = cfg.path("tables_dir")
    fact_table(facts).to_csv(tables / "ai_fact_sheet.csv", index=False, float_format="%.6g")
    rt = red_team(facts)
    rt.to_csv(tables / "ai_red_team.csv", index=False)
    n_unusual = sum(f.unusual for f in facts)
    att = (
        pd.DataFrame(res.attempts)
        if res.attempts
        else pd.DataFrame([{"attempt": "none", "outcome": "LLM not enabled"}])
    )
    text = f"""# AI-assisted reporting workflow (SYNTHETIC data)

## Summary for management

1. **Business question.** Can a language model take the first pass at the monthly performance commentary
   without inventing numbers or claiming causes the evidence does not support?
2. **Why it matters.** Analysts spend hours each month turning dashboards into words, and a fluent but wrong
   sentence in a board pack is worse than none. Speed only helps if every claim can be traced and trusted.
3. **What this establishes.** The workflow builds a fact sheet of {len(facts)} numbered facts from the
   validated SQL layer; {n_unusual} {"is" if n_unusual == 1 else "are"} flagged as unusual by a statistical test, not by the model.
   The model drafts from those facts only, and code checks every sentence before anyone reads it:
   - every number matches a cited fact;
   - no metric the facts do not contain;
   - no causal wording without a randomised test behind it;
   - every sentence cites its sources.

   A failed draft gets one retry with its errors listed. After that a plain template is used, so the process
   never stalls. This run used: **{res.source}**.
4. **In business terms.** The model writes the prose; the numbers, the "unusual" flags and the rules stay with
   code; a named person signs off. The red-team test below shows the checker catching each kind of error.
5. **Action to consider.** Use the draft as a first pass for the monthly pack, with sign-off as a required
   step. Review the analyst questions at the monthly meeting.
6. **Assumptions and limits.**
   - The checker verifies numbers and wording, not judgement: a draft can be accurate and still emphasise the
     wrong things. That is what the reviewer is for.
   - "Unusual" means far from this series' own history, which is not the same as important.
   - Calling the API sends the fact sheet (synthetic here) to Anthropic.

## How it works

| Step | Done by | Output |
|---|---|---|
| 1. 4-week totals per business and channel | SQL (`sql/08_kpi_windows.sql`) | `kpi_windows` |
| 2. Fact sheet: values, changes, evidence type, data-quality notes; experiment and plan findings | Python | `reports/tables/ai_fact_sheet.csv` |
| 3. Unusual movements: 4-week change vs that series' own history, robust z ≥ {cfg.section("ai_reporting")["unusual_z"]} | Python | `unusual`, `robust_z` |
| 4. Draft: headline, paragraphs, questions; every sentence lists its fact IDs | Claude ({cfg.section("ai_reporting")["model"]}, structured JSON output) or template | draft JSON |
| 5. Checks: citations, numbers, causal wording, metric vocabulary | Python (`reporting_ai/validate.py`) | findings; retry once, then template |
| 6. Human sign-off, tied to the exact draft text | Named reviewer (`mbo review`) | `reports/ai_commentary_reviews.json` |
| 7. Audit: fact-sheet hash, attempts, findings, the draft | Python | `artifacts/ai_commentary_audit.json` |

The model never sees raw tables, never computes a number, and its output is data until it passes the checks.

## This run

Period: {periods["current"]}. Draft source: {res.source}. Findings on the final draft: {len(res.findings)}.
Draft: `reports/ai_commentary_draft.md`.

{att.to_markdown(index=False)}

## Red team: does the checker catch what it should?

{rt.to_markdown(index=False)}

## Unusual movements this period

{fact_table([f for f in facts if f.unusual])[["fact_id", "metric_label", "change_vs_previous", "robust_z", "dq_note"]].to_markdown(index=False, floatfmt=",.3g") if n_unusual else "None."}
"""
    path = cfg.path("reports_dir") / "ai_reporting.md"
    path.write_text(text, encoding="utf-8")
    return path
