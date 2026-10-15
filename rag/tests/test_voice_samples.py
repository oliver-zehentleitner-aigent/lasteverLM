from lasteverlm_rag.options import LANGUAGES
from lasteverlm_rag.voice_samples import SAMPLE_TEXT

from .conftest import AUTH, FakeLLM, FakeObjects, FakeRetriever, FakeStore, FakeTTS, make_client

SAMPLE = "/api/rag/outputs/voice-sample"


def client_with(settings, store=None, tts=None, objects=None):
    return make_client(settings, store or FakeStore(), FakeRetriever([]), FakeLLM(), tts, objects)


def test_a_sample_is_synthesized_once_and_then_served_from_storage(settings):
    store, tts, objects = FakeStore(), FakeTTS(), FakeObjects()
    client = client_with(settings, store, tts, objects)
    body = {"voice": "serena", "speed": 1.25, "language": "de"}

    first = client.post(SAMPLE, json=body, headers=AUTH)
    assert first.status_code == 200, first.text
    key = "samples/serena/1.25/de.mp3"
    assert first.json() == {"url": f"https://objects.test/{key}?expires=3600", "cached": False}
    text = SAMPLE_TEXT["de"].format(name="Serena")
    assert tts.inputs == [text] and tts.settings == [("serena", 1.25)]
    assert objects.objects[key][1] == "audio/mpeg"
    (row,) = [u for _, _, u in store.usage if u.kind == "tts"]
    assert (row.tokens_in, row.tokens_out) == (FakeTTS.seconds(text), 0)

    # same combination, any user: no model call, no usage
    second = client.post(SAMPLE, json=body, headers=AUTH)
    assert second.json() == {"url": first.json()["url"], "cached": True}
    assert len(tts.inputs) == 1 and len(store.usage) == 1


def test_defaults_are_english_at_normal_speed(settings):
    tts, objects = FakeTTS(), FakeObjects()
    client = client_with(settings, tts=tts, objects=objects)
    r = client.post(SAMPLE, json={"voice": "ryan"}, headers=AUTH)
    assert r.status_code == 200 and "samples/ryan/1.00/en.mp3" in objects.objects
    assert tts.inputs == [SAMPLE_TEXT["en"].format(name="Ryan")]


def test_values_outside_the_catalogue_are_422(settings):
    client = client_with(settings, tts=FakeTTS(), objects=FakeObjects())
    for body in (
        {"voice": "alloy"},
        {"voice": "ryan", "speed": 3.0},
        {"voice": "ryan", "language": "xx"},
        {"voice": "ryan", "pitch": 2},
        {},
    ):
        assert client.post(SAMPLE, json=body, headers=AUTH).status_code == 422, body


def test_a_new_sample_needs_credit_a_cached_one_does_not(settings):
    objects = FakeObjects()
    broke = FakeStore(balance=0)
    client = client_with(settings, broke, FakeTTS(), objects)
    r = client.post(SAMPLE, json={"voice": "ryan"}, headers=AUTH)
    assert (r.status_code, r.json()) == (402, {"error": "credit exhausted"})
    objects.put("samples/ryan/1.00/en.mp3", b"\xff\xf3", "audio/mpeg")
    assert client.post(SAMPLE, json={"voice": "ryan"}, headers=AUTH).json()["cached"] is True


def test_without_speech_the_endpoint_says_so(settings):
    client = client_with(settings)
    r = client.post(SAMPLE, json={"voice": "ryan"}, headers=AUTH)
    assert (r.status_code, r.json()) == (503, {"error": "text-to-speech is not available"})
    assert client.post(SAMPLE, json={"voice": "ryan"}).status_code == 401


def test_every_catalogue_language_has_a_sample_text():
    assert set(SAMPLE_TEXT) == {lang.code for lang in LANGUAGES}
    assert all("{name}" in text for text in SAMPLE_TEXT.values())


def test_a_synthesis_without_audio_is_a_502_billed_and_not_cached(settings):
    store, objects = FakeStore(), FakeObjects()
    client = client_with(settings, store, FakeTTS(silent=True), objects)
    r = client.post(SAMPLE, json={"voice": "ryan"}, headers=AUTH)
    assert (r.status_code, r.json()) == (
        502,
        {"error": "the model did not answer", "code": "model_no_answer", "cause": "no_audio"},
    )
    assert objects.objects == {}
    seconds = FakeTTS.seconds(SAMPLE_TEXT["en"].format(name="Ryan"))
    # tried twice, both billed
    assert [(u.kind, u.tokens_in) for _, _, u in store.usage] == [("tts", seconds)] * 2
