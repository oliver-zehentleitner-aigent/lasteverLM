"""Pure citation logic: number passages for the prompt, map ``[n]`` markers back to sources.

No I/O here; this is the part covered by unit tests with a mocked LLM.
"""

from __future__ import annotations

import re

from .contracts import Citation
from .models import Passage, RetrievedChunk

QUOTE_MAX_CHARS = 300

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
    """Resolve the markers in ``answer`` against ``passages``.

    Markers that name a passage become citations, in order of first appearance,
    keeping the number the model used so ``n`` and the inline marker agree.
    Markers that name no passage are removed from the text: a number the model
    made up must not reach the reader as if it were a source.
    """
    by_n = {p.n: p for p in passages}
    cleaned = _MARKER_GROUP.sub(lambda m: _rewrite_group(m.group(1), by_n), answer)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    citations = [_to_citation(by_n[n]) for n in extract_markers(cleaned)]
    return cleaned, citations


def _rewrite_group(inner: str, by_n: dict[int, Passage]) -> str:
    kept = [raw.strip() for raw in inner.split(",") if int(raw) in by_n]
    return f"[{', '.join(kept)}]" if kept else ""


def _to_citation(p: Passage) -> Citation:
    return Citation(
        n=p.n,
        source_id=p.source_id,
        source_name=p.source_name,
        source_kind=p.source_kind,
        chunk_id=p.chunk_id,
        page=p.page,
        quote=_quote(p.text),
    )


def _quote(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= QUOTE_MAX_CHARS:
        return text
    cut = text.rfind(" ", 0, QUOTE_MAX_CHARS)
    return text[: cut if cut > 0 else QUOTE_MAX_CHARS].rstrip() + "…"
