from __future__ import annotations

from collections.abc import Mapping, Set
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
    # 3: every fitting source, unused named; 2: cites passages
    prompt_version: str = "4"  # 4: every detail cited, one no passage states left out
    instructions: str = (
        "Extract the data in the material that is best shown as one table: the entities and "
        f"their attributes, figures, dates or comparisons. Cells are short strings. {CITE_RULE} "
        'List the passage numbers of each row in "row_refs", one list per row, in row order. '
        'Reply as {"title": "...", "columns": [...], "rows": [[...], ...], '
        '"row_refs": [[n, ...], ...]}.'
    )

    # -- editing: a unit is a row with its refs -------------------------------

    def editable(self, document: BaseModel, index: int) -> dict[str, Any]:
        assert isinstance(document, Table)
        refs = document.row_refs[index] if document.row_refs else []
        return {"cells": document.rows[index], "refs": refs}

    def edit(self, document: BaseModel, index: int, fields: Mapping[str, Any]) -> BaseModel:
        assert isinstance(document, Table)
        cells, refs = fields.get("cells"), fields.get("refs", [])
        if not isinstance(cells, list) or len(cells) != len(document.columns):
            raise ValueError("a revised row has one cell per column")
        if not isinstance(refs, list) or not all(isinstance(n, int) for n in refs):
            raise ValueError("refs are passage numbers")
        rows = list(document.rows)
        rows[index] = [str(c) for c in cells]
        row_refs = list(document.row_refs) or [[] for _ in rows]
        row_refs[index] = refs
        return document.model_copy(update={"rows": rows, "row_refs": row_refs})

    def remove(self, document: BaseModel, indexes: Set[int]) -> BaseModel:
        assert isinstance(document, Table)
        rows = [r for i, r in enumerate(document.rows) if i not in indexes]
        row_refs = [r for i, r in enumerate(document.row_refs) if i not in indexes]
        return document.model_copy(update={"rows": rows, "row_refs": row_refs})

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
