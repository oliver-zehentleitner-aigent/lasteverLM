"""Internal data shapes and the request bodies only rag accepts. The shared
API models (Answer, Citation, Message, Output, SharedOutput) come from core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from lasteverlm_core import OutputKind, OutputStatus, SharedOutput, SourceKind
from pydantic import BaseModel, Field, StringConstraints

from .options import OutputOptions


class AskScope(BaseModel):
    output_id: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID
    scope: AskScope | None = None
    # the sources the user ticked; absent or empty means all
    source_ids: list[UUID] | None = None


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ConversationRename(BaseModel):
    """A chat tab's new name, trimmed before the length check."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Conversation(BaseModel):
    """One chat tab of a notebook; every message belongs to exactly one."""

    id: UUID
    notebook_id: UUID
    title: str
    created_at: datetime


@dataclass(frozen=True)
class ConversationRow:
    """The ``conversations`` row plus the notebook owner, for the ownership check."""

    id: str
    notebook_id: str
    owner: str
    title: str
    created_at: Any

    def to_api(self) -> Conversation:
        return Conversation.model_validate(
            {
                "id": self.id,
                "notebook_id": self.notebook_id,
                "title": self.title,
                "created_at": self.created_at,
            }
        )


class OutputRename(BaseModel):
    """An output's new title, trimmed before the length check."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SharedSource(BaseModel):
    name: str
    kind: SourceKind


class SharedNotebook(BaseModel):
    """What ``GET /api/rag/shared/notebooks/{token}`` returns: the notebook's
    title, its ready uploads by name and kind (no files, no previews, no
    ids), and its ready outputs outside the trash, oldest first, each as the
    shared view of one output shows it."""

    title: str
    sources: list[SharedSource]
    outputs: list[SharedOutput]


class EstimateRequest(BaseModel):
    """``POST /api/rag/estimate``: an output ``kind`` with its options, or an
    ``action`` (``chat_answer``, ``chart_propose``, ``judge`` with ``level``
    and ``kind``, ``voice_sample``)."""

    kind: OutputKind | None = None
    action: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class JudgeRequest(BaseModel):
    """``POST /outputs/{id}/judge`` and ``POST /messages/{id}/judge``."""

    level: Literal["low", "medium", "high"]


class ChartPropose(BaseModel):
    """``POST /notebooks/{id}/charts/propose``: the user's instructions for
    the proposal and how many candidates at most."""

    instructions: str | None = Field(default=None, max_length=500)
    max: int = Field(default=6, ge=1, le=12)


class OutputCreate(BaseModel):
    kind: OutputKind
    options: OutputOptions | None = None
    # the sources the document is made from; absent or empty means all
    source_ids: list[UUID] | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk as returned by retrieval, with its source resolved."""

    chunk_id: str
    source_id: str
    source_name: str
    source_kind: SourceKind
    page: int | None
    text: str
    similarity: float
    chunk_index: int | None = None
    chunk_count: int | None = None


@dataclass(frozen=True)
class Passage:
    """A retrieved chunk numbered for the prompt; ``n`` is the citation marker."""

    n: int
    chunk_id: str
    source_id: str
    source_name: str
    source_kind: SourceKind
    page: int | None
    text: str
    similarity: float | None = None
    chunk_index: int | None = None
    chunk_count: int | None = None


@dataclass(frozen=True)
class NotebookDocument:
    """One ready document of a notebook as the chat lists it to the model."""

    source_id: str
    name: str
    kind: SourceKind
    output_kind: OutputKind | None = None


@dataclass(frozen=True)
class SourceSummary:
    """What a generator sees of one source: its name and the summary ingest wrote."""

    source_id: str
    name: str
    kind: SourceKind
    summary: str


@dataclass(frozen=True)
class SourceState:
    source_id: str
    kind: SourceKind
    status: str


@dataclass
class Unit:
    """One checkable part of a generated output: ``target`` is the entry in
    the content (a paragraph, a fact, a turn) that receives ``refs`` and
    ``support``; ``text`` is what is compared with the cited passages;
    ``refs`` are the passage numbers the model gave. A unit that is not a
    ``claim`` (an interviewer's question) is checked only when it cites."""

    target: dict[str, Any]
    text: str
    refs: list[int]
    claim: bool = True


@dataclass(frozen=True)
class Booking:
    """Who pays for a model call and for which user action: every usage row
    of one action (a chat answer, an output with all its attempts and judge
    rounds, a chart proposal, a judgement on request, a voice preview)
    shares the ``action_id``, so core books a fixed fee once per action."""

    user_id: str
    notebook_id: str | None
    action: str  # one of core's USAGE_ACTIONS
    action_id: UUID

    @classmethod
    def new(cls, user_id: str, notebook_id: str | None, action: str) -> Booking:
        return cls(user_id, notebook_id, action, uuid4())


@dataclass(frozen=True)
class GeneratedOutput:
    """What a generator produces: the title, the content per the kind's schema,
    and the plain text that gets chunked and embedded so chat can cite it."""

    title: str
    content: dict[str, Any]
    index_text: str
    speech: list[SpeechTurn] | None = None
    """What to synthesize into the output's audio file, turn by turn (audio
    kind only)."""
    units: list[Unit] = field(default_factory=list)
    """The parts the provenance check marks; empty for kinds without refs."""
    check: dict[str, Any] | None = None
    """A check the kind ran itself (a chart's number check); the word-overlap
    check of the units runs when this is ``None``."""
    document: Any = None
    """The validated document the content was built from; the judge edits
    it and rebuilds the output (``None`` for a chart)."""


@dataclass(frozen=True)
class SpeechTurn:
    """One stretch of a script read by one voice: ``speaker`` is a role
    (``narrator``, ``interviewer``, ``expert``), the options map it to a voice."""

    speaker: str
    text: str


@dataclass(frozen=True)
class OutputRow:
    """The ``outputs`` row. ``notebook_id`` is the origin, ``None`` once that
    notebook is deleted; ``owner`` is the user the output belongs to."""

    id: str
    notebook_id: str | None
    owner: str
    kind: OutputKind
    title: str
    content: dict[str, Any] | None
    status: OutputStatus
    error: str | None
    share_token: str | None
    source_id: str | None
    attempts: int
    created_at: str
    options: dict[str, Any] = field(default_factory=dict)
    origin_title: str = ""
    deleted_at: str | None = None
    purge_at: str | None = None
    provenance: dict[str, Any] | None = None


class NotebookStats(BaseModel):
    total: int


class MessageStats(BaseModel):
    total: int
    last_24h: int


class OutputStats(BaseModel):
    by_kind: dict[OutputKind, int]
    by_status: dict[OutputStatus, int]


class JobStats(BaseModel):
    pending: int
    running: int
    failed: int


class ShareStats(BaseModel):
    outputs: int


class AdminStats(BaseModel):
    """``GET /api/rag/admin/stats``; every key is present, zeros included."""

    notebooks: NotebookStats
    messages: MessageStats
    outputs: OutputStats
    jobs: JobStats
    shared: ShareStats


class DayStats(BaseModel):
    day: date
    messages: int
    outputs: int
    outputs_by_kind: dict[OutputKind, int]


class DailyStats(BaseModel):
    """``GET /api/rag/admin/stats/daily``: one entry per UTC day, oldest first,
    the last one today; every day and every kind present, zeros included."""

    days: list[DayStats]
