import shutil
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from lasteverlm_core import DEMO_USER_ID, probe_audio

from lasteverlm_ingest import worker
from lasteverlm_ingest.loaders import LoaderError
from lasteverlm_ingest.loaders.convert import convert_to_mp3, sniff_container
from lasteverlm_ingest.worker import TRANSCRIBED_NAME, process_source
from tests.fakes import FakeTranscriber, InMemoryRepository, InMemoryStorage
from tests.test_audio_loader import MP3, WAV, _audio_deps, _url
from tests.test_worker import USER

OGG = b"OggS\x00\x02" + b"\x00" * 64
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64


@pytest.mark.parametrize(
    ("data", "container"),
    [
        (M4A, "mp4"),
        (b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8, "mp4"),
        (OGG, "ogg"),
        (b"fLaC\x00\x00\x00\x22", "flac"),
        (b"\x1a\x45\xdf\xa3\x01\x00", "webm"),
        (b"\xff\xf1\x50\x80\x00", "aac"),
        (MP3, None),  # passes through
        (WAV, None),  # within the cap
        (b"%PDF-1.4", None),
        (b"", None),
    ],
)
def test_sniff_container(data, container):
    assert sniff_container(data) == container


class FakeRun:
    """subprocess.run for ffmpeg: writes the output file, or fails."""

    def __init__(self, output=b"converted", returncode=0, stderr=b"", error=None):
        self.output, self.returncode, self.stderr, self.error = output, returncode, stderr, error
        self.commands: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        assert kwargs["timeout"] > 0 and kwargs["check"] is False
        if self.error is not None:
            raise self.error
        if self.returncode == 0:
            Path(command[-1]).write_bytes(self.output)
        return subprocess.CompletedProcess(command, self.returncode, b"", self.stderr)


def test_ffmpeg_is_boxed_in_and_returns_the_mp3():
    run = FakeRun()
    assert convert_to_mp3(M4A, "mp4", run=run) == b"converted"
    [command] = run.commands
    joined = " ".join(command)
    # The demuxer is forced from the sniffed bytes, only files are opened.
    assert "-protocol_whitelist file -f mov -i" in joined
    assert "-map 0:a:0 -vn -sn -dn -ac 1 -ar 16000 -c:a libmp3lame -b:a 32k -f mp3" in joined
    assert command[0] == "ffmpeg" and "-nostdin" in command
    # Input and output lived in a private directory that is gone now.
    assert not Path(command[command.index("-i") + 1]).exists()


def test_a_conversion_error_names_ffmpegs_last_line():
    run = FakeRun(
        returncode=1, stderr=b"first\n[mov] moov atom not found\nStream map matches no streams.\n"
    )
    with pytest.raises(LoaderError, match=r"converted: Stream map matches no streams\.$"):
        convert_to_mp3(M4A, "mp4", run=run)
    with pytest.raises(LoaderError, match="ffmpeg exited with 1"):
        convert_to_mp3(M4A, "mp4", run=FakeRun(returncode=1))
    timeout = subprocess.TimeoutExpired("ffmpeg", 300)
    with pytest.raises(LoaderError, match="could not be converted in 300 s"):
        convert_to_mp3(M4A, "mp4", run=FakeRun(error=timeout))
    with pytest.raises(LoaderError, match="ffmpeg is not installed"):
        convert_to_mp3(M4A, "mp4", run=FakeRun(error=FileNotFoundError()))


def _add(repo, storage, data):
    nb = repo.create_notebook(USER, "nb")
    sid = repo.add_source(nb.id, "talk.m4a", "audio", f"{USER}/orig/talk.m4a").library_id
    storage.put(f"{USER}/orig/talk.m4a", data, "audio/mp4")
    return sid


def test_the_worker_converts_stores_and_transcribes_the_mp3(monkeypatch):
    repo, storage, transcriber = InMemoryRepository(), InMemoryStorage(), FakeTranscriber()
    calls = []
    monkeypatch.setattr(worker, "convert_to_mp3", lambda data, c: calls.append(c) or MP3)
    sid = _add(repo, storage, M4A)
    process_source(sid, _audio_deps(repo, storage, transcriber))
    lib = repo.library[sid]
    assert lib.status == "ready" and calls == ["mp4"]
    key = f"{USER}/{sid}/{TRANSCRIBED_NAME}"
    assert lib.transcribed_path == key
    assert storage.objects[key] == MP3 and storage.types[key] == "audio/mpeg"
    assert storage.objects[f"{USER}/orig/talk.m4a"] == M4A  # the original stays
    assert transcriber.calls == [(MP3, "audio.mp3")]
    # Converting, transcribing and embedding each moved the claim.
    assert repo.refreshed == [sid, sid, sid]


def test_a_retry_reuses_the_stored_conversion(monkeypatch):
    repo, storage = InMemoryRepository(), InMemoryStorage()
    calls = []
    monkeypatch.setattr(worker, "convert_to_mp3", lambda data, c: calls.append(c) or MP3)
    sid = _add(repo, storage, OGG)
    from lasteverlm_core import ProviderError

    process_source(sid, _audio_deps(repo, storage, FakeTranscriber(error=ProviderError("503"))))
    assert repo.library[sid].status == "processing" and calls == ["ogg"]
    process_source(sid, _audio_deps(repo, storage, FakeTranscriber()))
    assert repo.library[sid].status == "ready" and calls == ["ogg"]


def test_the_caps_apply_to_the_converted_file(monkeypatch):
    repo, storage = InMemoryRepository(), InMemoryStorage()
    monkeypatch.setattr(worker, "convert_to_mp3", lambda data, c: b"\x00" * 64)
    sid = _add(repo, storage, OGG)
    transcriber = FakeTranscriber()
    process_source(sid, _audio_deps(repo, storage, transcriber))
    lib = repo.library[sid]
    assert lib.status == "failed" and "only those can be transcribed" in (lib.error or "")
    assert transcriber.calls == [] and repo.usage == []


def test_a_conversion_failure_fails_the_source_at_once(monkeypatch):
    repo, storage = InMemoryRepository(), InMemoryStorage()

    def broken(data, container):
        raise LoaderError("the audio could not be converted: Invalid data found")

    monkeypatch.setattr(worker, "convert_to_mp3", broken)
    sid = _add(repo, storage, M4A)
    process_source(sid, _audio_deps(repo, storage, FakeTranscriber()))
    lib = repo.library[sid]
    assert (
        lib.status == "failed"
        and lib.error == "the audio could not be converted: Invalid data found"
    )


@pytest.mark.parametrize(
    ("name", "data", "media_type", "stored"),
    [
        ("talk.m4a", M4A, "audio/mp4", "audio/mp4"),
        ("talk.ogg", OGG, "application/octet-stream", "audio/ogg"),
        ("clip", b"\x1a\x45\xdf\xa3\x01" + b"\x00" * 32, "video/webm", "audio/webm"),
        ("talk.flac", b"fLaC" + b"\x00" * 32, "audio/flac", "audio/flac"),
    ],
)
def test_other_formats_are_accepted_and_stored_by_their_bytes(
    client, storage, name, data, media_type, stored
):
    r = client.post(_url(client), files={"file": (name, data, media_type)})
    assert r.status_code == 202 and r.json()["kind"] == "audio"
    key = f"{DEMO_USER_ID}/{r.json()['library_id']}/{name}"
    assert storage.types[key] == stored
    # Nothing converted yet: the original is what opens, no separate download.
    assert r.json()["preview_url"].startswith(f"https://storage.test/{key}?")
    assert r.json()["original_url"] is None


def test_a_converted_source_plays_the_mp3_and_offers_the_original(client, repo, storage):
    url = _url(client)
    r = client.post(url, files={"file": ("Vortrag.m4a", M4A, "audio/mp4")})
    lib = UUID(r.json()["library_id"])
    converted = f"{DEMO_USER_ID}/{lib}/{TRANSCRIBED_NAME}"
    storage.put(converted, MP3, "audio/mpeg")
    repo.set_transcribed_path(lib, converted)
    original = f"{DEMO_USER_ID}/{lib}/Vortrag.m4a"
    expected = (
        f"https://storage.test/{converted}?expires=3600",
        f"https://storage.test/{original}?expires=3600&download=Vortrag.m4a",
    )
    [listed] = client.get(url).json()
    assert (listed["preview_url"], listed["original_url"]) == expected
    entry = client.get(f"/api/ingest/library/{lib}").json()
    assert (entry["preview_url"], entry["original_url"]) == expected
    # The trash purge removes both objects.
    client.delete(f"/api/ingest/library/{lib}")
    [trashed] = client.get("/api/ingest/library/trash").json()
    assert (trashed["preview_url"], trashed["original_url"]) == expected
    assert client.delete(f"/api/ingest/library/{lib}/purge").status_code == 204
    assert converted not in storage.objects and original not in storage.objects


def test_purge_expired_returns_both_keys():
    from datetime import UTC, datetime, timedelta

    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = _add(repo, storage, M4A)
    repo.set_transcribed_path(sid, "converted-key")
    repo.trash_library_source(USER, sid)
    repo.trash_days[USER] = 0
    repo.library[sid] = repo.library[sid].model_copy(
        update={"deleted_at": datetime.now(UTC) - timedelta(minutes=1)}
    )
    assert sorted(repo.purge_expired()) == sorted([f"{USER}/orig/talk.m4a", "converted-key"])


FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg (the ingest image has it)")
@pytest.mark.parametrize(
    ("name", "container"),
    [
        ("tone.ogg", "ogg"),  # Vorbis
        ("tone.opus", "ogg"),
        ("tone.flac", "flac"),
        ("tone.m4a", "mp4"),  # AAC
        ("tone.aac", "aac"),  # ADTS
        ("tone.webm", "webm"),  # Opus
        ("clip.mp4", "mp4"),  # a video: its audio track
    ],
)
def test_the_images_ffmpeg_converts_every_format_to_a_file_core_accepts(name, container):
    """Two-second 440 Hz tones, made once with a full ffmpeg; this runs
    against the minimal one the image builds."""
    data = (FIXTURES / name).read_bytes()
    assert sniff_container(data) == container
    info = probe_audio(convert_to_mp3(data, container))
    assert info.format == "mp3" and 1.8 < info.seconds < 2.3


def test_a_wav_over_the_cap_is_converted_one_within_it_passes(monkeypatch):
    from lasteverlm_ingest.loaders import convert

    monkeypatch.setattr(convert, "MAX_AUDIO_BYTES", len(WAV) - 1)
    assert sniff_container(WAV) == "wav"
    monkeypatch.setattr(convert, "MAX_AUDIO_BYTES", len(WAV))
    assert sniff_container(WAV) is None


def test_the_worker_converts_a_wav_over_the_cap_and_keeps_it(monkeypatch):
    from lasteverlm_ingest.loaders import convert

    monkeypatch.setattr(convert, "MAX_AUDIO_BYTES", len(WAV) - 1)
    repo, storage, transcriber = InMemoryRepository(), InMemoryStorage(), FakeTranscriber()
    calls = []
    monkeypatch.setattr(worker, "convert_to_mp3", lambda data, c: calls.append(c) or MP3)
    sid = _add(repo, storage, WAV)
    process_source(sid, _audio_deps(repo, storage, transcriber))
    assert repo.library[sid].status == "ready" and calls == ["wav"]
    assert transcriber.calls == [(MP3, "audio.mp3")]
    assert storage.objects[f"{USER}/orig/talk.m4a"] == WAV  # the original stays


def test_a_wav_over_the_cap_is_accepted_at_upload(client, storage, monkeypatch):
    from lasteverlm_ingest.loaders import convert

    monkeypatch.setattr(convert, "MAX_AUDIO_BYTES", len(WAV) - 1)
    r = client.post(_url(client), files={"file": ("long.wav", WAV, "audio/wav")})
    assert r.status_code == 202 and r.json()["kind"] == "audio"
    assert storage.types[f"{DEMO_USER_ID}/{r.json()['library_id']}/long.wav"] == "audio/wav"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg (the ingest image has it)")
@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
def test_the_images_ffmpeg_converts_a_wav(sample_width):
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(sample_width)
        w.setframerate(44100)
        w.writeframes(b"\x10" * sample_width * 2 * 44100 * 2)
    info = probe_audio(convert_to_mp3(buffer.getvalue(), "wav"))
    assert info.format == "mp3" and 1.8 < info.seconds < 2.3
