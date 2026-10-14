import json

import pytest
from lasteverlm_core import ConfigError

from lasteverlm_rag.config import Settings

from .conftest import (
    AUTH,
    BASE_ENV,
    NOTEBOOK,
    REPORT_DEFAULTS,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
REPORT = json.dumps({"title": "Himmel", "markdown": "Der Himmel ist blau."})
AUDIO = json.dumps(
    {"title": "Gesprochen", "paragraphs": [{"text": "Der Himmel ist blau. Gras ist grün."}]}
)


def ready_store() -> FakeStore:
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    return store


def test_the_catalogue_lists_languages_voices_speeds_and_options_per_kind(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get("/api/rag/outputs/options").status_code == 401
    body = client.get("/api/rag/outputs/options", headers=AUTH).json()
    assert {"code": "de", "label": "Deutsch"} in body["languages"]
    voices = {v["id"]: v for v in body["audio"]["voices"]}
    assert set(voices) == {
        "vivian",
        "serena",
        "uncle_fu",
        "dylan",
        "eric",
        "ryan",
        "aiden",
        "ono_anna",
        "sohee",
    }
    assert (voices["ryan"]["gender"], voices["sohee"]["gender"]) == ("male", "female")
    assert body["audio"]["default_voice"] == "ryan"
    assert body["audio"]["speed"] == {"min": 0.75, "max": 1.5, "step": 0.25, "default": 1.0}
    assert body["kinds"]["report"] == [
        "language",
        "instructions",
        "judge",
        "report_style",
        "length",
    ]
    assert body["kinds"]["audio"] == [
        "language",
        "instructions",
        "judge",
        "voice",
        "speed",
        "audio_style",
        "audio_voice_2",
    ]
    assert body["audio"]["styles"] == ["overview", "story", "conversation", "faq"]
    assert body["audio"]["default_style"] == "overview"


def test_a_text_kind_is_written_in_the_chosen_language_and_keeps_it(settings):
    store = ready_store()
    llm = FakeLLM(REPORT)
    client = make_client(settings, store, FakeRetriever([]), llm)
    r = client.post(OUTPUTS, json={"kind": "report", "options": {"language": "de"}}, headers=AUTH)
    assert r.status_code == 202 and r.json()["options"] == {"language": "de", **REPORT_DEFAULTS}
    client.worker.run_once()
    assert "in German, whatever language the material is written in" in llm.calls[0][0]
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert (out["status"], out["options"]) == ("ready", {"language": "de", **REPORT_DEFAULTS})
    token = client.post(f"/api/rag/outputs/{out['id']}/share", headers=AUTH).json()["share_token"]
    assert client.get(f"/api/rag/shared/{token}").json()["options"] == {
        "language": "de",
        **REPORT_DEFAULTS,
    }


def test_without_a_language_the_document_follows_its_sources(settings):
    llm = FakeLLM(REPORT)
    client = make_client(settings, ready_store(), FakeRetriever([]), llm)
    r = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH)
    assert r.json()["options"] == REPORT_DEFAULTS
    client.worker.run_once()
    assert "Write in the language the material is written in." in llm.calls[0][0]


def test_audio_gets_voice_and_speed_with_defaults_filled_in(settings):
    tts = FakeTTS()
    client = make_client(
        settings, ready_store(), FakeRetriever([]), FakeLLM(AUDIO), tts, FakeObjects()
    )
    r = client.post(OUTPUTS, json={"kind": "audio"}, headers=AUTH)
    assert r.json()["options"] == {"voice": "ryan", "speed": 1.0, "audio_style": "overview"}
    chosen = {"language": "de", "voice": "serena", "speed": 1.25, "audio_style": "story"}
    r = client.post(OUTPUTS, json={"kind": "audio", "options": chosen}, headers=AUTH)
    assert r.json()["options"] == chosen
    client.worker.run_once()
    assert set(tts.settings) == {("ryan", 1.0), ("serena", 1.25)}


@pytest.mark.parametrize(
    ("kind", "options", "message"),
    [
        ("report", {"voice": "ryan"}, "voice: not an option of report"),
        ("report", {"speed": 1.0}, "speed: not an option of report"),
        ("report", {"language": "xx"}, "language: unknown code"),
        ("audio", {"voice": "alloy"}, "voice: unknown voice"),
        ("audio", {"speed": 1.3}, "speed: 1.3 is not between"),
        ("audio", {"speed": 2.0}, "speed: 2.0 is not between"),
        ("audio", {"audio_style": "podcast"}, "audio_style: unknown style"),
        ("audio", {"audio_voice_2": "aiden"}, "audio_voice_2: only for the conversation and faq"),
        (
            "audio",
            {"audio_style": "conversation", "voice": "aiden", "audio_voice_2": "aiden"},
            "audio_voice_2: must differ from voice",
        ),
        ("audio", {"audio_style": "conversation", "audio_voice_2": "x"}, "audio_voice_2: unknown"),
        ("report", {"audio_style": "story"}, "audio_style: not an option of report"),
    ],
)
def test_options_that_do_not_fit_are_422(settings, kind, options, message):
    client = make_client(settings, ready_store(), FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": kind, "options": options}, headers=AUTH)
    assert r.status_code == 422 and message in r.json()["error"], r.text


def test_unknown_option_keys_are_422(settings):
    client = make_client(settings, ready_store(), FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": "report", "options": {"tone": "fun"}}, headers=AUTH)
    assert r.status_code == 422


def test_the_default_voice_must_be_a_platform_voice():
    with pytest.raises(ConfigError, match="TTS_VOICE 'alloy'"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "TTS_VOICE": "alloy"})
