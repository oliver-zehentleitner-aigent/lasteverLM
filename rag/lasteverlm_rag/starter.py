"""Copying a starter notebook's outputs into a new user's copy of it.

Ingest copies the starter's uploads and hands rag the id maps (old link and
library ids to new, old chunk ids to new) in an ``output_copies`` row. rag
copies the ready outputs: the content as it is (an audio file under a new
key), the options and the provenance log with every id that points into
the starter rewritten to the copy's. An id that cannot be mapped is never
left pointing at the maintainer's rows: an option or a retrieval candidate
goes, a cited passage stays with its quote and no chunk (its source is not
in the copy), so every citation still resolves to a passage. Share tokens are not
copied; judge annotations and the support check are kept, as they hold for
the same text and passages.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_COPY_ATTEMPTS = 3


@dataclass(frozen=True)
class OutputCopy:
    """One claimed ``output_copies`` row."""

    target_notebook: str
    source_notebook: str
    owner: str
    source_map: Mapping[str, str]
    chunk_map: Mapping[str, str]
    attempts: int


def remap_options(options: Mapping[str, Any], copy_: OutputCopy) -> dict[str, Any]:
    """The options with the source selection and a chart's cited chunks
    rewritten; unmapped ones dropped."""
    out = copy.deepcopy(dict(options))
    if "sources" in out:
        mapped = [copy_.source_map[s] for s in out["sources"] if s in copy_.source_map]
        if mapped:
            out["sources"] = mapped
        else:
            del out["sources"]
    # the candidates a chart, table or infographic was made from
    for key in ("charts", "tables", "themes"):
        for candidate in out.get(key, []):
            candidate["passages"] = [
                {**p, "chunk_id": copy_.chunk_map[p["chunk_id"]]}
                for p in candidate.get("passages", [])
                if p.get("chunk_id") in copy_.chunk_map
            ]
            if "sources" in candidate:
                candidate["sources"] = [
                    {**s, "source_id": copy_.source_map[s["source_id"]]}
                    for s in candidate["sources"]
                    if s.get("source_id") in copy_.source_map
                ]
    return out


def remap_provenance(
    provenance: Mapping[str, Any] | None, copy_: OutputCopy
) -> dict[str, Any] | None:
    """The log with its passages', candidates' and coverage's chunk and
    source ids rewritten. A cited passage whose chunk cannot be mapped is
    kept without one (its quote is the citation); a retrieval candidate is
    dropped."""
    if provenance is None:
        return None
    out = copy.deepcopy(dict(provenance))

    def mapped(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept = []
        for entry in entries:
            chunk = copy_.chunk_map.get(entry.get("chunk_id", ""))
            if chunk is None:
                continue
            source = copy_.source_map.get(entry.get("source_id", ""))
            kept.append({**entry, "chunk_id": chunk, "source_id": source})
        return kept

    if "passages" in out:
        out["passages"] = [
            {
                **entry,
                "chunk_id": copy_.chunk_map.get(entry.get("chunk_id", "")),
                "source_id": copy_.source_map.get(entry.get("source_id", "")),
            }
            for entry in out["passages"]
        ]
    coverage = out.get("coverage")
    if isinstance(coverage, dict):
        for source in coverage.get("sources", []):
            source["source_id"] = copy_.source_map.get(source.get("source_id", ""))
    retrieval = out.get("retrieval")
    if isinstance(retrieval, dict) and "candidates" in retrieval:
        retrieval["candidates"] = mapped(retrieval["candidates"])
    if "options" in out:
        out["options"] = remap_options(out["options"], copy_)
    return out
