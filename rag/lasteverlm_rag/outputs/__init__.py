"""Output generators: one interface, one module per kind.

A generator turns a notebook (the summaries of its sources plus the chunks
retrieved for the generator's own focus query) into a document of one kind.
Adding a kind is one more module here plus its renderer in web; nothing
else changes.
"""

from __future__ import annotations

from typing import Protocol

from lasteverlm_core import CompletionResult, OutputKind

from ..models import GeneratedOutput, Passage, SourceSummary


class OutputGenerator(Protocol):
    kind: OutputKind
    focus_query: str

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
        *,
        language: str | None = None,
    ) -> GeneratedOutput: ...


class CompleteFn(Protocol):
    """One accounted LLM call: the service wraps ``LLM.complete`` so every call
    the generator makes writes its usage row. Same signature as ``LLM.complete``;
    thinking stays off unless a generator asks for it."""

    def __call__(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        *,
        thinking: bool | None = None,
    ) -> CompletionResult: ...


def registry(tts_available: bool) -> dict[OutputKind, OutputGenerator]:
    from .audio import AudioGenerator
    from .infographic import InfographicGenerator
    from .mindmap import MindmapGenerator
    from .quiz import QuizGenerator
    from .report import ReportGenerator
    from .table import TableGenerator

    generators: list[OutputGenerator] = [
        ReportGenerator(),
        QuizGenerator(),
        TableGenerator(),
        MindmapGenerator(),
        InfographicGenerator(),
        AudioGenerator(available=tts_available),
    ]
    return {g.kind: g for g in generators}
