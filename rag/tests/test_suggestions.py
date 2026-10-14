"""Suggested questions with every answer and for a new notebook; feedback
on answers and its admin overview."""

import json

import pytest

from lasteverlm_rag.suggestions import split_suggestions

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    OWNER,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"
SUGGEST = f"/api/rag/notebooks/{NOTEBOOK}/suggestions"
SKY = chunk(1, "The sky is blue on a clear day.")
ANSWER = (
    "The sky is blue on a clear day [1].\n\nSuggestions:\n"
    "- Why is the sky blue? [1]\n- What colour is it at night?\n- Does it change in winter?\n"
    "- One too many?"
)


def ask(client):
    return client.post(ASK, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH)


@pytest.mark.parametrize(
    ("text", "answer", "suggestions"),
    [
        ("A [1].\n\nSuggestions:\n- B?\n- C?", "A [1].", ["B?", "C?"]),
        ("A.\n**Suggestions:**\n1. B?\n2) C?\n* D?", "A.", ["B?", "C?", "D?"]),
        ("A.\nsuggestions\n- B? [2]\n-   \n- b?", "A.", ["B?"]),
        ("A without a tail.", "A without a tail.", []),
        ("Suggestions: are good.\n\nSuggestions:\n- B?", "Suggestions: are good.", ["B?"]),
    ],
)
def test_the_suggestion_tail_is_cut_off_and_cleaned(text, answer, suggestions):
    assert split_suggestions(text) == (answer, suggestions)


def test_an_answer_brings_its_suggestions_from_the_same_call(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    llm = FakeLLM(ANSWER)
    client = make_client(settings, store, FakeRetriever([SKY]), llm)
    body = ask(client).json()
    assert body["answer"] == "The sky is blue on a clear day [1]."
    assert body["suggestions"] == [
        "Why is the sky blue?",
        "What colour is it at night?",
        "Does it change in winter?",
    ]
    assert [c["n"] for c in body["citations"]] == [1]
    assert len(llm.calls) == 1 and 'write "Suggestions:"' in llm.calls[0][0]
    stored = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert stored[-1]["suggestions"] == body["suggestions"] and stored[0]["suggestions"] == []


def test_a_notebook_gets_starting_questions_cached_until_its_uploads_change(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    assert client.get(SUGGEST, headers=AUTH).json() == {"suggestions": [], "cached": False}
    assert store.usage == []  # no upload, no call

    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    reply = json.dumps({"questions": ["Why is the sky blue? [1]", "When is it grey?", "x" * 200]})
    llm = FakeLLM(reply)
    client = make_client(settings, store, FakeRetriever([]), llm)
    first = client.get(SUGGEST, headers=AUTH).json()
    assert first["cached"] is False
    assert first["suggestions"][:2] == ["Why is the sky blue?", "When is it grey?"]
    assert len(first["suggestions"][2]) == 150
    assert "About the sky." in llm.calls[0][1]
    assert [a for a, _ in store.bookings] == ["chat_answer"]
    assert client.get(SUGGEST, headers=AUTH).json() == {**first, "cached": True}
    assert len(llm.calls) == 1

    store.add_source(NOTEBOOK, "grass.pdf", summary="About grass.")
    assert client.get(SUGGEST, headers=AUTH).json()["cached"] is False
    assert len(llm.calls) == 2


def test_starting_questions_that_do_not_parse_are_a_billed_502(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM("no json"))
    r = client.get(SUGGEST, headers=AUTH)
    assert r.status_code == 502 and len(store.usage) == 1
    assert store.suggestions == {}
    other = f"/api/rag/notebooks/{OTHER_NOTEBOOK}/suggestions"
    assert client.get(other, headers=AUTH).status_code == 404
    assert client.get(SUGGEST).status_code == 401


def test_an_answer_is_rated_and_the_rating_can_change(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    client = make_client(settings, store, FakeRetriever([SKY]), FakeLLM(ANSWER))
    message_id = ask(client).json()["message_id"]
    path = f"/api/rag/messages/{message_id}/feedback"
    r = client.post(path, json={"rating": "up"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["feedback"]["rating"] == "up"
    r = client.post(path, json={"rating": "down", "comment": "  wrong colour "}, headers=AUTH)
    feedback = r.json()["feedback"]
    assert (feedback["rating"], feedback["comment"]) == ("down", "wrong colour")
    listed = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert listed[-1]["feedback"]["rating"] == "down" and listed[0]["feedback"] is None

    question = listed[0]["id"]
    r = client.post(f"/api/rag/messages/{question}/feedback", json={"rating": "up"}, headers=AUTH)
    assert (r.status_code, r.json()) == (409, {"error": "feedback is for answers only"})
    other = store.insert_message(OTHER_NOTEBOOK, CONVERSATION, "assistant", "x", [])
    r = client.post(f"/api/rag/messages/{other.id}/feedback", json={"rating": "up"}, headers=AUTH)
    assert r.status_code == 404
    for bad in ({"rating": "meh"}, {"rating": "up", "comment": "x" * 1001}, {}):
        assert client.post(path, json=bad, headers=AUTH).status_code == 422
    assert client.post(path, json={"rating": "up"}).status_code == 401


def test_the_feedback_overview_is_for_admins_and_viewers(settings):
    for store, status in (
        (FakeStore(), 403),
        (FakeStore(viewers={OWNER}), 200),
        (FakeStore(admins={OWNER}), 200),
    ):
        client = make_client(settings, store, FakeRetriever([]), FakeLLM())
        r = client.get("/api/rag/admin/feedback", headers=AUTH)
        assert r.status_code == status, r.text
        if status == 200:
            assert {"days", "latest_down"} <= set(r.json())
    assert client.get("/api/rag/admin/feedback?days=0", headers=AUTH).status_code == 422


def test_starting_questions_have_an_estimate(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    body = {"action": "chat_answer", "options": {"suggestions": True}}
    starting = client.post("/api/rag/estimate", json=body, headers=AUTH).json()
    answer = client.post("/api/rag/estimate", json={"action": "chat_answer"}, headers=AUTH).json()
    assert 0 < starting["charge_cents_max"] < answer["charge_cents_max"]


def test_a_viewer_sees_the_feedback_counts_but_not_the_answers(settings):
    store = FakeStore(viewers={OWNER})
    store.add_source(NOTEBOOK, "sky.pdf")
    client = make_client(settings, store, FakeRetriever([SKY]), FakeLLM(ANSWER))
    message_id = ask(client).json()["message_id"]
    client.post(f"/api/rag/messages/{message_id}/feedback", json={"rating": "down"}, headers=AUTH)
    body = client.get("/api/rag/admin/feedback", headers=AUTH).json()
    assert body["latest_down"] == [] and body["detail"] == "admins only"
    assert "days" in body

    store.viewers.clear()
    store.admins.add(OWNER)
    body = client.get("/api/rag/admin/feedback", headers=AUTH).json()
    assert [r["message_id"] for r in body["latest_down"]] == [message_id]
    assert "detail" not in body
