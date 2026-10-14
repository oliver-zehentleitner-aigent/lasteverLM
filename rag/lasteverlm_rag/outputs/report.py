from __future__ import annotations

import re
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


class ReportGenerator(JsonGenerator):
    kind: OutputKind = "report"
    focus_query: str = "main topics, key findings, conclusions"
    schema: type[BaseModel] = Report
    prompt_version: str = "2"  # 2: cites passages for provenance
    instructions: str = (
        "Write a structured report on the material: an introduction, one section per main "
        "topic with headings, and a conclusion. Markdown, no top-level title inside the text. "
        f"{CITE_RULE} Put the markers in the text after the sentence they support, as [2] or "
        "[1, 3]; headings carry none. "
        'Reply as {"title": "...", "markdown": "..."}.'
    )

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
        *,
        language: str | None = None,
        style: str | None = None,
    ) -> GeneratedOutput:
        generated = super().generate(
            complete, notebook_title, summaries, passages, language=language, style=style
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
