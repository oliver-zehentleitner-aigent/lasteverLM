"""Verification levels: basic is the word and negation check; standard also
judges what that check doubts, once at low; thorough is the judge at medium
with revision. Outputs take the level as an option, chat answers follow the
user's level, and the estimate prices every level."""

import pytest

from lasteverlm_rag.options import OutputOptions, resolve

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
from .test_judging import OUTPUTS, SKY, judges, report

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"


def test_the_level_is_validated_and_stored():
    assert "verification" not in resolve("report", OutputOptions(verification="basic"), "ryan")
    assert (
        resolve("report", OutputOptions(verification="standard"), "ryan")["verification"]
        == "standard"
    )
    thorough = resolve("report", OutputOptions(verification="thorough"), "ryan")
    assert (thorough["verification"], thorough["judge"]) == ("thorough", "medium")
    # stored options pass again unchanged
    assert resolve("report", OutputOptions(**thorough), "ryan") == thorough
    for bad, message in (
        ({"verification": "extreme"}, "verification: unknown value 'extreme'"),
        ({"verification": "standard", "judge": "low"}, "verification: send either"),
    ):
        with pytest.raises(ValueError, match=message):
            resolve("report", OutputOptions(**bad), "ryan")
    with pytest.raises(ValueError, match="verification: not an option of chart"):
        resolve("chart", OutputOptions(verification="standard"), "ryan")


def run(settings, verification, *replies):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    judge_models = judges()
    client = make_client(
        settings, store, FakeRetriever([SKY]), FakeLLM(*replies), judges=judge_models
    )
    body = {"kind": "report", "options": {"verification": verification}}
    r = client.post(OUTPUTS, json=body, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    return client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json(), judge_models


def test_standard_judges_only_what_the_word_check_doubts_once_at_low(settings):
    out, judge_models = run(
        settings,
        "standard",
        report("The sky is blue on a clear day. [1]", "Paris has many museums and cafés. [1]"),
    )
    assert out["status"] == "ready", out
    supported, doubted = out["content"]["units"]
    assert supported["support"] == "supported" and "judge" not in supported
    assert doubted["support"] == "unsupported"
    assert (doubted["judge"]["level"], doubted["judge"]["round"]) == ("low", 1)
    assert judge_models["low"].statements == ["Paris has many museums and cafés."]
    assert judge_models["medium"].statements == [] and judge_models["high"].statements == []
    log = out["provenance"]["judge"]
    assert (log["mode"], log["judged"], log["level"]) == ("doubted", 1, "low")
    assert out["provenance"]["usage"]["judge"] == {"tokens_in": 120, "tokens_out": 15}


def test_thorough_is_the_judge_at_medium_with_revision(settings):
    out, judge_models = run(
        settings, "thorough", report("The sky is blue on a clear day. [1]", "Grass is green. [1]")
    )
    assert out["status"] == "ready", out
    assert out["options"]["verification"] == "thorough"
    assert len(judge_models["medium"].statements) == 2 and judge_models["low"].statements == []


def test_basic_calls_no_judge(settings):
    out, judge_models = run(settings, "basic", report("Paris has many museums. [1]"))
    assert out["status"] == "ready", out
    assert "judge" not in out["content"]["units"][0]
    assert all(not j.statements for j in judge_models.values())


def test_the_estimate_prices_every_level(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.post(
        "/api/rag/estimate",
        json={"kind": "report", "options": {"verification": "standard"}},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    levels = r.json()["levels"]
    assert list(levels) == ["basic", "standard", "thorough"]
    assert levels["standard"]["min"] == levels["basic"]["min"]  # nothing doubted: no judge
    assert levels["basic"]["max"] < levels["standard"]["max"] < levels["thorough"]["max"]
    assert (r.json()["charge_cents_min"], r.json()["charge_cents_max"]) == (
        levels["standard"]["min"],
        levels["standard"]["max"],
    )


def chat(settings, level, answer):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    if level:
        store.preferences[OWNER] = {"verification_level": level}
    judge_models = judges()
    sky = chunk(1, "The sky is blue on a clear day.")
    client = make_client(
        settings, store, FakeRetriever([sky]), FakeLLM(answer), judges=judge_models
    )
    r = client.post(ASK, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json(), store, judge_models


TWO_PARAGRAPHS = "The sky is blue on a clear day [1].\n\nParis has many museums [1]."


def test_a_chat_answer_at_standard_judges_its_doubted_paragraphs(settings):
    body, store, judge_models = chat(settings, "standard", TWO_PARAGRAPHS)
    supported, doubted = body["units"]
    assert "judge" not in supported and doubted["judge"]["level"] == "low"
    assert judge_models["low"].statements == ["Paris has many museums."]
    stored = store.messages[-1]["support"]["judge"]
    assert (stored["mode"], stored["judged"]) == ("doubted", 1)


def test_a_chat_answer_at_thorough_judges_every_paragraph_at_medium(settings):
    body, _, judge_models = chat(settings, "thorough", TWO_PARAGRAPHS)
    assert [u["judge"]["level"] for u in body["units"]] == ["medium", "medium"]
    assert len(judge_models["medium"].statements) == 2


def test_a_chat_answer_at_basic_or_with_an_older_default_off_calls_no_judge(settings):
    body, _, judge_models = chat(settings, None, TWO_PARAGRAPHS)
    assert all("judge" not in u for u in body["units"])
    assert all(not j.statements for j in judge_models.values())
