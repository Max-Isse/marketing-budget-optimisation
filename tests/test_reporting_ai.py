import json
from types import SimpleNamespace

import pytest

from marketing_budget.config import Config, with_overrides
from marketing_budget.reporting_ai import draft as D
from marketing_budget.reporting_ai.facts import Fact, _quantities, _with_z
from marketing_budget.reporting_ai.review import body_hash, current_status, record_review
from marketing_budget.reporting_ai.validate import check_sentence, parse_numbers, validate_draft

PERIOD = "the 4 weeks from 28 Sep 2026 to 25 Oct 2026"
PERIODS = {"current": PERIOD, "previous": "", "last_year": ""}


def _facts() -> list[Fact]:
    return [
        Fact(
            "B1.customers",
            "B1 Hearth Box",
            "customers",
            "new customers",
            "actual",
            PERIOD,
            1894,
            1538,
            1948,
            0.2315,
            -0.0277,
            1.2,
            False,
            None,
            quantities=_with_z(_quantities("count", [1894, 1538, 1948], [0.2315, -0.0277]), 1.2),
        ),
        Fact(
            "B1.blended_cac",
            "B1 Hearth Box",
            "blended_cac",
            "blended CAC",
            "actual",
            PERIOD,
            36.29,
            43.22,
            36.12,
            -0.16,
            0.005,
            None,
            False,
            "spend restated after first report in 1 of the 4 weeks",
            quantities=_quantities("money", [36.29, 43.22, 36.12], [-0.16, 0.005]),
        ),
        Fact(
            "B3.affiliates.last_click_cac",
            "B3 affiliates",
            "last_click_cac",
            "last-click CAC",
            "attribution",
            PERIOD,
            37.27,
            21.61,
            36.41,
            0.725,
            0.024,
            3.5,
            True,
            None,
            quantities=_with_z(_quantities("money", [37.27, 21.61, 36.41], [0.725, 0.024]), 3.5),
        ),
        Fact(
            "EXP.landing_page",
            "experiment",
            "experiment_effect",
            "conversion rate",
            "causal",
            "phase 3",
            statement="x",
            quantities={"percent": [6.6, 2.9, 10.5]},
        ),
    ]


def _by_id():
    return {f.fact_id: f for f in _facts()}


def test_parse_numbers_kinds_and_precision():
    p = parse_numbers("spend $171k, CAC $38.68, up 12.3%, 1,894 customers, ratio 1.35x")
    assert (171000.0, "money", 500.0) in p
    assert (38.68, "money", 0.005) in p
    assert (12.3, "percent", 0.05) in p
    assert (1894.0, "count", 0.5) in p
    assert (1.35, "ratio", 0.005) in p


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("B1 Hearth Box won 1,894 new customers, up 23% on the previous 4 weeks.", True),
        ("B1 Hearth Box won about 1,900 new customers.", False),  # rounded beyond what was written
        ("B1 Hearth Box won 2,488 new customers.", False),
        (f"B1 Hearth Box new customers: 1,894 in {PERIOD}.", True),  # period dates are not claims
    ],
)
def test_numbers_must_match_cited_facts(text, ok):
    found = check_sentence(text, ["B1.customers"], _by_id(), "s")
    assert (not found) is ok, found


def test_rounding_to_the_written_precision_is_allowed():
    assert not check_sentence("Blended CAC fell to $36.", ["B1.blended_cac"], _by_id(), "s")
    assert check_sentence("Blended CAC fell to $35.", ["B1.blended_cac"], _by_id(), "s")


def test_causal_wording_needs_a_causal_fact_but_questions_may_ask():
    t = "B3 affiliates drove a 72.5% rise in last-click CAC."
    assert any(f.check == "causal language" for f in check_sentence(t, ["B3.affiliates.last_click_cac"], _by_id(), "s"))
    assert not check_sentence(
        "The new landing page caused a 6.6% conversion rise.", ["EXP.landing_page"], _by_id(), "s"
    )
    q = "Was the 72.5% rise in last-click CAC caused by a tracking change?"
    assert not check_sentence(q, ["B3.affiliates.last_click_cac"], _by_id(), "q", question=True)


def test_invented_metric_and_missing_citation_are_caught():
    f = check_sentence("ROAS for B1 Hearth Box rose.", ["B1.customers"], _by_id(), "s")
    assert any(x.check == "metric" for x in f)
    assert any(x.check == "citation" for x in check_sentence("Strong month.", [], _by_id(), "s"))
    assert any(x.check == "citation" for x in check_sentence("Grew.", ["B9.x"], _by_id(), "s"))


def test_template_draft_passes_its_own_checks():
    d = D.template_draft(_facts(), PERIODS)
    assert validate_draft(d, _by_id()) == []
    assert d["questions"] and d["questions"][0]["fact_ids"] == ["B3.affiliates.last_click_cac"]


def _good():
    return {
        "headline": {"text": "B1 Hearth Box new customers rose 23%.", "fact_ids": ["B1.customers"]},
        "paragraphs": [{"topic": "B1", "sentences": [{"text": "1,894 new customers.", "fact_ids": ["B1.customers"]}]}],
        "questions": [],
    }


def _bad():
    return {
        "headline": {"text": "Record month: 9,999 customers.", "fact_ids": ["B1.customers"]},
        "paragraphs": [],
        "questions": [],
    }


class FakeClient:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def draft(self, system, user, cfg):
        self.prompts.append(user)
        r = self.replies.pop(0)
        return (r, {"model": "fake"}) if r is not None else (None, {"model": "fake", "stop_reason": "refusal"})


@pytest.mark.parametrize(
    ("replies", "source", "n_attempts"),
    [([_good()], "llm", 1), ([_bad(), _good()], "llm", 2), ([_bad(), _bad()], "template", 2), ([None], "template", 1)],
)
def test_retry_then_fall_back_to_the_template(cfg, replies, source, n_attempts):
    client = FakeClient(replies)
    res = D.make_draft(_facts(), PERIODS, cfg, client=client, use_llm=True)
    assert res.source == source and len(res.attempts) == n_attempts
    assert res.findings == []  # whatever the path, the final draft passes
    if n_attempts == 2 and replies[0] is not None:
        assert "failed these checks" in client.prompts[1]


def test_claude_request_shape_and_refusal_handling(cfg, monkeypatch):
    import anthropic

    calls = []

    def response(stop):
        return SimpleNamespace(
            stop_reason=stop,
            model="claude-opus-5-5",
            _request_id="req_1",
            content=[SimpleNamespace(type="text", text=json.dumps(_good()))],
        )

    class Fake:
        def __init__(self, stop):
            self.beta = SimpleNamespace(
                messages=SimpleNamespace(create=lambda **kw: calls.append(kw) or response(stop))
            )

    monkeypatch.setattr(anthropic, "Anthropic", lambda: Fake("end_turn"))
    draft, meta = D.ClaudeClient().draft("sys", "user", cfg)
    kw = calls[0]
    assert draft == _good() and meta["request_id"] == "req_1"
    assert kw["model"] == "claude-opus-5-5" and kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["effort"] == "medium"
    assert kw["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["extra_body"] == {"fallbacks": "default"}

    monkeypatch.setattr(anthropic, "Anthropic", lambda: Fake("refusal"))
    draft, meta = D.ClaudeClient().draft("sys", "user", cfg)
    assert draft is None and meta["stop_reason"] == "refusal"


def test_review_is_tied_to_the_exact_draft(cfg, tmp_path):
    c: Config = with_overrides(cfg, tmp_path)
    (tmp_path / "reports").mkdir()
    p = tmp_path / "reports" / "ai_commentary_draft.md"
    p.write_text("banner\n<!-- body -->\nversion one", encoding="utf-8")
    sha1 = body_hash(p.read_text(encoding="utf-8"))
    assert current_status(c, sha1).startswith("NOT REVIEWED")
    record_review(c, "A. Reviewer", "approved", "fine")
    assert current_status(c, sha1).startswith("APPROVED by A. Reviewer")
    p.write_text("banner changed\n<!-- body -->\nversion two", encoding="utf-8")
    assert current_status(c, body_hash(p.read_text(encoding="utf-8"))).startswith("NOT REVIEWED")
    with pytest.raises(ValueError):
        record_review(c, "", "approved")
    with pytest.raises(ValueError):
        record_review(c, "B", "maybe")
