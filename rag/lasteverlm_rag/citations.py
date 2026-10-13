"""Pure citation logic: number passages for the prompt, map ``[n]`` markers back to sources.

No I/O here; this is the part covered by unit tests with a mocked LLM.
"""

from __future__ import annotations

import re

from lasteverlm_core import Citation

from .models import Passage, RetrievedChunk

SIMILARITY_DECIMALS = 3

# One bracket group: "[1]", "[1, 2]", "[ 3 ]". Several groups in a row are matched one by one.
_MARKER_GROUP = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")


def number_passages(chunks: list[RetrievedChunk]) -> list[Passage]:
    """Assign 1-based markers in retrieval order."""
    return [
        Passage(
            n=i,
            chunk_id=c.chunk_id,
            source_id=c.source_id,
            source_name=c.source_name,
            source_kind=c.source_kind,
            page=c.page,
            text=c.text,
            similarity=c.similarity,
            chunk_index=c.chunk_index,
            chunk_count=c.chunk_count,
        )
        for i, c in enumerate(chunks, start=1)
    ]


def extract_markers(answer: str) -> list[int]:
    """Marker numbers in order of first appearance, duplicates removed."""
    seen: list[int] = []
    for group in _MARKER_GROUP.finditer(answer):
        for raw in group.group(1).split(","):
            n = int(raw)
            if n not in seen:
                seen.append(n)
    return seen


def map_citations(answer: str, passages: list[Passage]) -> tuple[str, list[Citation]]:
    """Resolve the markers in ``answer`` against ``passages`` and normalize them
    to the contract: one ``[n]`` per citation and ``n`` dense from 1 in order of
    first appearance.

    A grouped marker like ``[1, 3]`` becomes ``[1][2]``; a marker that names no
    passage is removed (a number the model made up must not reach the reader as
    if it were a source) and the remaining ones are renumbered so the text and
    ``citations`` agree without gaps.
    """
    by_n = {p.n: p for p in passages}
    renumber: dict[int, int] = {}
    for old in extract_markers(answer):
        if old in by_n:
            renumber[old] = len(renumber) + 1

    def rewrite(match: re.Match[str]) -> str:
        kept = [renumber[int(raw)] for raw in match.group(1).split(",") if int(raw) in renumber]
        return "".join(f"[{n}]" for n in kept)

    cleaned = _MARKER_GROUP.sub(rewrite, answer)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    citations = [_to_citation(by_n[old], new) for old, new in renumber.items()]
    return cleaned, citations


def _to_citation(p: Passage, n: int) -> Citation:
    """Provenance travels with the citation: the verbatim chunk text (never
    trimmed, so a reader can check the claim against exactly what the model
    saw), the chunk's score for this question and its position in its source."""
    # ids are strings inside this service; the contract model parses them into UUIDs
    return Citation.model_validate(
        {
            "n": n,
            "source_id": p.source_id,
            "source_name": p.source_name,
            "source_kind": p.source_kind,
            "chunk_id": p.chunk_id,
            "page": p.page,
            "quote": p.text,
            "similarity": (
                round(p.similarity, SIMILARITY_DECIMALS) if p.similarity is not None else None
            ),
            "chunk_index": p.chunk_index,
            "chunk_count": p.chunk_count,
        }
    )
