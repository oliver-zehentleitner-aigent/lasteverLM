"""Audio the transcription model does not take, converted to MP3.

The platform's model accepts WAV and MP3 only. Every other recording
(M4A/MP4, AAC, Ogg/Opus, FLAC, WebM/Matroska, the audio track of a
video) is converted by ffmpeg into mono 16 kHz MP3 at 32 kbit/s, which
is what speech recognition needs and keeps four hours near 55 MiB, and
the converted file is what gets transcribed. The original stays in
storage for playback and download. WAV and MP3 pass through untouched.

ffmpeg runs on user-supplied bytes, so it is boxed in: the container
format is forced from the sniffed magic bytes (no probing into playlist
or concat demuxers, which would open other files or URLs), only the
`file` protocol is allowed, the input and output live in a private
temporary directory under /tmp (the only writable path in the pod), and
the run has a time limit.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from lasteverlm_ingest.loaders import LoaderError

Container = Literal["mp4", "aac", "ogg", "flac", "webm"]

# The ffmpeg demuxer for each sniffed container.
_DEMUXER: dict[Container, str] = {
    "mp4": "mov",
    "aac": "aac",
    "ogg": "ogg",
    "flac": "flac",
    "webm": "matroska",
}
# How the original is stored, so the browser can play it where it can.
MEDIA_TYPES: dict[Container, str] = {
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "webm": "audio/webm",
}
# Below the claim timeout, together with the transcription call after it
# (the claim is refreshed in between).
CONVERT_SECONDS = 300

Run = Callable[..., "subprocess.CompletedProcess[bytes]"]


def sniff_container(data: bytes) -> Container | None:
    """A container that needs converting, from the file's first bytes;
    None for anything else (WAV and MP3 included)."""
    if data[4:8] == b"ftyp":
        return "mp4"
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    # ADTS: 12 sync bits, then layer 00 (an MPEG audio frame has a layer).
    if len(data) > 1 and data[0] == 0xFF and data[1] & 0xF6 == 0xF0:
        return "aac"
    return None


def convert_to_mp3(
    data: bytes,
    container: Container,
    *,
    timeout: float = CONVERT_SECONDS,
    run: Run = subprocess.run,
) -> bytes:
    """Mono 16 kHz MP3 at 32 kbit/s from the first audio track; LoaderError
    with ffmpeg's last line of output when it cannot be converted."""
    with tempfile.TemporaryDirectory(prefix="ingest-audio-") as tmp:
        source, target = Path(tmp) / "in", Path(tmp) / "out.mp3"
        source.write_bytes(data)
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-protocol_whitelist",
            "file",
            "-f",
            _DEMUXER[container],
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "32k",
            "-f",
            "mp3",
            str(target),
        ]
        try:
            done = run(command, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise LoaderError(f"the audio could not be converted in {timeout:.0f} s") from None
        except FileNotFoundError:
            raise LoaderError("the audio could not be converted: ffmpeg is not installed") from None
        if done.returncode != 0 or not target.exists():
            lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
            reason = lines[-1].strip() if lines else f"ffmpeg exited with {done.returncode}"
            raise LoaderError(f"the audio could not be converted: {reason}")
        return target.read_bytes()
