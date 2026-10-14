"""Chart output: number series from the sources, drawn as the user picks them.

Two steps. ``POST /notebooks/{id}/charts/propose`` asks the LLM once, over
passages retrieved for numeric material, for candidate charts; nothing is
stored. The user picks candidates and creates a ``chart`` output with the
picked candidate objects as ``options.charts``; the worker makes no second
model call. It loads the cited chunks again from the notebook and checks
every value against them (``numbers``): a value is ``supported`` only when
the number is written in a passage it cites, a computed one (a share, a sum,
a difference) is ``derived`` from the passages it names, never
``supported``. The candidates carry the chunk ids of their passages, so the
create step needs no server-side state from the proposal.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput, Passage
from ..numbers import NUMBER_CHECK, written_in
from ..options import CHARTS_MAX, PROPOSE_DEFAULT
from ._base import CITE_RULE, JsonGenerator

NO_SERIES = "the sources contain no number series"
SUPPORTED, UNSUPPORTED, DERIVED = "supported", "unsupported", "derived"

ChartType = Literal["bar", "line", "pie", "stacked_bar", "scatter"]


class Point(BaseModel):
    x: str | int | float
    y: float
    refs: list[int] = Field(default_factory=list, max_length=8)
    # the passages a computed value (a share, a sum, a difference) comes from
    derived_from: list[int] | None = Field(default=None, max_length=8)
    # set by the check, on the proposal and again on the output; never trusted from a client
    support: Literal["supported", "unsupported", "derived"] | None = None


class Series(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    points: list[Point] = Field(min_length=1, max_length=60)


class Chart(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    chart_type: ChartType
    x_label: str = Field(default="", max_length=80)
    y_label: str = Field(default="", max_length=80)
    series: list[Series] = Field(min_length=1, max_length=8)
    note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _fits_its_type(self) -> Chart:
        if self.chart_type == "pie" and len(self.series) != 1:
            raise ValueError("a pie chart has exactly one series")
        if self.chart_type == "scatter" and any(
            isinstance(p.x, str) for s in self.series for p in s.points
        ):
            raise ValueError("a scatter chart has numeric x values")
        return self


class Proposal(BaseModel):
    charts: list[Chart] = Field(default_factory=list, max_length=CHARTS_MAX)


class PassageRef(BaseModel):
    """A passage a candidate cites: its number in the proposal and its chunk."""

    n: int
    chunk_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    source_name: str
    page: int | None = None


class ProposalCall(BaseModel):
    """The proposal's model call, as the proposal reported it."""

    model: str
    prompt_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    proposed_at: str


class Candidate(Chart):
    """A proposed chart: what the user picks and sends back to create the output."""

    id: str = Field(min_length=1, max_length=64)
    passages: list[PassageRef] = Field(default_factory=list, max_length=60)
    proposal: ProposalCall


class ChartProposals(BaseModel):
    """What ``POST /notebooks/{id}/charts/propose`` returns; ``reason`` says
    why the list is empty, ``None`` otherwise."""

    candidates: list[Candidate]
    reason: str | None = None


class ChartGenerator(JsonGenerator):
    """The proposal prompt. The output itself is built by ``chart_content``
    from the picked candidates, without a model call."""

    kind: OutputKind = "chart"
    focus_query: str = "numbers, figures, statistics, amounts, percentages, values over time"
    schema: type[BaseModel] = Proposal
    prompt_version: str = "1"
    max_tokens: int = 6000
    instructions: str = ""

    def prompt(self, options: Mapping[str, Any]) -> tuple[str, type[BaseModel]]:
        limit = int(options.get("max", PROPOSE_DEFAULT))
        return (
            f"Propose up to {limit} charts of number series the material contains. A chart "
            "needs at least two values that belong together (a quantity over time, across "
            "categories, or as parts of a whole). Use only numbers written in the passages; "
            "never estimate, round or invent one. A value you compute from written numbers "
            '(a share, a sum, a difference) lists its passages in "derived_from" instead of '
            f'"refs". {CITE_RULE} Every value lists in "refs" the passages it is written in. '
            "chart_type is one of bar, line, pie, stacked_bar, scatter: line for values over "
            "time, pie only for parts of one whole (one series), scatter only for two "
            'numeric quantities. "note" says in one sentence what the chart shows and any '
            'unit. When the material has no number series, reply {"charts": []}. Reply as '
            '{"charts": [{"title", "chart_type", "x_label", "y_label", "series": [{"name", '
            '"points": [{"x", "y", "refs": [n], "derived_from": null or [n]}]}], "note"}]}.',
            Proposal,
        )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        raise NotImplementedError("a chart is built by chart_content")


def has_numbers(passages: list[Passage]) -> bool:
    return any(any(ch.isdigit() for ch in p.text) for p in passages)


def check_point(point: dict[str, Any], texts: Mapping[int, str]) -> str:
    """``derived`` when the point names the passages it is computed from and
    they all exist; ``supported`` when its value is written in a passage it
    cites; ``unsupported`` otherwise."""
    derived = point.get("derived_from")
    if derived:
        return DERIVED if all(n in texts for n in derived) else UNSUPPORTED
    refs = point.get("refs") or []
    if not refs or any(n not in texts for n in refs):
        return UNSUPPORTED
    return SUPPORTED if written_in(point["y"], [texts[n] for n in refs]) else UNSUPPORTED


def check_charts(charts: list[dict[str, Any]], texts: Mapping[int, str]) -> dict[str, Any]:
    """Mark every point's ``support`` in place; the counts for the log."""
    counts = {SUPPORTED: 0, UNSUPPORTED: 0, DERIVED: 0}
    for chart in charts:
        for series in chart["series"]:
            for point in series["points"]:
                point["support"] = check_point(point, texts)
                counts[point["support"]] += 1
    return {"method": NUMBER_CHECK, **counts}


def drawn(chart: Chart) -> dict[str, Any]:
    """A chart as content: no candidate id, no passages, no proposal."""
    return Chart.model_validate(chart.model_dump()).model_dump(exclude_none=True)


def renumber(candidates: list[Candidate]) -> tuple[list[str], list[dict[str, Any]]]:
    """One numbering for the passages of all picked candidates (each was
    numbered by its own proposal): the chunk ids in order of first use, and
    the charts with their refs rewritten to that numbering. A ref the
    candidate does not list becomes 0, which no passage has."""
    chunk_ids: list[str] = []
    charts: list[dict[str, Any]] = []
    for candidate in candidates:
        local = {p.n: p.chunk_id for p in candidate.passages}
        for chunk_id in local.values():
            if chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)

        def number(n: int, local: dict[int, str] = local) -> int:
            return chunk_ids.index(local[n]) + 1 if n in local else 0

        chart = drawn(candidate)
        for series in chart["series"]:
            for point in series["points"]:
                point["refs"] = [number(n) for n in point.get("refs", [])]
                if point.get("derived_from"):
                    point["derived_from"] = [number(n) for n in point["derived_from"]]
        charts.append(chart)
    return chunk_ids, charts


def chart_title(charts: list[dict[str, Any]]) -> str:
    if len(charts) == 1:
        return str(charts[0]["title"])
    return f"{charts[0]['title']} and {len(charts) - 1} more"[:200]


def chart_index_text(title: str, charts: list[dict[str, Any]]) -> str:
    """The charts as text for chat: each series as its x: y pairs."""
    lines = [title]
    for chart in charts:
        lines += ["", chart["title"]]
        if chart.get("note"):
            lines.append(chart["note"])
        axes = " / ".join(a for a in (chart.get("x_label"), chart.get("y_label")) if a)
        if axes:
            lines.append(axes)
        for series in chart["series"]:
            pairs = ", ".join(f"{p['x']}: {_number(p['y'])}" for p in series["points"])
            lines.append(f"{series['name']}: {pairs}")
    return "\n".join(lines)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else json.dumps(value)
