"""Checks every drafted sentence against the fact sheet. A draft is publishable only with zero findings.

1. Citations: every sentence cites at least one fact ID, and every cited ID exists.
2. Numbers: every number in a sentence must equal a quantity of one of its cited facts, to the precision written
   ("$171k" matches 171,400; "12%" matches 12.3%). Dates and the period labels of cited facts are ignored.
3. Causal language ("drove", "caused", "due to"...) is allowed only when a cited fact is causal (a randomised
   test). Questions may ask about causes: they are exempt from this check, not from the others.
4. Metric vocabulary: a sentence may not name a metric (ROAS, CAC, revenue...) that none of its cited facts is
   about. This stops the model introducing measures the fact sheet does not contain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from marketing_budget.reporting_ai.facts import Fact

CAUSAL = re.compile(
    r"\b(caus(e|ed|es|ing)|dr(ove|ive|ives|iven|iving)|due to|because of|led to|leads? to|result(ed|s)? in|"
    r"thanks to|boost(ed|s)?|impact of|effect of|as a result|attributable to|responsible for)\b",
    re.IGNORECASE,
)
DATES = re.compile(
    r"\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b|\b\d{4}-\d{2}-\d{2}\b|"
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b"
)
NUMBER = re.compile(r"(?P<cur>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)\s?(?P<suf>%|k\b|K\b|M\b|m\b|x\b|\u00d7)?")
# words that name a metric -> metrics that justify them
VOCAB: dict[str, set[str]] = {
    r"\bROAS\b|return on ad spend": set(),
    r"\bCAC\b|cost per (new )?customer|acquisition cost": {"blended_cac", "last_click_cac"},
    r"\brevenue\b": {"revenue"},
    r"contribution": {"contribution_profit", "plan_gain"},
    r"\bspend\b|\bspent\b|\bspending\b": {"spend", "blended_cac", "last_click_cac", "plan_gain", "contribution_profit"},
    r"\bqualif": {"qualified_rate", "experiment_effect"},
    r"platform": {"platform_crm_ratio", "experiment_effect"},
    r"\bconversion rate|click-through|\bCTR\b": {"experiment_effect"},
    r"\bimpressions?\b|(?<!last-)\bclicks?\b": set(),
    r"\bchurn|retention|lifetime value|\bLTV\b": set(),
}


@dataclass
class Finding:
    item: str  # e.g. "paragraph 2, sentence 1" or "question 3"
    check: str
    detail: str


def parse_numbers(text: str) -> list[tuple[float, str, float]]:
    """(value in base units, kind, half of the last written digit's unit) for each number in the text."""
    out = []
    for m in NUMBER.finditer(text):
        raw = m.group("num").replace(",", "")
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        v = float(raw)
        half = 0.5 * 10 ** (-decimals)
        suf = (m.group("suf") or "").lower()
        scale = {"k": 1e3, "m": 1e6}.get(suf, 1.0)
        if m.group("cur"):
            kind = "money"
        elif suf == "%":
            kind = "percent"
        elif suf in ("x", "\u00d7"):  # "x" or the multiplication sign
            kind = "ratio"
        else:
            kind = "money" if suf in ("k", "m") else "count"
        # an unprefixed number with k/M is still money in this report; with commas it is a count
        out.append((v * scale, kind, half * scale))
    return out


def _allowed(facts: list[Fact], kind: str) -> list[float]:
    vals: list[float] = []
    for f in facts:
        vals += f.quantities.get(kind, [])
        if kind == "count":  # counts can be quoted for count-type quantities and z-scores
            vals += f.quantities.get("ratio", [])
    return vals


def check_sentence(
    text: str, cited: list[str], facts: dict[str, Fact], item: str, question: bool = False
) -> list[Finding]:
    found: list[Finding] = []
    if not cited:
        found.append(Finding(item, "citation", "no fact cited"))
    unknown = [c for c in cited if c not in facts]
    if unknown:
        found.append(Finding(item, "citation", f"unknown fact IDs: {', '.join(unknown)}"))
    cf = [facts[c] for c in cited if c in facts]

    stripped = DATES.sub(" ", text)
    for f in cf:  # a cited fact's own period label and data-quality note are labels, not claims
        stripped = stripped.replace(f.period, " ")
        if f.dq_note:
            stripped = stripped.replace(f.dq_note, " ")
    stripped = re.sub(r"\b(B[123])\b", " ", stripped)  # business codes are labels, not numbers
    stripped = re.sub(r"\b(4|four)[- ]weeks?\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(24|12)[- ]month", " ", stripped)
    stripped = re.sub(r"\b95% (range|interval|confidence)", " ", stripped)
    for value, kind, half in parse_numbers(stripped):
        ok = any(abs(abs(value) - abs(a)) <= half + 1e-9 for a in _allowed(cf, kind))
        if not ok:
            found.append(Finding(item, "number", f"{value:g} ({kind}) is not a quantity of the cited facts"))

    if not question and CAUSAL.search(text) and not any(f.evidence == "causal" for f in cf):
        found.append(
            Finding(item, "causal language", f"'{CAUSAL.search(text).group(0)}' needs a causal (randomised-test) fact")  # type: ignore[union-attr]
        )
    metrics = {f.metric for f in cf}
    for pattern, ok_metrics in VOCAB.items():
        if re.search(pattern, text, re.IGNORECASE) and not (metrics & ok_metrics):
            found.append(Finding(item, "metric", f"names a metric ({pattern}) that no cited fact is about"))
    return found


def validate_draft(draft: dict, facts: dict[str, Fact]) -> list[Finding]:  # type: ignore[type-arg]
    found: list[Finding] = []
    found += check_sentence(draft["headline"]["text"], draft["headline"]["fact_ids"], facts, "headline")
    for i, p in enumerate(draft["paragraphs"], 1):
        for j, s in enumerate(p["sentences"], 1):
            found += check_sentence(s["text"], s["fact_ids"], facts, f"paragraph {i}, sentence {j}")
    for k, q in enumerate(draft["questions"], 1):
        found += check_sentence(q["question"], q["fact_ids"], facts, f"question {k}", question=True)
    return found
