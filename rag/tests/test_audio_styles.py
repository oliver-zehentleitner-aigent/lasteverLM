import json

import pytest

from lasteverlm_rag.models import SpeechTurn
from lasteverlm_rag.options import second_voice
from lasteverlm_rag.outputs.audio import Conversation
from lasteverlm_rag.service import voiced_stretches

from .conftest import (
    AUTH,
    NOTEBOOK,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
CONVERSATION = json.dumps(
    {
        "title": "The sky, discussed",
        "turns": [
            {"speaker": "interviewer", "text": "What colour is the sky?"},
            {"speaker": "expert", "text": "Blue, according to the material."},
            {"speaker": "expert", "text": "At noon, at least."},
            {"speaker": "interviewer", "text": "Thank you."},
        ],
    }
)
STORY = json.dumps(
    {
        "title": "A day of sky",
        "paragraphs": [
            {"text": "It began at dawn.", "refs": [1]},
            {"text": "By noon the sky was blue.", "refs": [1]},
        ],
    }
)


def run(settings, reply: str, options: dict):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    llm, tts, objects = FakeLLM(reply), FakeTTS(), FakeObjects()
    client = make_client(settings, store, FakeRetriever([]), llm, tts, objects)
    r = client.post(OUTPUTS, json={"kind": "audio", "options": options}, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    output_id = r.json()["id"]
    return store, client, llm, tts, output_id


def test_a_conversation_reads_each_turn_with_its_speakers_voice(settings):
    store, client, llm, tts, output_id = run(
        settings, CONVERSATION, {"audio_style": "conversation", "voice": "ryan"}
    )
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert out["status"] == "ready", out
    assert out["options"]["audio_voice_2"] == "aiden"  # the default second voice
    assert "an interviewer, who introduces the topic" in llm.calls[0][1]
    # consecutive turns of one speaker are one request
    assert [s[0] for s in tts.settings] == ["ryan", "aiden", "ryan"]
    assert tts.inputs[1] == "Blue, according to the material. At noon, at least."
    assert [t["speaker"] for t in out["content"]["transcript"]] == [
        "interviewer",
        "expert",
        "expert",
        "interviewer",
    ]
    assert len([u for _, _, u in store.usage if u.kind == "tts"]) == 3
    (generated,) = [s for s in store.sources.values() if s["kind"] == "generated"]
    assert "Interviewer: What colour is the sky?" in generated["summary"]

    token = client.post(f"/api/rag/outputs/{output_id}/share", headers=AUTH).json()
    shared = client.get(f"/api/rag/shared/{token['share_token']}").json()
    assert shared["content"]["transcript"] == out["content"]["transcript"]
    assert shared["options"]["audio_style"] == "conversation"


def test_a_story_is_told_by_one_narrator_in_paragraphs(settings):
    _, client, llm, tts, output_id = run(settings, STORY, {"audio_style": "story"})
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert "a narrative with a beginning, a middle and an end" in llm.calls[0][1]
    assert "invent no events" in llm.calls[0][1]
    # refs to passages the prompt never had: kept as text, marked unsupported
    assert out["content"]["transcript"] == [
        {"speaker": "narrator", "text": "It began at dawn.", "refs": [], "support": "unsupported"},
        {
            "speaker": "narrator",
            "text": "By noon the sky was blue.",
            "refs": [],
            "support": "unsupported",
        },
    ]
    assert tts.inputs == ["It began at dawn. By noon the sky was blue."]
    assert tts.settings == [("ryan", 1.0)]


def test_the_overview_stays_the_default(settings):
    _, client, llm, _, output_id = run(settings, STORY, {})
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert out["options"]["audio_style"] == "overview"
    assert "a spoken overview of the material" in llm.calls[0][1]


@pytest.mark.parametrize(
    "turns",
    [
        [{"speaker": "expert", "text": "a"}, {"speaker": "expert", "text": "b"}],
        [{"speaker": "interviewer", "text": "x" * 1500}] * 3
        + [{"speaker": "expert", "text": "x" * 1500}] * 2,
        [{"speaker": "host", "text": "a"}, {"speaker": "expert", "text": "b"}],
    ],
)
def test_a_conversation_needs_both_speakers_within_the_length(turns):
    with pytest.raises(ValueError):
        Conversation.model_validate({"title": "t", "turns": turns})


def test_a_conversation_that_breaks_the_schema_fails_after_one_retry(settings):
    reply = json.dumps({"title": "t", "turns": [{"speaker": "expert", "text": "Only me."}] * 2})
    store, _, llm, tts, output_id = run(settings, reply, {"audio_style": "conversation"})
    row = store.outputs[output_id]
    assert row["status"] == "failed" and "did not match the document format" in row["error"]
    assert len(llm.calls) == 2 and tts.inputs == []


def test_the_second_voice_shares_the_first_ones_native_language():
    assert [second_voice(v) for v in ("ryan", "aiden", "vivian", "eric", "sohee")] == [
        "aiden",
        "ryan",
        "serena",
        "vivian",
        "ryan",
    ]


def test_voiced_stretches_join_consecutive_turns_of_one_voice():
    turns = [
        SpeechTurn("interviewer", "Q1"),
        SpeechTurn("expert", "A1"),
        SpeechTurn("expert", "A2"),
        SpeechTurn("narrator", "N"),
    ]
    options = {"voice": "ryan", "audio_voice_2": "aiden"}
    assert voiced_stretches(turns, options) == [
        ("ryan", "Q1"),
        ("aiden", "A1 A2"),
        ("ryan", "N"),
    ]
