"""Provenance of generated outputs: the support check of their units and the
generation log stored with them.

Every unit of a generated output (a report paragraph, an infographic fact
or section, an audio paragraph or turn) carries the passage numbers it
cites (``refs``) and the result of a deterministic check (``support``):

- ``supported``: every ref names a passage that was in the prompt, and the
  unit's words overlap the cited passages by at least the threshold
  (``citations.overlap``);
- ``unsupported``: no refs, a ref no passage has, or too little overlap;
- ``unverified``: the refs are valid but the overlap is low while the output
  was written in a chosen language, which may not be the material's, so
  word overlap cannot tell.

A unit that fails is kept and marked, never dropped, and never fails the
output. A unit that is not a claim (an interviewer's question without refs)
gets no ``support``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .citations import CHECK_METHOD, OVERLAP_THRESHOLD, overlap
from .models import Passage, RetrievedChunk, Unit

PROVENANCE_VERSION = 1
SUPPORTED, UNSUPPORTED, UNVERIFIED = "supported", "unsupported", "unverified"
# what the shared view leaves out: ids of the owner's sources and chunks
_PRIVATE_KEYS = ("chunk_id", "source_id")


def check_units(units: list[Unit], passages: list[Passage], translated: bool) -> dict[str, Any]:
    """Mark every unit's ``target`` with its valid ``refs`` and its ``support``;
    returns the check's summary for the log."""
    by_n = {p.n: p for p in passages}
    counts = {SUPPORTED: 0, UNSUPPORTED: 0, UNVERIFIED: 0}
    for unit in units:
        refs = list(dict.fromkeys(unit.refs))
        valid = [n for n in refs if n in by_n]
        unit.target["refs"] = valid
        if not refs and not unit.claim:
            continue
        if not refs or len(valid) != len(refs):
            support = UNSUPPORTED
        elif overlap(unit.text, [by_n[n].text for n in valid]) >= OVERLAP_THRESHOLD:
            support = SUPPORTED
        else:
            support = UNVERIFIED if translated else UNSUPPORTED
        unit.target["support"] = support
        counts[support] += 1
    return {"method": CHECK_METHOD, "threshold": OVERLAP_THRESHOLD, **counts}


def now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class GenerationLog:
    """Collected while an output is generated; ``record`` is what is stored."""

    prompt_version: str
    model: str
    options: dict[str, Any]
    focus_query: str
    k: int
    floor: float
    started_at: str = field(default_factory=now)
    candidates: list[RetrievedChunk] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)
    llm_in: int = 0
    llm_out: int = 0
    embedding_in: int = 0
    tts_seconds: int = 0

    def record(self, check: dict[str, Any]) -> dict[str, Any]:
        in_prompt = {p.chunk_id for p in self.passages}
        return {
            "version": PROVENANCE_VERSION,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "options": self.options,
            "focus_query": self.focus_query,
            "retrieval": {
                "k": self.k,
                "floor": self.floor,
                "candidates": [
                    {
                        "chunk_id": c.chunk_id,
                        "source_id": c.source_id,
                        "source_name": c.source_name,
                        "page": c.page,
                        "similarity": round(c.similarity, 3),
                        "in_prompt": c.chunk_id in in_prompt,
                    }
                    for c in self.candidates
                ],
            },
            "passages": [
                {
                    "n": p.n,
                    "chunk_id": p.chunk_id,
                    "source_id": p.source_id,
                    "source_name": p.source_name,
                    "source_kind": p.source_kind,
                    "page": p.page,
                    "chunk_index": p.chunk_index,
                    "chunk_count": p.chunk_count,
                    "similarity": None if p.similarity is None else round(p.similarity, 3),
                    "quote": p.text,
                }
                for p in self.passages
            ],
            "usage": {
                "llm": {"tokens_in": self.llm_in, "tokens_out": self.llm_out},
                "embedding": {"tokens_in": self.embedding_in},
                "tts": {"seconds": self.tts_seconds},
            },
            "started_at": self.started_at,
            "finished_at": now(),
            "check": check,
        }


def shared_provenance(provenance: dict[str, Any] | None) -> dict[str, Any] | None:
    """The log as the shared view shows it: without the owner's source and
    chunk ids and without the source selection in the options."""
    if provenance is None:
        return None

    def public(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in e.items() if k not in _PRIVATE_KEYS} for e in entries]

    retrieval = provenance.get("retrieval", {})
    return {
        **provenance,
        "options": {k: v for k, v in provenance.get("options", {}).items() if k != "sources"},
        "retrieval": {**retrieval, "candidates": public(retrieval.get("candidates", []))},
        "passages": public(provenance.get("passages", [])),
    }
