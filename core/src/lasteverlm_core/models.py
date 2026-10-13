"""The API models of the family's contract v1 (parent: docs/architecture.md).

One definition for the rows three services share and the frontend
renders. Ids are `UUID`, timestamps `datetime`; Pydantic serializes both
to strings on the wire, so a service that handled them as strings so far
only casts at its own boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# The user every caller of DEMO_TOKEN resolves to. Seeded by the account
# service's migration; fixed so all services agree on whose rows these are.
DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
DEMO_USER_EMAIL = "demo@localhost"

SourceKind = Literal["pdf", "text", "url", "image", "generated"]
SourceStatus = Literal["processing", "ready", "failed"]
OutputKind = Literal["report", "quiz", "table", "mindmap", "infographic", "audio"]
OutputStatus = Literal["waiting", "processing", "ready", "failed"]
UsageKind = Literal["llm", "embedding", "tts"]
UsageService = Literal["ingest", "rag"]
MessageRole = Literal["user", "assistant"]


class _Row(BaseModel):
    """Base for models that are read straight from database rows."""

    model_config = ConfigDict(from_attributes=True)


class User(_Row):
    """The account view every service and the frontend share."""

    id: UUID
    email: str
    is_admin: bool
    balance_cents: int
    created_at: datetime


class AdminUser(User):
    last_login_at: datetime | None = None
    usage_cents: int


class Notebook(_Row):
    id: UUID
    title: str
    created_at: datetime


class Source(_Row):
    id: UUID
    notebook_id: UUID
    name: str
    kind: SourceKind
    status: SourceStatus
    error: str | None = None
    created_at: datetime


class Citation(BaseModel):
    """One `[n]` marker of an answer, mapped back to the chunk it cites.

    `source_kind` lets the frontend render a citation into a PDF
    differently from one into a generated report. `quote` is the verbatim
    chunk text, never trimmed. `similarity` is the chunk's cosine
    similarity to the question (3 decimals), `chunk_index` its 0-based
    position in its source (`chunks.idx`), `chunk_count` the number of
    chunks of that source. The three are optional because messages stored
    before they existed carry none and still validate.
    """

    n: int = Field(ge=1)
    source_id: UUID
    source_name: str
    source_kind: SourceKind
    chunk_id: UUID
    page: int | None = None
    quote: str
    similarity: float | None = None
    chunk_index: int | None = Field(default=None, ge=0)
    chunk_count: int | None = Field(default=None, ge=1)


class ChunkView(BaseModel):
    """One chunk with its place in the source: what a click on a citation
    opens (`GET /api/rag/chunks/{chunk_id}`). `text` is the full chunk."""

    chunk_id: UUID
    source_id: UUID
    source_name: str
    source_kind: SourceKind
    page: int | None = None
    chunk_index: int = Field(ge=0)
    chunk_count: int = Field(ge=1)
    text: str


class Message(_Row):
    id: UUID
    role: MessageRole
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class Answer(BaseModel):
    message_id: UUID
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class Output(_Row):
    """A generated document. `options` holds the resolved generation options
    (language, voice, speed) as rag stores them; older outputs carry `{}`."""

    id: UUID
    notebook_id: UUID
    kind: OutputKind
    title: str
    content: dict[str, Any] | None = None
    status: OutputStatus
    error: str | None = None
    share_token: str | None = None
    source_id: UUID | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SharedOutput(BaseModel):
    """What `GET /api/rag/shared/{token}` returns: the document without ids."""

    kind: OutputKind
    title: str
    content: dict[str, Any] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class UsageRecord(BaseModel):
    """One row of the shared `usage` table, priced at write time.

    Usage rows are the only debit; the account service sums them against
    the ledger. Nothing else writes a debit.
    """

    user_id: UUID
    notebook_id: UUID | None
    service: UsageService
    kind: UsageKind
    model: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_cents: int = Field(ge=0)
