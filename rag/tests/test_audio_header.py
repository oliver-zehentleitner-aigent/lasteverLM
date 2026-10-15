"""Joined segments carry one Xing header for the whole stream, so a player
reads the full length and can seek; later segments' headers are dropped."""

import json

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

# MPEG-2 layer III, 64 kbit/s, 24 kHz, mono: 192 bytes, 576 samples (0.024 s)
HEADER = bytes([0xFF, 0xF3, 0x84, 0xC4])
FRAME = HEADER + bytes(188)
FRAME_S = 576 / 24000
XING_AT = 4 + 9  # after the header and a mono MPEG-2 side info


def segment(frames: int, delay: int = 576, padding: int = 300) -> bytes:
    """A segment as the provider sends it: a Xing frame (frames, bytes, a
    seek table, quality and a LAME tag) and its audio frames."""
    total = 192 * (frames + 1)
    tag = bytearray(FRAME)
    pos = XING_AT
    tag[pos : pos + 4] = b"Xing"
    tag[pos + 4 : pos + 8] = (15).to_bytes(4, "big")
    tag[pos + 8 : pos + 12] = frames.to_bytes(4, "big")
    tag[pos + 12 : pos + 16] = total.to_bytes(4, "big")
    tag[pos + 16 : pos + 116] = bytes(range(100))
    lame = pos + 120
    tag[lame : lame + 9] = b"LAME3.100"
    tag[lame + 21 : lame + 24] = bytes(
        [delay >> 4, ((delay & 0x0F) << 4) | (padding >> 8), padding & 0xFF]
    )
    return bytes(tag) + FRAME * frames


def xing(data: bytes) -> dict:
    pos = XING_AT
    lame = pos + 120
    delay_padding = data[lame + 21 : lame + 24]
    return {
        "frames": int.from_bytes(data[pos + 8 : pos + 12], "big"),
        "bytes": int.from_bytes(data[pos + 12 : pos + 16], "big"),
        "toc": data[pos + 16 : pos + 116],
        "delay": (delay_padding[0] << 4) | (delay_padding[1] >> 4),
        "padding": ((delay_padding[1] & 0x0F) << 8) | delay_padding[2],
        "length": int.from_bytes(data[lame + 28 : lame + 32], "big"),
        "crc": int.from_bytes(data[lame + 34 : lame + 36], "big"),
        "crc_of": data[: lame + 34],
    }


def test_joined_segments_have_one_header_for_the_whole_stream():
    parts = [segment(10, delay=576, padding=100), segment(20), segment(5, padding=444)]
    joined = mp3.join(parts)
    frames = mp3.frames(joined)
    assert [mp3.is_header(joined, f) for f in frames].count(True) == 1
    assert mp3.is_header(joined, frames[0])
    header = xing(joined)
    assert header["frames"] == 35 == len(frames) - 1
    assert header["bytes"] == len(joined) == header["length"]
    # the duration the header declares is the duration of the frames
    assert abs(header["frames"] * FRAME_S - mp3.duration(joined)) < 1e-9
    assert abs(mp3.duration(joined) - sum(mp3.duration(p) for p in parts)) < 1e-9
    # the seek table starts after the header and only goes forward
    toc = list(header["toc"])
    assert toc[0] == 192 * 256 // len(joined) and toc == sorted(toc)
    # gapless: the first segment's delay, the last's padding; the tag's checksum holds
    assert (header["delay"], header["padding"]) == (576, 444)
    assert header["crc"] == mp3._crc16(header["crc_of"])


def test_segments_without_a_header_are_joined_as_they_are():
    assert mp3.join([FRAME * 2, FRAME]) == FRAME * 3


class XingTTS(FakeTTS):
    """Segments as the provider sends them: a Xing frame and audio frames."""

    def synthesize(self, text, *, voice=None, speed=None):
        result = super().synthesize(text, voice=voice, speed=speed)
        return type(result)(segment(max(1, len(text) // 5)), result.usage)


def test_an_audio_is_stored_with_one_header_and_its_times_line_up(settings):
    script = {
        "title": "Sky",
        "paragraphs": [
            {"text": "The sky is blue on a clear day.", "refs": [1]},
            {"text": "Grass is green in spring and summer.", "refs": [1]},
        ],
    }
    store, objects = FakeStore(), FakeObjects()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    client = make_client(
        settings,
        store,
        FakeRetriever([]),
        FakeLLM(json.dumps(script)),
        tts=XingTTS(),
        objects=objects,
    )
    output_id = client.post(
        f"/api/rag/notebooks/{NOTEBOOK}/outputs", json={"kind": "audio"}, headers=AUTH
    ).json()["id"]
    client.worker.run_once()
    row = store.outputs[output_id]
    assert row["status"] == "ready", row["error"]
    audio = objects.objects[row["content"]["key"]][0]
    frames = mp3.frames(audio)
    assert [mp3.is_header(audio, f) for f in frames].count(True) == 1
    assert xing(audio)["frames"] == len(frames) - 1
    transcript = row["content"]["transcript"]
    assert transcript[0]["start"] == 0.0
    assert transcript[0]["end"] == transcript[1]["start"]
    assert abs(transcript[-1]["end"] - mp3.duration(audio)) < 0.001


def broken_audio(store: FakeStore, objects: FakeObjects) -> str:
    """An audio as 0.20.2 stored it: two segments concatenated with both
    headers, the times counted with every header frame."""
    a, b = segment(10), segment(20)
    store.notebooks.setdefault(NOTEBOOK, {"id": NOTEBOOK, "owner": "u", "title": "nb"})
    row = store.create_output(NOTEBOOK, "audio", "processing")
    key = f"{NOTEBOOK}/{row.id}/audio.mp3"
    objects.put(key, a + b, "audio/mpeg")
    first_end = round(11 * FRAME_S, 3)  # its header and ten frames
    transcript = [
        {"speaker": "narrator", "text": "One.", "start": 0.0, "end": first_end},
        {"speaker": "narrator", "text": "Two.", "start": first_end, "end": round(32 * FRAME_S, 3)},
    ]
    store.update_output(row.id, status="ready", content={"key": key, "transcript": transcript})
    return row.id


def test_the_repair_is_a_dry_run_by_default_then_fixes_once():
    from lasteverlm_rag.repair_audio import repair_outputs

    store, objects = FakeStore(), FakeObjects()
    output_id = broken_audio(store, objects)
    key = store.outputs[output_id]["content"]["key"]
    before = objects.get(key)
    lines: list[str] = []
    (dry,) = repair_outputs(store, objects, apply=False, say=lines.append)
    assert objects.get(key) == before and not dry.applied
    assert (dry.headers_removed, dry.bytes_before, dry.bytes_after) == (2, 32 * 192, 31 * 192)
    assert lines == [
        f"{output_id}: would repair: 2 header frames removed, 6144 → 5952 bytes, "
        f"{round(30 * FRAME_S, 3)} s, transcript times back by up to {round(2 * FRAME_S, 3)} s"
    ]

    repair_outputs(store, objects, apply=True, say=lines.append)
    fixed = objects.get(key)
    assert xing(fixed)["frames"] == 30 and xing(fixed)["bytes"] == len(fixed)
    transcript = store.outputs[output_id]["content"]["transcript"]
    # the times now count only audio frames: ten, then twenty
    assert [(e["start"], e["end"]) for e in transcript] == [
        (0.0, round(10 * FRAME_S, 3)),
        (round(10 * FRAME_S, 3), round(30 * FRAME_S, 3)),
    ]
    assert transcript[-1]["end"] == round(mp3.duration(fixed), 3)

    # idempotent: a second run changes nothing
    lines.clear()
    assert repair_outputs(store, objects, apply=True, say=lines.append) == []
    assert lines == [f"{output_id}: ok"] and objects.get(key) == fixed
