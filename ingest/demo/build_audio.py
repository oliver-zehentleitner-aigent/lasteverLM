"""Builds the demo recording from its script, once, with the platform's TTS.

    INFERENCE_BASE_URL=... INFERENCE_API_KEY=... TTS_MODEL=... \
        .venv/bin/python demo/build_audio.py /path/to/ffmpeg-capable-dir

Reads `hollin-interview.txt` (one line per turn, `voice: text`), has
the platform's speech model say each turn in its voice and writes the
turns, joined, to `src/lasteverlm_ingest/demo/hollin-interview.mp3`.
Unlike `build.py` this is not deterministic (the model's speech varies
from call to call) and it costs a few cents, so the MP3 is committed and
this runs only when the script changes. The turns are joined and
re-encoded to mono 64 kbit/s by ffmpeg (`ffmpeg` on the path), which
keeps the file under 1 MB.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

DEMO = Path(__file__).resolve().parents[1] / "src" / "lasteverlm_ingest" / "demo"
SCRIPT = DEMO / "hollin-interview.txt"
OUT = DEMO / "hollin-interview.mp3"


def main() -> None:
    client = OpenAI(
        base_url=os.environ.get("INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"),
        api_key=os.environ["INFERENCE_API_KEY"],
        timeout=120,
    )
    model = os.environ["TTS_MODEL"]
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for n, line in enumerate(SCRIPT.read_text().splitlines()):
            if not line.strip():
                continue
            voice, text = (p.strip() for p in line.split(":", 1))
            audio = client.audio.speech.create(model=model, voice=voice, input=text)
            part = Path(tmp) / f"{n:02d}.mp3"
            part.write_bytes(audio.content)
            parts.append(part)
        listing = Path(tmp) / "parts.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                "-map_metadata",
                "-1",
                str(OUT),
            ],
            check=True,
        )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
