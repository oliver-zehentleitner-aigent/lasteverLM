from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import OutputKind
from ..models import GeneratedOutput
from ._base import JsonGenerator


class Report(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1)


class ReportGenerator(JsonGenerator):
    kind: OutputKind = "report"
    focus_query: str = "main topics, key findings, conclusions"
    schema: type[BaseModel] = Report
    instructions: str = (
        "Write a structured report on the material: an introduction, one section per main "
        "topic with headings, and a conclusion. Markdown, no top-level title inside the text. "
        'Reply as {"title": "...", "markdown": "..."}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Report)
        return GeneratedOutput(
            title=document.title,
            content={"markdown": document.markdown},
            index_text=f"{document.title}\n\n{document.markdown}",
        )
