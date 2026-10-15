"""Pure citation logic: number passages for the prompt, map ``[n]`` markers back to sources,
and keep marker-shaped text of the user's files out of prompts.

No I/O here; this is the part covered by unit tests with a mocked LLM.
"""

from __future__ import annotations

import re

from lasteverlm_core import Citation

from .models import Passage, RetrievedChunk

SIMILARITY_DECIMALS = 3

# One bracket group: "[1]", "[1, 2]", "[ 3 ]". Several groups in a row are matched one by one.
MARKER_GROUP = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")
# A name (file, document, notebook) in a prompt is one line of bounded length.
NAME_MAX_CHARS = 120


def strip_markers(text: str) -> str:
    """Remove every marker group, with the space before it."""
    return re.sub(r"\s*" + MARKER_GROUP.pattern, "", text)


def defuse_markers(text: str) -> str:
    """Rewrite marker-shaped text ("[2]", "[1, 3]") as "(2)", "(1, 3)": text
    from a source cannot then pass for a citation of another passage."""
    return MARKER_GROUP.sub(lambda m: f"({m.group(1)})", text)


def inline(name: str, limit: int = NAME_MAX_CHARS) -> str:
    """A name from the user's files as it goes into a prompt or a log line:
    one line (no newline can start a fake rule or passage), markers defused,
    cut to ``limit`` characters."""
    flat = " ".join(defuse_markers(name).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


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


def keep_markers(text: str, valid: set[int]) -> str:
    """Drop the numbers no passage has from every marker group; a group left
    empty goes with the space before it."""

    def rewrite(match: re.Match[str]) -> str:
        kept = [raw.strip() for raw in match.group(2).split(",") if int(raw) in valid]
        return f"{match.group(1)}[{', '.join(kept)}]" if kept else ""

    return re.sub(r"(\s*)" + MARKER_GROUP.pattern, rewrite, text)


def extract_markers(answer: str) -> list[int]:
    """Marker numbers in order of first appearance, duplicates removed."""
    seen: list[int] = []
    for group in MARKER_GROUP.finditer(answer):
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

    cleaned = MARKER_GROUP.sub(rewrite, answer)
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


# -- support of a generated unit by the passages it cites ---------------------

# The check that a unit of a generated output (a paragraph, a fact, a turn)
# says what its cited passages say: deterministic, no model call. A unit's
# content words are compared with the words of all its cited chunks taken
# together; the unit is supported when at least ``OVERLAP_THRESHOLD`` of its
# words occur there. Words are lowercased letters and digits, at least three
# characters or containing a digit, without the commonest English and German
# function words, and cut to their first ``WORD_PREFIX`` characters so that
# "cloud" and "clouds" match. The threshold is set, not calibrated on rated
# outputs (see rag/context/citations.md).
# v2: the word check plus the negation check (negation.py)
CHECK_METHOD = "lexical-overlap-v2"
OVERLAP_THRESHOLD = 0.5
WORD_PREFIX = 5
_WORD = re.compile(r"\w+")
_STOPWORDS = frozenset("""
    the and for are but not you all any can had has her was one our out his how its may new
    now old see two way who did get him let say she too use that with have this will your from
    they been were said each which their there what about would make like into than them then
    these some could other more very after also only over such most even when where while
    being does both because through under again those should just
    der die das und ist ein eine einer eines einem einen den dem des sich mit auf für von
    nicht auch als wie bei aus nach oder wird sind war hat zum zur noch nur über unter durch
    wenn dann dass sein seine ihre ihr wir sie ihm ihn uns kann können werden wurde wurden
    haben hatte diese dieser dieses diesem diesen einem einer vom beim
    """.split())


# A few words frequent in one of the two languages and absent from the other,
# enough to tell an English text from a German one; anything else is unknown.
_ENGLISH = frozenset("the and is are was were this that with which of to in it".split())
_GERMAN = frozenset("der die das und ist sind war nicht mit ein eine zu im den dem".split())


def language_of(text: str) -> str | None:
    """``en``, ``de`` or ``None`` when the text says too little to tell:
    one language's marker words must outnumber the other's twice."""
    words = _WORD.findall(text.lower())
    english = sum(w in _ENGLISH for w in words)
    german = sum(w in _GERMAN for w in words)
    if english >= 3 and english >= 2 * german:
        return "en"
    if german >= 3 and german >= 2 * english:
        return "de"
    return None


def content_words(text: str) -> set[str]:
    words = set()
    for raw in _WORD.findall(strip_markers(text).lower()):
        if raw in _STOPWORDS or (len(raw) < 3 and not any(c.isdigit() for c in raw)):
            continue
        words.add(raw[:WORD_PREFIX])
    return words


def overlap(text: str, sources: list[str]) -> float:
    """The share of the text's content words found in the sources together;
    1.0 for a text without content words (there is nothing to support)."""
    words = content_words(text)
    if not words:
        return 1.0
    pool: set[str] = set()
    for source in sources:
        pool |= content_words(source)
    return len(words & pool) / len(words)
