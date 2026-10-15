"""Bulletproof: the high judge and a second judge of another family on every
unit; supported only if both say so, disputed (kept, marked, revised like a
failing unit) when they disagree, removed when both fail."""

import json

import pytest
from lasteverlm_core import CompletionResult, Usage

from lasteverlm_rag.judge import Judgement
from lasteverlm_rag.judging import DISPUTED, DISPUTED_REASON, pair

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    OWNER,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)
from .test_judging import OUTPUTS, SKY, RuleJudge, judges, report, revision

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"


def judgement(verdict):
    return Judgement(verdict, f"{verdict} by rule", "q", True)


@pytest.mark.parametrize(
    ("first", "second", "result"),
    [
        ("supported", "supported", "supported"),
        ("contradicted", "not_in_source", "contradicted"),
        ("contradicted", "supported", DISPUTED),
        ("supported", "not_in_source", DISPUTED),
        ("supported", None, None),  # a judge without an answer passes nothing
        (None, "contradicted", "contradicted"),
    ],
)
def test_two_judges_pass_a_unit_only_together(first, second, result):
    paired = pair(judgement(first), judgement(second))
    assert paired.verdict == result
    if result == DISPUTED:
        assert paired.reason == DISPUTED_REASON


class LenientJudge(RuleJudge):
    """Another family's judge: misses what is only "wrong", sees what is "missing"."""

    def complete(self, system, user, max_tokens=None, *, thinking=None):
        statement = user.split("\n")[1]
        with self._lock:
            self.statements.append(statement)
        verdict = "not_in_source" if "missing" in statement else "supported"
        reply = json.dumps({"verdict": verdict, "reason": f"{verdict} by second", "quote": "q"})
        return CompletionResult(reply, Usage("llm", self.model, 100, 10))


def bulletproof_judges():
    found = judges()
    found["second"] = LenientJudge("test-judge-second")
    return found


def test_a_bulletproof_output_keeps_a_disputed_unit_and_removes_a_failing_one(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    judge_models = bulletproof_judges()
    keep = lambda i, text: {"index": i, "action": "revise", "unit": {"text": text}}  # noqa: E731
    llm = FakeLLM(
        report(
            "The sky is blue. [1]", "The sky is wrong green. [1]", "Grass is missing purple. [1]"
        ),
        revision(keep(1, "The sky is wrong green. [1]"), keep(2, "Grass is missing purple. [1]")),
        revision(keep(1, "The sky is wrong green. [1]"), keep(2, "Grass is missing purple. [1]")),
    )
    client = make_client(settings, store, FakeRetriever([SKY]), llm, judges=judge_models)
    r = client.post(
        OUTPUTS, json={"kind": "report", "options": {"verification": "bulletproof"}}, headers=AUTH
    )
    assert r.status_code == 202, r.text
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready", out
    assert out["options"] == {
        "verification": "bulletproof",
        "judge": "high",
        "report_style": "briefing",
        "length": "medium",
    }
    units = out["content"]["units"]
    assert [u["text"] for u in units] == ["The sky is blue. [1]", "The sky is wrong green. [1]"]
    passed, disputed = units
    assert passed["judge"]["verdict"] == "supported"
    assert passed["judge"]["second"]["verdict"] == "supported"
    assert (disputed["judge"]["verdict"], disputed["judge"]["reason"]) == (
        DISPUTED,
        DISPUTED_REASON,
    )
    assert disputed["judge"]["second"] == {
        "model": "test-judge-second",
        "verdict": "supported",
        "reason": "supported by second",
        "quote": "q",
    }
    # each judge's own verdict beside the result
    assert disputed["judge"]["first"] == {
        "verdict": "contradicted",
        "reason": "contradicted by rule",
        "quote": "The sky is blue",
    }
    assert disputed["judge"]["round"] == 3  # revised like a failing unit, judged again
    log = out["provenance"]["judge"]
    assert log["second_model"] == "test-judge-second"
    assert [r["text"] for r in log["removed"]] == ["Grass is missing purple. [1]"]
    # both judges saw every unit of the first round
    assert len(judge_models["second"].statements) >= 3 and len(judge_models["high"].statements) >= 3


def test_a_chat_answer_at_bulletproof_marks_a_disputed_paragraph(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    store.preferences[OWNER] = {"verification_level": "bulletproof"}
    sky = chunk(1, "The sky is blue on a clear day.")
    answer = "The sky is blue on a clear day [1].\n\nThe sky is wrong green on a clear day [1]."
    client = make_client(
        settings, store, FakeRetriever([sky]), FakeLLM(answer), judges=bulletproof_judges()
    )
    body = client.post(
        ASK, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH
    ).json()
    first, second = body["units"]
    assert first["judge"]["verdict"] == "supported" and first["judge"]["level"] == "high"
    assert second["judge"]["verdict"] == DISPUTED
    assert second["judge"]["second"]["model"] == "test-judge-second"
