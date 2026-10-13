"""Every source of a notebook in a generated document: balanced input and a
cheap check of the output.

A generator's passages used to be one global top-k for its focus query,
which a single source can fill completely; the model then wrote about
that source alone (a mind map of a two-PDF notebook covered one PDF).
``balance`` keeps the best few chunks of every source and fills the rest
by score. ``uncovered_sources`` names the sources whose distinctive name
words the document never mentions; the worker logs them as a warning.
"""

from __future__ import annotations

import re

from .models import RetrievedChunk, SourceSummary

MIN_CHUNKS_PER_SOURCE = 2
# Upper bound for the passages of one generation (about 420 tokens each),
# so a notebook with many sources stays inside the model's context.
MAX_GENERATOR_PASSAGES = 24

_WORD = re.compile(r"[^\W_]+")


def per_source_quota(sources: int, k: int) -> tuple[int, int]:
    """(chunks guaranteed per source, total passages)."""
    if sources == 0:
        return 0, k
    total = min(max(k, MIN_CHUNKS_PER_SOURCE * sources), MAX_GENERATOR_PASSAGES)
    return max(1, min(MIN_CHUNKS_PER_SOURCE, total // sources)), total


def balance(
    per_source: list[list[RetrievedChunk]], ranked: list[RetrievedChunk], total: int
) -> list[RetrievedChunk]:
    """The guaranteed chunks of each source (``per_source``, best first), then
    the best of ``ranked`` not yet taken, up to ``total``; ordered by score.
    If the guaranteed chunks alone exceed ``total``, each source keeps its
    best chunk first, so as many sources as possible stay represented."""
    picked: dict[str, RetrievedChunk] = {}
    depth = max((len(chunks) for chunks in per_source), default=0)
    for level in range(depth):  # round robin: every source's best, then second best
        for chunks in per_source:
            if level < len(chunks) and len(picked) < total:
                picked.setdefault(chunks[level].chunk_id, chunks[level])
    for chunk in ranked:
        if len(picked) >= total:
            break
        picked.setdefault(chunk.chunk_id, chunk)
    return sorted(picked.values(), key=lambda c: c.similarity, reverse=True)


def uncovered_sources(
    text: str, summaries: list[SourceSummary], passages: list[RetrievedChunk]
) -> list[str]:
    """Names of sources that fed the input but whose distinctive name words
    (words of the file name no other source's name has) appear nowhere in
    ``text``. A source without such a word is not checked."""
    in_input = {p.source_id for p in passages} | {s.source_id for s in summaries}
    words = {s.source_id: _name_words(s.name) for s in summaries}
    found = {w.lower() for w in _WORD.findall(text)}
    missing = []
    for s in summaries:
        if s.source_id not in in_input:
            continue
        others = set().union(*(w for sid, w in words.items() if sid != s.source_id))
        distinctive = words[s.source_id] - others
        if distinctive and not distinctive & found:
            missing.append(s.name)
    return missing


def _name_words(name: str) -> set[str]:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return {w.lower() for w in _WORD.findall(stem) if len(w) >= 2 and not w.isdigit()}
