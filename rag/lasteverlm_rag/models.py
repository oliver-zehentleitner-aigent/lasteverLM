"""Internal data shapes and the request bodies only rag accepts. The shared
API models (Answer, Citation, Message, Output, SharedOutput) come from core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from lasteverlm_core import OutputKind, OutputStatus, SourceKind
from pydantic import BaseModel, Field, StringConstraints

from .options import OutputOptions


class AskScope(BaseModel):
    output_id: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID
    scope: AskScope | None = None


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


class OutputCreate(BaseModel):
    kind: OutputKind
    options: OutputOptions | None = None


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


@dataclass(frozen=True)
class GeneratedOutput:
    """What a generator produces: the title, the content per the kind's schema,
    and the plain text that gets chunked and embedded so chat can cite it."""

    title: str
    content: dict[str, Any]
    index_text: str
    speech: str | None = None
    """Text to synthesize into the output's audio file (audio kind only)."""


@dataclass(frozen=True)
class OutputRow:
    """The ``outputs`` row plus the notebook owner, for the ownership check."""

    id: str
    notebook_id: str
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
