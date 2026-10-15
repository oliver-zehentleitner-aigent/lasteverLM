"""Tables and infographic themes proposed first, picked by the user, then
made one by one: "Find tables" / "Find themes".

A proposal is a preview, not the result: a table candidate has its title,
its columns and a few rows, a theme its headline and a few facts, each with
the sources it comes from. Creating the output makes one full table (or one
infographic part) per picked candidate, from that candidate's sources only,
so a notebook of unrelated sources gives several tables instead of one that
silently uses one source or forces them together.

``CompositeGenerator`` holds the made parts as one document: the word check,
the judge's revisions and removal see their units in order, part after part.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import replace
from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..models import GeneratedOutput, Passage
from ._base import CITE_RULE, JsonGenerator
from .chart import PassageRef, ProposalCall

PREVIEW_ROWS = 3
PREVIEW_FACTS = 4


class TableIdea(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    columns: list[str] = Field(min_length=1, max_length=20)
    preview: list[list[str]] = Field(default_factory=list, max_length=PREVIEW_ROWS)
    refs: list[int] = Field(default_factory=list, max_length=24)


class TableIdeas(BaseModel):
    tables: list[TableIdea] = Field(default_factory=list, max_length=12)


class FactPreview(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=200)


class ThemeIdea(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    headline: str = Field(min_length=1, max_length=300)
    facts: list[FactPreview] = Field(default_factory=list, max_length=PREVIEW_FACTS)
    refs: list[int] = Field(default_factory=list, max_length=24)


class ThemeIdeas(BaseModel):
    themes: list[ThemeIdea] = Field(default_factory=list, max_length=12)


class SourceRef(BaseModel):
    source_id: str
    name: str


class TableCandidate(BaseModel):
    """A proposed table: what the user picks and sends back to create it."""

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    columns: list[str] = Field(min_length=1, max_length=20)
    preview: list[list[str]] = Field(default_factory=list, max_length=PREVIEW_ROWS)
    sources: list[SourceRef] = Field(min_length=1, max_length=24)
    passages: list[PassageRef] = Field(default_factory=list, max_length=60)
    proposal: ProposalCall


class ThemeCandidate(BaseModel):
    """A proposed infographic theme."""

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    headline: str = Field(min_length=1, max_length=300)
    facts: list[FactPreview] = Field(default_factory=list, max_length=PREVIEW_FACTS)
    sources: list[SourceRef] = Field(min_length=1, max_length=24)
    passages: list[PassageRef] = Field(default_factory=list, max_length=60)
    proposal: ProposalCall


class TableProposals(BaseModel):
    candidates: list[TableCandidate] = Field(default_factory=list)
    reason: str | None = None


class ThemeProposals(BaseModel):
    candidates: list[ThemeCandidate] = Field(default_factory=list)
    reason: str | None = None


# the option that carries the picked candidates, per kind, and the content's list
PART_OPTION = {"table": "tables", "infographic": "themes"}
PART_LIST = {"table": "tables", "infographic": "parts"}

# what each kind proposes, and how
PROPOSE = {
    "table": {
        "action": "table_propose",
        "option": "tables",
        "focus_query": "figures, dates, comparisons, lists of items with attributes",
        "schema": TableIdeas,
        "candidate": TableCandidate,
        "task": (
            "Propose up to {max} distinct tables the material supports. Each table shows one "
            "set of things with the same attributes and comes only from the sources that "
            "hold them: material from unrelated sources makes separate tables, never one "
            "table forced across them. Give each a title, its columns, at most "
            f'{PREVIEW_ROWS} example rows as they would appear, and in "refs" the passage '
            "numbers it comes from. Propose fewer, or none, when the material holds fewer. "
            'Reply as {{"tables": [{{"title", "columns": [...], "preview": [[...], ...], '
            '"refs": [n, ...]}}]}}.'
        ),
    },
    "infographic": {
        "action": "infographic_propose",
        "option": "themes",
        "focus_query": "striking numbers, key facts, the main messages",
        "schema": ThemeIdeas,
        "candidate": ThemeCandidate,
        "task": (
            "Propose up to {max} distinct themes for an infographic that the material "
            "supports, each from the sources that hold it: material from unrelated sources "
            "makes separate themes. Give each a title, a one-line headline, at most "
            f'{PREVIEW_FACTS} key facts as short label/value pairs, and in "refs" the '
            "passage numbers it comes from. Propose fewer, or none, when the material "
            'holds fewer. Reply as {{"themes": [{{"title", "headline", "facts": [{{"label", '
            '"value"}}], "refs": [n, ...]}}]}}.'
        ),
    },
}


def idea_task(kind: str, limit: int) -> tuple[str, type[BaseModel]]:
    spec = PROPOSE[kind]
    task = str(spec["task"]).format(max=limit) + f" {CITE_RULE}"
    schema = spec["schema"]
    assert isinstance(schema, type)
    return task, schema


def part_task(kind: str, candidate: Mapping[str, Any], instructions: str) -> str:
    """The generator's own task, aimed at one picked candidate."""
    if kind == "table":
        columns = "; ".join(str(c) for c in candidate["columns"])
        aim = (
            f'Make the table "{candidate["title"]}" with these columns: {columns}. Keep the '
            "columns unless the material needs another; include every row the material holds."
        )
    else:
        aim = (
            f'Make the infographic part "{candidate["title"]}" around the message '
            f'"{candidate["headline"]}".'
        )
    return f"{aim} {instructions}"


class Composite(BaseModel):
    """Several made parts as one document (a table per picked candidate, or an
    infographic part per picked theme)."""

    title: str
    parts: list[Any]
    candidate_ids: list[str]


class CompositeGenerator(JsonGenerator):
    """The kind's generator over a ``Composite``: unit ``i`` is found by
    walking the parts in order, each part handled by the base generator."""

    def __init__(self, base: JsonGenerator, key: str) -> None:
        self.base = base
        self.key = key  # "tables" or "parts", the content's list
        self.kind: OutputKind = base.kind
        self.focus_query = base.focus_query
        self.instructions = base.instructions
        self.schema = base.schema
        self.max_tokens = base.max_tokens
        self.prompt_version = base.prompt_version
        self.fixed_fields = base.fixed_fields

    def _where(self, document: Composite, index: int) -> tuple[int, int]:
        for p, part in enumerate(document.parts):
            count = len(self.base.to_output(part).units)
            if index < count:
                return p, index
            index -= count
        raise IndexError("no such unit")

    def editable(self, document: BaseModel, index: int) -> dict[str, Any]:
        assert isinstance(document, Composite)
        p, i = self._where(document, index)
        return self.base.editable(document.parts[p], i)

    def edit(self, document: BaseModel, index: int, fields: Mapping[str, Any]) -> BaseModel:
        assert isinstance(document, Composite)
        p, i = self._where(document, index)
        parts = list(document.parts)
        parts[p] = self.base.edit(parts[p], i, fields)
        return document.model_copy(update={"parts": parts})

    def remove(self, document: BaseModel, indexes: Set[int]) -> BaseModel:
        assert isinstance(document, Composite)
        parts, ids, start = [], [], 0
        for part, cid in zip(document.parts, document.candidate_ids, strict=True):
            count = len(self.base.to_output(part).units)
            local = {i - start for i in indexes if start <= i < start + count}
            start += count
            if count and len(local) == count:
                continue  # every unit of the part went: the part goes
            parts.append(self.base.remove(part, local) if local else part)
            ids.append(cid)
        return document.model_copy(update={"parts": parts, "candidate_ids": ids})

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Composite)
        made = [self.base.to_output(part) for part in document.parts]
        content = {
            self.key: [
                {"title": out.title, **out.content, "candidate_id": cid}
                for out, cid in zip(made, document.candidate_ids, strict=True)
            ]
        }
        return GeneratedOutput(
            title=document.title,
            content=content,
            index_text="\n\n".join([document.title, *(out.index_text for out in made)]),
            units=[unit for out in made for unit in out.units],
        )

    def rebuild(self, document: BaseModel, passages: list[Passage]) -> GeneratedOutput:
        return replace(self.to_output(document), document=document)


def composite_title(titles: list[str]) -> str:
    title = " · ".join(titles)
    return title if len(title) <= 200 else title[:199] + "…"
