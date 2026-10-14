"""Every usage row is booked under its user action: one action_id per
action, so core charges a fixed fee once; and the estimate before an
action runs."""

import json
import uuid

import pytest
from lasteverlm_core import USAGE_ACTIONS, PricingRules

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    FakeDecision,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    chunk,
    make_client,
)
from .test_judging import judges, report, revision

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day. In 2024 it rained 120 days.")


def setup(settings, *replies, **extra):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    client = make_client(settings, store, FakeRetriever([SKY]), FakeLLM(*replies), **extra)
    return store, client


def actions(store: FakeStore) -> list[str]:
    return [action for action, _ in store.bookings]


def test_a_chat_answer_is_one_action(settings):
    store, client = setup(settings, "The sky is blue [1].")
    ask = f"/api/rag/notebooks/{NOTEBOOK}/ask"
    for _ in range(2):
        client.post(ask, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH)
    assert actions(store) == ["chat_answer"] * 4
    first, second = {i for _, i in store.bookings[:2]}, {i for _, i in store.bookings[2:]}
    assert len(first) == 1 and len(second) == 1 and first != second


def test_an_output_with_its_judge_rounds_is_one_action_under_its_id(settings):
    store, client = setup(
        settings,
        report("The sky is blue. [1]", "The sky is wrong green. [1]"),
        revision({"index": 1, "action": "revise", "unit": {"text": "It rained 120 days. [1]"}}),
        judges=judges(),
    )
    r = client.post(OUTPUTS, json={"kind": "report", "options": {"judge": "low"}}, headers=AUTH)
    client.worker.run_once()
    assert set(actions(store)) == {"output:report"}
    assert {i for _, i in store.bookings} == {uuid.UUID(r.json()["id"])}
    models = [u.model for _, _, u in store.usage]
    # focus query, generation, judge x2, revision, judge, index
    assert models.count("test-judge-low") == 3 and models.count("test-llm") == 2


def test_every_segment_of_an_audio_and_both_calls_of_a_decision_share_the_output(settings):
    script = json.dumps(
        {"title": "A", "paragraphs": [{"text": "One. " * 200}, {"text": "Two. " * 200}]}
    )
    store, client = setup(settings, script, tts=FakeTTS(), objects=FakeObjects())
    audio = client.post(OUTPUTS, json={"kind": "audio"}, headers=AUTH).json()["id"]
    client.worker.run_once()
    tts_rows = [
        b for b, (_, _, u) in zip(store.bookings, store.usage, strict=True) if u.kind == "tts"
    ]
    assert len(tts_rows) > 1 and set(tts_rows) == {("output:audio", uuid.UUID(audio))}

    evidence = json.dumps(
        {"verdict_text": "Yes.", "evidence_for": [{"text": "The sky is blue.", "refs": [1]}]}
    )
    store, client = setup(settings, evidence, decision=FakeDecision({"type": "noul", "noul": 0.9}))
    body = {"kind": "decision", "options": {"question": "Is the sky blue?"}}
    decision = client.post(OUTPUTS, json=body, headers=AUTH).json()["id"]
    client.worker.run_once()
    assert set(store.bookings) == {("output:decision", uuid.UUID(decision))}
    assert {u.kind for _, _, u in store.usage} >= {"decision", "llm", "embedding"}


def test_a_proposal_a_judgement_on_request_and_a_preview_are_actions_of_their_own(settings):
    proposal = json.dumps(
        {
            "charts": [
                {
                    "title": "Rain",
                    "chart_type": "bar",
                    "series": [{"name": "Days", "points": [{"x": "2024", "y": 120, "refs": [1]}]}],
                }
            ]
        }
    )
    store, client = setup(settings, proposal)
    client.post(f"/api/rag/notebooks/{NOTEBOOK}/charts/propose", json={}, headers=AUTH)
    assert actions(store) == ["chart_propose", "chart_propose"]

    store, client = setup(settings, report("The sky is blue. [1]"), judges=judges())
    out = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    client.worker.run_once()
    store.bookings.clear()
    client.post(f"/api/rag/outputs/{out}/judge", json={"level": "high"}, headers=AUTH)
    ((action, action_id),) = set(store.bookings)
    assert action == "judge" and action_id != uuid.UUID(out)

    store, client = setup(settings, tts=FakeTTS(), objects=FakeObjects())
    client.post("/api/rag/outputs/voice-sample", json={"voice": "ryan"}, headers=AUTH)
    assert actions(store) == ["voice_sample"]


def test_every_action_rag_books_is_one_core_knows():
    booked = {"chat_answer", "chart_propose", "judge", "voice_sample"}
    booked |= {f"output:{kind}" for kind in ("report", "quiz", "table", "mindmap")}
    booked |= {f"output:{kind}" for kind in ("infographic", "audio", "decision", "chart")}
    assert booked <= set(USAGE_ACTIONS)


# -- the estimate ------------------------------------------------------------------

ESTIMATE = "/api/rag/estimate"


def test_an_output_estimate_is_a_range_with_the_fee_counted_once(settings):
    store, client = setup(settings)
    r = client.post(ESTIMATE, json={"kind": "report"}, headers=AUTH)
    assert r.status_code == 200, r.text
    plain = r.json()
    assert plain["action"] == "output:report"
    assert 0 < plain["charge_cents_min"] < plain["charge_cents_max"]
    # no rules: the charge is the cost
    assert plain["charge_cents_max"] == plain["cost_cents_max"]

    store.rules = PricingRules.parse(
        {"actions": {"output:report": {"margin_pct": 100, "fixed_cents": 5}}}
    )
    priced = client.post(ESTIMATE, json={"kind": "report"}, headers=AUTH).json()
    assert priced["cost_cents_max"] == plain["cost_cents_max"]
    # double the cost, plus one fee of 5 cents for the whole output
    assert priced["charge_cents_max"] == pytest.approx(2 * plain["cost_cents_max"] + 5, abs=0.02)


def test_a_judge_level_widens_the_range_by_up_to_three_rounds(settings):
    _, client = setup(settings)
    plain = client.post(ESTIMATE, json={"kind": "report"}, headers=AUTH).json()
    judged = client.post(
        ESTIMATE, json={"kind": "report", "options": {"judge": "high"}}, headers=AUTH
    ).json()
    assert judged["charge_cents_min"] > plain["charge_cents_min"]
    assert judged["charge_cents_max"] > plain["charge_cents_max"]
    on_request = client.post(
        ESTIMATE,
        json={"action": "judge", "options": {"level": "low", "kind": "quiz", "question_count": 5}},
        headers=AUTH,
    ).json()
    assert on_request["action"] == "judge" and on_request["charge_cents_min"] > 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"kind": "report", "action": "chat_answer"},
        {"action": "summary"},
        {"kind": "report", "options": {"judge": "extreme"}},
        {"action": "judge", "options": {"level": "ultra"}},
        {"kind": "audio"},  # no text-to-speech on this deployment
    ],
)
def test_an_estimate_that_cannot_be_made_is_422(settings, body):
    _, client = setup(settings)
    r = client.post(ESTIMATE, json=body, headers=AUTH)
    assert r.status_code == 422, r.text


def test_actions_without_an_output_can_be_estimated(settings):
    _, client = setup(settings)
    for action in ("chat_answer", "chart_propose"):
        body = client.post(ESTIMATE, json={"action": action}, headers=AUTH).json()
        assert body["action"] == action and body["charge_cents_max"] > 0
    assert client.post(ESTIMATE, json={"action": "chat_answer"}).status_code == 401
