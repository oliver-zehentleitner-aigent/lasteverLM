"""Where each spoken turn lies in the final MP3, measured from its frames."""

import json

import pytest

from lasteverlm_rag import mp3

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
# MPEG-2 layer III, 64 kbit/s, 24 kHz, no padding: 192 bytes, 576 samples (0.024 s)
FRAME = bytes([0xFF, 0xF3, 0x84, 0xC4]) + bytes(188)
FRAME_S = 576 / 24000


class FramesTTS(FakeTTS):
    """Real MP3 frames: one per 5 characters, fewer when spoken faster, as
    the platform's speed option shortens the audio it returns."""

    def synthesize(self, text, *, voice=None, speed=None):
        result = super().synthesize(text, voice=voice, speed=speed)
        frames = max(1, round(len(text) / 5 / (speed or 1.0)))
        return type(result)(FRAME * frames, result.usage)


def run(settings, script: dict, options: dict):
    store, objects = FakeStore(), FakeObjects()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    tts = FramesTTS()
    client = make_client(
        settings, store, FakeRetriever([]), FakeLLM(json.dumps(script)), tts, objects
    )
    output_id = client.post(
        OUTPUTS, json={"kind": "audio", "options": options}, headers=AUTH
    ).json()["id"]
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    return out, objects.get(store.outputs[output_id]["content"]["key"])


CONVERSATION = {
    "title": "Sky",
    "turns": [
        {"speaker": "interviewer", "text": "What colour is the sky on a clear day?"},
        {"speaker": "expert", "text": "Blue, according to the material we have here. " * 20},
        {"speaker": "interviewer", "text": "Thank you."},
    ],
}


@pytest.mark.parametrize("speed", [1.0, 1.5])
def test_every_turn_has_contiguous_times_ending_at_the_files_length(settings, speed):
    out, audio = run(settings, CONVERSATION, {"audio_style": "conversation", "speed": speed})
    assert out["status"] == "ready", out
    transcript = out["content"]["transcript"]
    assert transcript[0]["start"] == 0.0
    for before, after in zip(transcript, transcript[1:], strict=False):
        assert before["end"] == after["start"]  # contiguous
        assert before["end"] > before["start"]
    total = mp3.duration(audio)
    assert transcript[-1]["end"] == pytest.approx(total, abs=0.001)
    # the long answer was cut into several segments: still one entry, its sum
    assert transcript[1]["end"] - transcript[1]["start"] > 10 * FRAME_S


def test_faster_speech_gives_shorter_measured_times(settings):
    slow, _ = run(settings, CONVERSATION, {"audio_style": "conversation", "speed": 1.0})
    fast, _ = run(settings, CONVERSATION, {"audio_style": "conversation", "speed": 1.5})
    assert fast["content"]["transcript"][-1]["end"] < slow["content"]["transcript"][-1]["end"]


def test_a_segment_that_cannot_be_measured_leaves_the_audio_without_times(settings, caplog):
    store, objects = FakeStore(), FakeObjects()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(
        settings, store, FakeRetriever([]), FakeLLM(json.dumps(CONVERSATION)), FakeTTS(), objects
    )
    output_id = client.post(
        OUTPUTS, json={"kind": "audio", "options": {"audio_style": "conversation"}}, headers=AUTH
    ).json()["id"]
    with caplog.at_level("WARNING"):
        client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert out["status"] == "ready"
    assert all("start" not in t for t in out["content"]["transcript"])
    assert any("could not be measured" in r.getMessage() for r in caplog.records)


def test_the_duration_counts_every_frame_after_an_id3_tag():
    tag = b"ID3\x04\x00\x00\x00\x00\x00\x0a" + bytes(10)
    assert mp3.duration(tag + FRAME * 50) == pytest.approx(50 * FRAME_S)
    assert mp3.duration(FRAME * 3 + b"TAG" + bytes(125)) == pytest.approx(3 * FRAME_S)
    for broken in (b"\xff\xf3It b", FRAME + b"junk!", FRAME[:100]):
        with pytest.raises(mp3.NotMp3):
            mp3.duration(broken)
