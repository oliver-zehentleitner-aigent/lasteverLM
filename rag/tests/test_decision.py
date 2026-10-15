import json

import pytest

from lasteverlm_rag.models import Passage
from lasteverlm_rag.options import OutputOptions, resolve
from lasteverlm_rag.outputs.decision import (
    UNDECIDED_TEXT,
    Evidence,
    decision_content,
    evidence_instructions,
    finish_decision,
)
from lasteverlm_rag.provenance import check_units

from .conftest import (
    AUTH,
    NOTEBOOK,
    FakeDecision,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

PASSAGES = [
    Passage(1, "c1", "s1", "a.pdf", "pdf", 1, "The bridge was closed in 2024 for repairs."),
    Passage(2, "c2", "s2", "b.pdf", "pdf", 1, "Traffic moved to the ferry during the repairs."),
]


def decide(options, model_answer, evidence):
    content, units = decision_content(options, model_answer, Evidence.model_validate(evidence))
    check_units(units, PASSAGES)
    replaced = finish_decision(content)
    return content, replaced


FOR = {"text": "The bridge was closed in 2024 for repairs.", "refs": [1]}
AGAINST = {"text": "Traffic moved to the ferry during repairs.", "refs": [2]}
UNSUPPORTED = {"text": "Everyone loved the new bridge design.", "refs": [1]}


@pytest.mark.parametrize(
    ("p", "pro", "con", "agreement"),
    [
        (0.8, [FOR], [], "consistent"),
        (0.2, [], [AGAINST], "consistent"),
        (0.8, [], [AGAINST], "conflicting"),
        (0.2, [FOR], [], "conflicting"),
        (0.5, [FOR], [], "unclear"),
        (0.8, [FOR], [AGAINST], "unclear"),
    ],
)
def test_yes_no_agreement_compares_the_number_with_supported_evidence(p, pro, con, agreement):
    options = {"question": "Was the bridge closed?", "decision_type": "yes_no"}
    content, _ = decide(
        options,
        {"probability_yes": p, "answer": "yes" if p >= 0.5 else "no"},
        {"verdict_text": "It was.", "evidence_for": pro, "evidence_against": con},
    )
    assert content["agreement"] == agreement and content["agreement_note"]
    assert "llm_choice" not in content


def test_without_supported_evidence_the_sources_do_not_decide():
    options = {"question": "Was the bridge closed?", "decision_type": "yes_no"}
    content, replaced = decide(
        options,
        {"probability_yes": 0.95, "answer": "yes"},
        {"verdict_text": "Yes, clearly.", "evidence_for": [UNSUPPORTED], "gaps": ["dates"]},
    )
    assert content["agreement"] == "undecided" and content["verdict_text"] == UNDECIDED_TEXT
    assert replaced == "Yes, clearly."  # goes into the log, never silently dropped
    assert content["model_answer"]["probability_yes"] == 0.95  # still shown
    assert content["evidence_for"][0]["support"] == "unsupported"
    assert content["gaps"] == ["dates"]


def test_choice_agreement_compares_both_picks():
    options = {"question": "Which?", "decision_type": "choice", "choices": ["Ferry", "Bridge"]}
    answer = {"choice": "Bridge", "distribution": {"Ferry": 0.3, "Bridge": 0.7}, "confidence": 0.7}
    same, _ = decide(
        options, answer, {"verdict_text": "x", "llm_choice": "Bridge", "evidence_for": [FOR]}
    )
    other, _ = decide(
        options, answer, {"verdict_text": "x", "llm_choice": "Ferry", "evidence_for": [AGAINST]}
    )
    unknown, _ = decide(
        options, answer, {"verdict_text": "x", "llm_choice": "Boat", "evidence_for": [FOR]}
    )
    assert (same["agreement"], same["llm_choice"]) == ("consistent", "Bridge")
    assert (other["agreement"], other["llm_choice"]) == ("conflicting", "Ferry")
    assert (unknown["agreement"], unknown["llm_choice"]) == ("unclear", None)


def test_the_evidence_prompt_never_carries_the_models_answer():
    text = evidence_instructions("Which?", "scale", ["low", "mid", "high"])
    assert '"low"; "mid"; "high"' in text and "lowest first" in text
    assert "probability" not in text and "distribution" not in text


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "question: a decision needs a question"),
        ({"question": "x" * 501}, "question: at most 500"),
        ({"question": "q", "decision_type": "maybe"}, "decision_type: unknown"),
        ({"question": "q", "decision_type": "choice"}, "choices: 2 to 8"),
        ({"question": "q", "decision_type": "choice", "choices": ["a", "A"]}, "distinct"),
        ({"question": "q", "decision_type": "scale", "levels": ["a", "b"]}, "levels: 3 to 7"),
        ({"question": "q", "choices": ["a", "b"]}, "choices: not an option of decision_type"),
        ({"question": "q", "voice": "ryan"}, "voice: not an option of decision"),
    ],
)
def test_decision_options_that_do_not_fit_raise(options, message):
    with pytest.raises(ValueError, match=message):
        resolve("decision", OutputOptions.model_validate(options), "ryan")


def test_decision_options_are_normalised_with_defaults():
    resolved = resolve(
        "decision",
        OutputOptions(
            question="  Should  we go? ", decision_type="scale", levels=["low", " mid ", "high"]
        ),
        "ryan",
    )
    assert resolved == {
        "question": "Should we go?",
        "decision_type": "scale",
        "levels": ["low", "mid", "high"],
    }
    assert resolve("decision", OutputOptions(question="q"), "ryan")["decision_type"] == "yes_no"


# -- end to end: API, worker, both calls ---------------------------------------


OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
EVIDENCE = json.dumps(
    {
        "verdict_text": "Yes, the bridge was closed.",
        "llm_choice": None,
        "evidence_for": [{"text": "The bridge was closed in 2024 for repairs.", "refs": [1]}],
        "evidence_against": [],
        "gaps": ["How long the closure lasted."],
    }
)


def run_decision(settings, options, decision, reply=EVIDENCE):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.pdf", summary="About the bridge.")
    retriever = FakeRetriever([chunk(1, "The bridge was closed in 2024 for repairs.")])
    llm = FakeLLM(reply)
    client = make_client(settings, store, retriever, llm, decision=decision)
    r = client.post(OUTPUTS, json={"kind": "decision", "options": options}, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    return store, llm, out


def test_a_yes_no_decision_joins_the_models_number_and_the_independent_evidence(settings):
    decision = FakeDecision({"type": "noul", "noul": 0.83})
    store, llm, out = run_decision(settings, {"question": "Was the bridge closed?"}, decision)
    assert out["status"] == "ready", out
    content = out["content"]
    assert content["model_answer"] == {"probability_yes": 0.83, "answer": "yes"}
    assert content["evidence_for"][0]["support"] == "supported"
    assert (content["agreement"], content["verdict_text"]) == (
        "consistent",
        "Yes, the bridge was closed.",
    )
    assert out["title"] == "Was the bridge closed?"
    # the decision model got the question and the numbered passages
    ((state, questions),) = decision.calls
    assert questions == {"decision": {"type": "noul", "instructions": "Was the bridge closed?"}}
    assert state["passages"][0]["n"] == 1
    # the LLM never saw the number
    assert "0.83" not in llm.calls[0][1] and "83%" not in llm.calls[0][1]
    calls = out["provenance"]["calls"]
    assert [c["role"] for c in calls] == ["decision", "evidence"]
    assert calls[0]["usage"] == {"tokens_in": 100} and calls[0]["state"]["passages"] == 1
    assert out["provenance"]["usage"]["decision"] == {"tokens_in": 100}
    assert out["provenance"]["focus_query"] == "Was the bridge closed?"
    assert [u.kind for _, _, u in store.usage].count("decision") == 1


def test_an_undecided_decision_keeps_the_llms_sentence_in_the_log(settings):
    reply = json.dumps(
        {
            "verdict_text": "Probably yes.",
            "evidence_for": [{"text": "Fireworks lit the sky every night.", "refs": [1]}],
        }
    )
    _, _, out = run_decision(
        settings,
        {"question": "Was it closed?"},
        FakeDecision({"type": "noul", "noul": 0.9}),
        reply,
    )
    assert out["content"]["agreement"] == "undecided"
    assert out["content"]["verdict_text"] == "The sources do not decide this."
    assert out["provenance"]["llm_verdict_text"] == "Probably yes."


def test_a_scale_decision_is_normalised_to_its_level_labels(settings):
    raw = {
        "type": "score",
        "score": 1.6,
        "legend": {"0": "low", "1": "mid", "2": "high"},
        "probabilities": {"0": 0.1, "1": 0.2, "2": 0.7},
        "confidence": 0.7,
    }
    reply = json.dumps({**json.loads(EVIDENCE), "llm_choice": "high"})
    decision = FakeDecision(raw)
    _, _, out = run_decision(
        settings,
        {"question": "How bad?", "decision_type": "scale", "levels": ["low", "mid", "high"]},
        decision,
        reply,
    )
    assert out["content"]["model_answer"] == {
        "level": "high",
        "score": 1.6,
        "legend": ["low", "mid", "high"],
        "distribution": {"low": 0.1, "mid": 0.2, "high": 0.7},
        "confidence": 0.7,
    }
    assert out["content"]["llm_choice"] == "high"
    assert out["content"]["agreement"] == "consistent"
    assert decision.calls[0][1]["decision"]["criteria"] == ["low", "mid", "high"]


def test_a_decision_without_a_decision_model_fails_clearly(settings):
    _, _, out = run_decision(settings, {"question": "Was it closed?"}, None)
    assert (out["status"], out["error"]) == (
        "failed",
        "decision: no decision model on this deployment",
    )


def test_a_decision_needs_its_question(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": "decision"}, headers=AUTH)
    assert r.status_code == 422 and "question" in r.json()["error"]
