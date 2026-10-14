from __future__ import annotations

from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput, Unit
from ._base import CITE_RULE, JsonGenerator


class Table(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    columns: list[str] = Field(min_length=1, max_length=20)
    rows: list[list[str]] = Field(min_length=1, max_length=200)
    # the passage numbers of each row, in row order
    row_refs: list[list[int]] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def rows_match_columns(self) -> Table:
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("every row must have exactly one cell per column")
        if self.row_refs and len(self.row_refs) != len(self.rows):
            raise ValueError("row_refs must have one entry per row")
        return self


class TableGenerator(JsonGenerator):
    kind: OutputKind = "table"
    focus_query: str = "figures, dates, comparisons, lists of items with attributes"
    schema: type[BaseModel] = Table
    prompt_version: str = "2"  # 2: cites passages for provenance
    instructions: str = (
        "Extract the data in the material that is best shown as one table: the entities and "
        f"their attributes, figures, dates or comparisons. Cells are short strings. {CITE_RULE} "
        'List the passage numbers of each row in "row_refs", one list per row, in row order. '
        'Reply as {"title": "...", "columns": [...], "rows": [[...], ...], '
        '"row_refs": [[n, ...], ...]}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Table)
        lines = [document.title, "", " | ".join(document.columns)]
        lines += [" | ".join(row) for row in document.rows]
        refs = document.row_refs or [[] for _ in document.rows]
        row_refs: list[dict[str, Any]] = [{} for _ in document.rows]
        units = [
            Unit(target, " ".join(row), row_ref)
            for target, row, row_ref in zip(row_refs, document.rows, refs, strict=True)
        ]
        return GeneratedOutput(
            title=document.title,
            # rows stay lists of cells; row_refs[i] holds row i's refs and support
            content={"columns": document.columns, "rows": document.rows, "row_refs": row_refs},
            index_text="\n".join(lines),
            units=units,
        )
