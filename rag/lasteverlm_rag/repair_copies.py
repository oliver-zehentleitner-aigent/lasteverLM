"""Repair starter copies whose citations lead nowhere: a copy made before the
copy kept unmappable passages lost a cited passage whose chunk belonged to
a source no longer linked to the starter (its value still showed as
supported, its citation opened nothing), and a copied table or
infographic kept the starter's source ids in its options and coverage.

For every copied output, ids are mapped again by what the copy shares with
the original: a source by its name in the copy's notebook, a chunk by its
position in that source. A cited passage missing from the copy is restored
from the original, mapped where it can be and otherwise kept with its quote
and no chunk; option and coverage source ids are mapped or dropped. No
model call. A dry run by default; it lists each copy it would change.

    lasteverlm-rag-repair-copies            # dry run
    lasteverlm-rag-repair-copies --apply    # write the rows

Idempotent. Needs DATABASE_URL. Never run it against production without
the maintainer's go.
"""

from __future__ import annotations

import argparse
import copy
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .store import PostgresStore, Store, make_pool


@dataclass(frozen=True)
class CopyFix:
    output_id: str
    passages_restored: int
    ids_remapped: int
    applied: bool


def _source_map(names: dict[str, str], starter: dict[str, str]) -> Callable[[Any], str | None]:
    """A starter source id as the copy's (by its name), or None; an id that
    is the copy's already stays."""
    known = set(names.values())

    def source(old: Any) -> str | None:
        if old in known:
            return str(old)
        return names.get(starter.get(str(old), ""))

    return source


def repair_copies(store: Store, apply: bool, say: Callable[[str], None] = print) -> list[CopyFix]:
    done = []
    for copy_id, original_id in store.starter_copies():
        row, original = store.get_output(copy_id), store.get_output(original_id)
        if row is None or original is None or row.notebook_id is None:
            continue
        if original.notebook_id is None:
            continue
        names = {s.name: s.source_id for s in store.source_states(row.notebook_id)}
        starter = {s.source_id: s.name for s in store.source_states(original.notebook_id)}
        source = _source_map(names, starter)

        provenance = copy.deepcopy(dict(row.provenance or {}))
        options = copy.deepcopy(dict(row.options or {}))
        have = {p["n"] for p in provenance.get("passages") or []}
        restored = []
        for entry in (original.provenance or {}).get("passages") or []:
            if entry["n"] in have:
                continue
            new_source = names.get(str(entry.get("source_name", "")))
            chunk = None
            if new_source is not None and entry.get("chunk_index") is not None:
                chunk = store.chunk_ids_at(new_source, [int(entry["chunk_index"])]).get(
                    int(entry["chunk_index"])
                )
            restored.append({**entry, "source_id": new_source, "chunk_id": chunk})
        remapped = 0
        for key in ("tables", "themes"):
            for candidate in options.get(key, []):
                kept = []
                for s in candidate.get("sources", []):
                    new = source(s.get("source_id"))
                    if new != s.get("source_id"):
                        remapped += 1
                    if new is not None:
                        kept.append({**s, "source_id": new})
                candidate["sources"] = kept
        coverage = provenance.get("coverage")
        if isinstance(coverage, dict):
            for s in coverage.get("sources", []):
                new = source(s.get("source_id"))
                if new != s.get("source_id"):
                    remapped += 1
                    s["source_id"] = new
        if not restored and not remapped:
            continue
        fix = CopyFix(row.id, len(restored), remapped, apply)
        say(
            f"{row.id}: {'repaired' if apply else 'would repair'}: "
            f"{fix.passages_restored} passages restored, {fix.ids_remapped} source ids mapped"
        )
        if apply:
            provenance["passages"] = sorted(
                [*(provenance.get("passages") or []), *restored], key=lambda p: p["n"]
            )
            store.update_output(row.id, provenance=provenance, options=options)
        done.append(fix)
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write; without it, a dry run")
    args = parser.parse_args()
    pool = make_pool(os.environ["DATABASE_URL"])
    try:
        found = repair_copies(PostgresStore(pool, {}), args.apply)
        verb = "repaired" if args.apply else "would be repaired (dry run; --apply to write)"
        print(f"{len(found)} starter copies {verb}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
