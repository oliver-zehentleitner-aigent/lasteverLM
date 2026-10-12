from __future__ import annotations

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput
from ._base import JsonGenerator


class Table(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    columns: list[str] = Field(min_length=1, max_length=20)
    rows: list[list[str]] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def rows_match_columns(self) -> Table:
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("every row must have exactly one cell per column")
        return self


class TableGenerator(JsonGenerator):
    kind: OutputKind = "table"
    focus_query: str = "figures, dates, comparisons, lists of items with attributes"
    schema: type[BaseModel] = Table
    instructions: str = (
        "Extract the data in the material that is best shown as one table: the entities and "
        "their attributes, figures, dates or comparisons. Cells are short strings. Reply as "
        '{"title": "...", "columns": [...], "rows": [[...], ...]}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Table)
        lines = [document.title, "", " | ".join(document.columns)]
        lines += [" | ".join(row) for row in document.rows]
        return GeneratedOutput(
            title=document.title,
            content={"columns": document.columns, "rows": document.rows},
            index_text="\n".join(lines),
        )
