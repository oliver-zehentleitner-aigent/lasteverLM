"""Flashcards: front, back, hint; the back is the checked claim."""

import json

import pytest

from lasteverlm_rag.judging import stored_units
from lasteverlm_rag.outputs.flashcards import FlashcardsGenerator

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, chunk, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day because air scatters blue light.")


def deck(count: int, back: str = "Air scatters blue light.") -> str:
    card = {"front": "Why is the sky blue?", "back": back, "hint": "light", "refs": [1]}
    plain = {"front": "Sky colour", "back": "Blue on a clear day.", "refs": [1]}
    return json.dumps(
        {"title": "Sky cards", "cards": [card, plain] * (count // 2) + [card] * (count % 2)}
    )


def run(settings, options, *replies):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    llm = FakeLLM(*replies)
    client = make_client(settings, store, FakeRetriever([SKY]), llm)
    r = client.post(OUTPUTS, json={"kind": "flashcards", "options": options}, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    return llm, client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()


def test_a_deck_has_its_count_and_every_card_is_checked(settings):
    llm, out = run(settings, {"card_count": 6, "difficulty": "hard", "audience": "teens"}, deck(6))
    assert out["status"] == "ready", out
    assert out["options"] == {"card_count": 6, "difficulty": "hard", "audience": "teens"}
    cards = out["content"]["cards"]
    assert len(cards) == 6
    assert cards[0] == {
        "front": "Why is the sky blue?",
        "back": "Air scatters blue light.",
        "hint": "light",
        "refs": [1],
        "support": "supported",
    }
    assert "hint" not in cards[1]
    prompt = llm.calls[0][1]
    assert "exactly 6 flashcards" in prompt and "relations between points" in prompt
    assert "Write for teenagers" in prompt
    assert out["provenance"]["prompt_version"] == "flashcards-v3"
    assert out["provenance"]["check"]["supported"] == 6


def test_defaults_too_few_cards_and_an_unsupported_back(settings):
    llm, out = run(settings, {}, deck(3), deck(15, back="Mountains are made of cheese."))
    assert out["options"] == {"card_count": 15, "difficulty": "medium", "audience": "adults"}
    assert "3 cards, but exactly 15 were asked for" in llm.calls[1][1]
    supports = {c["back"]: c["support"] for c in out["content"]["cards"]}
    assert supports["Mountains are made of cheese."] == "unsupported"


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"card_count": 4}, "card_count: between 5 and 50"),
        ({"card_count": 51}, "card_count: between 5 and 50"),
        ({"difficulty": "brutal"}, "difficulty: unknown value"),
        ({"question_count": 10}, "question_count: not an option of flashcards"),
    ],
)
def test_options_that_do_not_fit_are_422(settings, options, message):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": "flashcards", "options": options}, headers=AUTH)
    assert r.status_code == 422 and message in r.json()["error"], r.text


def test_the_catalogue_estimate_and_stored_units_know_flashcards(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    catalogue = client.get("/api/rag/outputs/options", headers=AUTH).json()
    assert catalogue["flashcards"]["card_count"] == {"min": 5, "max": 50, "default": 15}
    assert catalogue["kinds"]["flashcards"][-3:] == ["card_count", "difficulty", "audience"]
    plain = client.post("/api/rag/estimate", json={"kind": "flashcards"}, headers=AUTH).json()
    judged = client.post(
        "/api/rag/estimate",
        json={"kind": "flashcards", "options": {"judge": "low", "card_count": 50}},
        headers=AUTH,
    ).json()
    assert 0 < plain["charge_cents_max"] < judged["charge_cents_max"]

    gen = FlashcardsGenerator()
    _, schema = gen.prompt({"card_count": 5})
    out = gen.to_output(schema.model_validate(json.loads(deck(5))))
    assert [(u.text, u.refs) for u in stored_units("flashcards", {"cards": [
        {**u.target, "refs": u.refs} for u in out.units
    ]})] == [(u.text, u.refs) for u in out.units]  # fmt: skip
