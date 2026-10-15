from __future__ import annotations

import re
from collections.abc import Mapping, Set
from dataclasses import replace
from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..citations import extract_markers, keep_markers, strip_markers
from ..models import GeneratedOutput, Passage, SourceSummary, Unit
from . import CompleteFn
from ._base import CITE_RULE, JsonGenerator

_PARAGRAPH = re.compile(r"\n\s*\n")


class Report(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1)


# one per style of ``options.REPORT_STYLES``: what kind of document, for whom
STYLES: dict[str, str] = {
    "briefing": (
        "Write a briefing document on the material: an introduction, one section per main "
        "topic with headings, and a conclusion."
    ),
    "detailed": (
        "Write a detailed report on the material: an introduction, one section per topic "
        "with headings, each covering the topic in depth with the specifics the material "
        "gives (numbers, names, conditions, exceptions), and a conclusion."
    ),
    "executive_summary": (
        "Write an executive summary of the material for a reader who has to act on it: the "
        "bottom line first, then the key findings, their implications and any risks or open "
        "points the material names, with short headings. Lead with what matters most."
    ),
    "explainer": (
        "Write an explainer of the material for a reader new to the subject: start from the "
        "basics, explain every term when it first appears, build up step by step under "
        "headings, and use the material's own examples. Plain words over jargon."
    ),
    "academic": (
        "Write an academic-style report on the material: a formal register and precise "
        "terminology, an introduction stating the subject and scope, sections with headings "
        "that present and discuss the material's content, and a conclusion that includes the "
        "limitations the material itself states. Cite no literature beyond the passages."
    ),
}
# one per length of ``options.LENGTHS``: the most words, and the answer's budget.
# An upper bound, not a target: a target fills short material with invention.
LENGTHS: dict[str, tuple[int, int]] = {
    "short": (500, 4000),
    "medium": (1200, 4000),
    "long": (2500, 8000),
}
NO_FILLER = (
    "Never add facts, roles, steps or reasons the material does not state, "
    "not even to reach the length."
)


class ReportGenerator(JsonGenerator):
    kind: OutputKind = "report"
    focus_query: str = "main topics, key findings, conclusions"
    schema: type[BaseModel] = Report
    # 4: lengths are upper bounds, no filler; 3: styles and lengths; 2: cites passages
    prompt_version: str = "4"
    instructions: str = ""

    def prompt(self, options: Mapping[str, Any]) -> tuple[str, type[BaseModel]]:
        style = STYLES[options.get("report_style", "briefing")]
        words, _ = LENGTHS[options.get("length", "medium")]
        return (
            f"{style} Length: at most {words} words; shorter when the material says less. "
            f"{NO_FILLER} Markdown, no top-level title inside the text. "
            f"{CITE_RULE} Put the markers in the text after the sentence they support, as [2] "
            "or [1, 3]; headings carry none. "
            'Reply as {"title": "...", "markdown": "..."}.',
            Report,
        )

    def budget(self, options: Mapping[str, Any]) -> int:
        return LENGTHS[options.get("length", "medium")][1]

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
        *,
        language: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> GeneratedOutput:
        generated = super().generate(
            complete, notebook_title, summaries, passages, language=language, options=options
        )
        # a marker no passage has is dropped from the text, as in a chat answer;
        # the check marks its paragraph unsupported
        markdown = keep_markers(generated.content["markdown"], {p.n for p in passages})
        output = self._document(generated.title, markdown, generated.units)
        return replace(output, document=Report(title=generated.title, markdown=markdown))

    # -- editing: a unit is a paragraph that is not a heading ---------------

    def _paragraphs(self, document: BaseModel) -> tuple[list[str], list[int]]:
        assert isinstance(document, Report)
        paragraphs = [p for p in _PARAGRAPH.split(document.markdown.strip()) if p.strip()]
        claims = [i for i, p in enumerate(paragraphs) if not p.lstrip().startswith("#")]
        return paragraphs, claims

    def editable(self, document: BaseModel, index: int) -> dict[str, Any]:
        paragraphs, claims = self._paragraphs(document)
        return {"text": paragraphs[claims[index]]}

    def edit(self, document: BaseModel, index: int, fields: Mapping[str, Any]) -> BaseModel:
        paragraphs, claims = self._paragraphs(document)
        # one paragraph stays one paragraph, and never turns into a heading
        text = " ".join(str(fields.get("text", "")).split()).lstrip("#").strip()
        if not text:
            raise ValueError("a revised paragraph needs text")
        paragraphs[claims[index]] = text
        return document.model_copy(update={"markdown": "\n\n".join(paragraphs)})

    def remove(self, document: BaseModel, indexes: Set[int]) -> BaseModel:
        paragraphs, claims = self._paragraphs(document)
        gone = {claims[i] for i in indexes}
        kept = [p for i, p in enumerate(paragraphs) if i not in gone]
        return document.model_copy(update={"markdown": "\n\n".join(kept)})

    def rebuild(self, document: BaseModel, passages: list[Passage]) -> GeneratedOutput:
        assert isinstance(document, Report)
        markdown = keep_markers(document.markdown, {p.n for p in passages})
        output = self._document(document.title, markdown, None)
        return replace(output, document=document.model_copy(update={"markdown": markdown}))

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Report)
        return self._document(document.title, document.markdown, None)

    def _document(self, title: str, markdown: str, cited: list[Unit] | None) -> GeneratedOutput:
        """One unit per paragraph that is not a heading: its text exactly as in
        the markdown, its refs the markers the model wrote (before cleaning)."""
        paragraphs = [p for p in _PARAGRAPH.split(markdown.strip()) if p.strip()]
        content_units: list[dict[str, Any]] = []
        units: list[Unit] = []
        claims = [p for p in paragraphs if not p.lstrip().startswith("#")]
        for i, paragraph in enumerate(claims):
            refs = cited[i].refs if cited else extract_markers(paragraph)
            target: dict[str, Any] = {"text": paragraph}
            content_units.append(target)
            units.append(Unit(target, paragraph, refs))
        return GeneratedOutput(
            title=title,
            content={"markdown": markdown, "units": content_units},
            index_text=f"{title}\n\n{strip_markers(markdown)}",
            units=units,
        )
