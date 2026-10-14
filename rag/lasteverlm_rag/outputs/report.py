from __future__ import annotations

import re
from collections.abc import Mapping
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
# one per length of ``options.LENGTHS``: the target in words, and the answer's budget
LENGTHS: dict[str, tuple[str, int]] = {
    "short": ("about 300 to 500 words", 4000),
    "medium": ("about 700 to 1200 words", 4000),
    "long": ("about 1800 to 2500 words", 8000),
}


class ReportGenerator(JsonGenerator):
    kind: OutputKind = "report"
    focus_query: str = "main topics, key findings, conclusions"
    schema: type[BaseModel] = Report
    prompt_version: str = "3"  # 3: styles and lengths; 2: cites passages for provenance
    instructions: str = ""

    def prompt(self, options: Mapping[str, Any]) -> tuple[str, type[BaseModel]]:
        style = STYLES[options.get("report_style", "briefing")]
        words, _ = LENGTHS[options.get("length", "medium")]
        return (
            f"{style} Length: {words}. Markdown, no top-level title inside the text. "
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
        return self._document(generated.title, markdown, generated.units)

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
