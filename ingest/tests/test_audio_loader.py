import io
import wave

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, AudioError, ProviderError, Usage

from lasteverlm_ingest.loaders import LoaderError, default_registry
from lasteverlm_ingest.loaders.audio import AudioLoader
from lasteverlm_ingest.worker import process_source
from tests.conftest import make_settings
from tests.fakes import FakeEmbedder, FakeTranscriber, InMemoryRepository, InMemoryStorage
from tests.test_worker import USER, deps


def _wav(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buffer.getvalue()


# MPEG-1 Layer III, 128 kbit/s, 44.1 kHz: 417-byte frames of 1152 samples.
MP3 = (b"\xff\xfb\x90\x64" + b"\x00" * 413) * 40
WAV = _wav()
SILENT_STT = ProviderError(
    "speech-to-text model fake-stt recognised no speech", Usage("stt", "fake-stt", 5, 0)
)


def test_a_recording_becomes_one_passage_and_its_usage():
    transcriber, billed = FakeTranscriber(), []
    passages = AudioLoader(transcriber).load_billed(WAV, billed.append)
    assert [(p.text, p.page) for p in passages] == [("Hallo und willkommen zur Sendung.", None)]
    assert transcriber.calls == [(WAV, "audio.wav")]
    [usage] = billed
    assert (usage.kind, usage.model, usage.tokens_in) == ("stt", "fake-stt", 90)
    AudioLoader(transcriber).load_billed(MP3, billed.append)
    assert transcriber.calls[-1] == (MP3, "audio.mp3")


def test_audio_failures_are_classified():
    billed: list = []
    # Core's probe refuses it before any call; final, nothing billed.
    with pytest.raises(LoaderError, match="only WAV and MP3"):
        AudioLoader(FakeTranscriber()).load_billed(b"OggS" + b"\x00" * 64, billed.append)
    refused = AudioError("the audio is 20000 seconds long")
    with pytest.raises(LoaderError, match="20000 seconds"):
        AudioLoader(FakeTranscriber(error=refused)).load_billed(MP3, billed.append)
    # No usable answer: the worker decides (retry, or fail when permanent).
    with pytest.raises(ProviderError):
        AudioLoader(FakeTranscriber(error=ProviderError("down"))).load_billed(MP3, billed.append)
    assert billed == []
    # The platform answered and billed, the answer is unusable: billed, final.
    with pytest.raises(LoaderError, match="recognised no speech"):
        AudioLoader(FakeTranscriber(error=SILENT_STT)).load_billed(MP3, billed.append)
    assert [(u.kind, u.tokens_in) for u in billed] == [("stt", 5)]


def test_no_transcriber_means_no_audio_kind():
    assert "audio" not in default_registry().kinds
    assert "audio" in default_registry(transcriber=FakeTranscriber()).kinds


def _audio_deps(repo, storage, transcriber):
    d = deps(repo, storage, FakeEmbedder(8))
    loaders = default_registry(transcriber=transcriber)
    return d.__class__(**{**d.__dict__, "loaders": loaders})


def _add_audio(repo, storage):
    nb = repo.create_notebook(USER, "nb")
    sid = repo.add_source(nb.id, "talk.mp3", "audio", "rec").library_id
    storage.put("rec", MP3, "audio/mpeg")
    return sid


def test_worker_bills_the_transcription_then_embeds_and_summarizes():
    repo, storage, transcriber = InMemoryRepository(), InMemoryStorage(), FakeTranscriber()
    sid = _add_audio(repo, storage)
    process_source(sid, _audio_deps(repo, storage, transcriber))
    assert repo.library[sid].status == "ready"
    assert [(u.kind, u.model) for u in repo.usage][0] == ("stt", "fake-stt")
    assert [u.kind for u in repo.usage] == ["stt", "embedding", "llm"]
    assert repo.refreshed == [sid, sid]  # the transcription, one embedding batch


def test_no_credit_means_no_transcription():
    repo, storage, transcriber = InMemoryRepository(), InMemoryStorage(), FakeTranscriber()
    repo.default_balance = 0
    sid = _add_audio(repo, storage)
    process_source(sid, _audio_deps(repo, storage, transcriber))
    source = repo.library[sid]
    assert source.status == "failed" and source.error == "credit exhausted"
    assert transcriber.calls == [] and repo.usage == []


def test_silence_fails_at_once_and_its_call_is_billed():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = _add_audio(repo, storage)
    process_source(sid, _audio_deps(repo, storage, FakeTranscriber(error=SILENT_STT)))
    source = repo.library[sid]
    assert source.status == "failed" and source.error == str(SILENT_STT)
    assert [u.kind for u in repo.usage] == ["stt"]


def test_a_permanent_provider_refusal_fails_at_once_a_transient_one_retries():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = _add_audio(repo, storage)
    refused = ProviderError("transcription request failed: 413", permanent=True)
    process_source(sid, _audio_deps(repo, storage, FakeTranscriber(error=refused)))
    assert repo.library[sid].status == "failed"
    assert repo.library[sid].error == "transcription request failed: 413"

    sid = _add_audio(repo, storage)
    process_source(sid, _audio_deps(repo, storage, FakeTranscriber(error=ProviderError("503"))))
    assert repo.library[sid].status == "processing" and repo.library[sid].error == "503"


def _url(client) -> str:
    nb = client.post("/api/ingest/notebooks", json={"title": "audio"}).json()["id"]
    return f"/api/ingest/notebooks/{nb}/sources"


def test_audio_upload_is_stored_by_its_detected_type_and_deduplicated(client, storage):
    url = _url(client)
    r = client.post(url, files={"file": ("Talk 1.MP3", MP3, "application/octet-stream")})
    assert r.status_code == 202 and r.json()["kind"] == "audio"
    key = f"{DEMO_USER_ID}/{r.json()['library_id']}/Talk_1.MP3"
    assert storage.objects[key] == MP3 and storage.types[key] == "audio/mpeg"
    # The browser plays the stored original.
    assert r.json()["preview_url"] == f"https://storage.test/{key}?expires=3600"
    r2 = client.post(url, files={"file": ("again.mp3", MP3, "audio/mpeg")})
    assert r2.status_code == 200 and r2.json()["library_id"] == r.json()["library_id"]
    r = client.post(url, files={"file": ("rec", WAV, "audio/x-wav")})
    assert r.status_code == 202 and r.json()["kind"] == "audio"
    key = f"{DEMO_USER_ID}/{r.json()['library_id']}/rec"
    assert storage.types[key] == "audio/wav"


def test_audio_upload_is_probed(client):
    url = _url(client)
    r = client.post(url, files={"file": ("fake.mp3", b"<html>" * 10, "audio/mpeg")})
    assert r.status_code == 415 and "only those can be transcribed" in r.json()["error"]
    assert "(accepted: MP3, WAV, M4A/MP4" in r.json()["error"]
    r = client.post(url, files={"file": ("silent.wav", _wav(0), "audio/wav")})
    assert r.status_code == 415 and r.json()["error"].startswith("the audio file contains no audio")


def test_audio_has_its_own_upload_cap(repo, storage, embedder, summarizer):
    from lasteverlm_core import MemoryRateLimitStore

    from lasteverlm_ingest.main import create_app
    from tests.conftest import DEMO_TOKEN

    app = create_app(
        make_settings(MAX_UPLOAD_BYTES="100", MAX_AUDIO_UPLOAD_BYTES=str(len(WAV) + 50)),
        rate_limit_store=MemoryRateLimitStore(),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
        loaders=default_registry(transcriber=FakeTranscriber()),
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        url = _url(client)
        # Over MAX_UPLOAD_BYTES, within MAX_AUDIO_UPLOAD_BYTES.
        assert client.post(url, files={"file": ("a.wav", WAV, "audio/wav")}).status_code == 202
        r = client.post(url, files={"file": ("b.wav", WAV + b"\x00" * 51, "audio/wav")})
        assert r.status_code == 413


def test_without_a_transcriber_audio_is_refused(repo, storage, embedder, summarizer):
    from lasteverlm_core import MemoryRateLimitStore

    from lasteverlm_ingest.main import create_app
    from tests.conftest import DEMO_TOKEN

    app = create_app(
        make_settings(),
        rate_limit_store=MemoryRateLimitStore(),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
        loaders=default_registry(),
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        r = client.post(_url(client), files={"file": ("a.mp3", MP3, "audio/mpeg")})
        assert r.status_code == 415
