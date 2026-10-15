"""Repair stored audio whose segments were joined with every segment's Xing
header (outputs made from 0.20.2 until the join was fixed): one header for
the whole stream, the transcript times moved back by the header frames
that go. A dry run by default; it lists what it would change.

    lasteverlm-rag-repair-audio                # dry run, every audio output
    lasteverlm-rag-repair-audio --output ID    # only these (repeatable)
    lasteverlm-rag-repair-audio --apply        # write the objects and rows

Idempotent: a file that is already right is left alone. Needs DATABASE_URL
and the S3_* settings. Never run it against production without the
maintainer's go.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lasteverlm_core import S3Settings, S3Storage, Storage

from . import mp3
from .store import PostgresStore, Store, make_pool


@dataclass(frozen=True)
class Repair:
    output_id: str
    key: str
    headers_removed: int
    bytes_before: int
    bytes_after: int
    seconds_after: float
    largest_shift: float  # seconds a transcript time moves back, at most
    applied: bool


def repair_outputs(
    store: Store,
    objects: Storage,
    apply: bool,
    output_ids: list[str] | None = None,
    say: Callable[[str], None] = print,
) -> list[Repair]:
    """Check every stored audio (or ``output_ids``) and, with ``apply``,
    rewrite those that need it: the object first, then the row's times."""
    done = []
    for row in store.audio_outputs(output_ids):
        content: dict[str, Any] = row.content or {}
        key = content.get("key")
        if not isinstance(key, str):
            continue
        try:
            fixed = mp3.repair(objects.get(key))
        except mp3.NotMp3 as exc:
            say(f"{row.id}: skipped, not readable as MP3: {exc}")
            continue
        if fixed is None:
            say(f"{row.id}: ok")
            continue
        data, removed = fixed
        before = len(objects.get(key))
        transcript = content.get("transcript") or []
        timed = [e for e in transcript if "start" in e and "end" in e]
        new_transcript = [
            (
                {
                    **e,
                    "start": mp3.shifted(e["start"], removed),
                    "end": mp3.shifted(e["end"], removed),
                }
                if e in timed
                else e
            )
            for e in transcript
        ]
        moved = [
            old["end"] - new["end"]
            for old, new in zip(transcript, new_transcript, strict=True)
            if old in timed
        ]
        repair = Repair(
            row.id,
            key,
            len(removed),
            before,
            len(data),
            round(mp3.duration(data), 3),
            round(max(moved, default=0.0), 3),
            apply,
        )
        say(
            f"{row.id}: {'repaired' if apply else 'would repair'}: "
            f"{repair.headers_removed} header frames removed, "
            f"{repair.bytes_before} → {repair.bytes_after} bytes, "
            f"{repair.seconds_after} s, transcript times back by up to {repair.largest_shift} s"
        )
        if apply:
            objects.put(key, data, "audio/mpeg")
            store.update_output(row.id, content={**content, "transcript": new_transcript})
        done.append(repair)
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write; without it, a dry run")
    parser.add_argument("--output", action="append", help="an output id (repeatable)")
    args = parser.parse_args()
    pool = make_pool(os.environ["DATABASE_URL"])
    try:
        store = PostgresStore(pool, {})
        found = repair_outputs(store, S3Storage(S3Settings.from_env()), args.apply, args.output)
        verb = "repaired" if args.apply else "would repair (dry run; --apply to write)"
        print(f"{len(found)} audio outputs {verb}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
