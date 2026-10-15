"""All database access, behind one interface.

The schema is owned by the infra repository (migrations); this module only
reads and writes it. Services share the database and never call each
other, so the tables below are the contract with rag and account.

A library source (`library_sources`) is what a user uploaded or entered
once, processed once, owning the chunks. A source (`sources`) is its link
into a notebook; the link id is the public source id. Library sources of
kind `generated` are rag's outputs: rag writes them and owns their trash,
restore and purge, so every read of the uploaded library goes through
`_LISTED`; they are listed on their own (`list_generated`) and can be
linked into any of the owner's notebooks like an upload. A deleted library source sits in the
trash (`deleted_at`, no links, chunks kept) until the owner's retention
has elapsed and the worker purges it.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from lasteverlm_core import (
    Chunk,
    ModelPrices,
    Notebook,
    PricingRules,
    PricingRulesCache,
    Role,
    Source,
    Usage,
    UsageRecord,
    balance_sql,
    funded_sql,
)
from lasteverlm_core import admin_role as core_admin_role
from lasteverlm_core import balance_cents as core_balance_cents
from lasteverlm_core import has_credit as core_has_credit
from lasteverlm_core import record_usage as core_record_usage
from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)


class OwnedNotebook(Notebook):
    """A notebook as its owner sees it: with the token of its read-only
    share link (null when not shared)."""

    share_token: str | None = None
    # Made as a copy of the starter notebook (first sign-in or on request).
    starter: bool = False


class StoredSource(Source):
    """A source as a notebook shows it: the link row joined with its
    library source, plus the fields the API does not expose."""

    model_config = ConfigDict(from_attributes=True)

    library_id: UUID
    owner: UUID
    storage_path: str | None
    url: str | None = None
    summary: str | None = None
    attempts: int = 0
    size_bytes: int | None = None
    capture: str | None = None
    starter: bool = False
    version: int = 1
    fetched_at: datetime | None = None
    final_url: str | None = None
    checked_at: datetime | None = None
    funded_request_at: datetime | None = Field(default=None, exclude=True)
    funded_cents: Decimal | None = Field(default=None, exclude=True)
    snapshot_path: str | None = None
    transcribed_path: str | None = None
    # Which models made the text ({"vision": …, "stt": …}), and the PDF
    # pages the vision model read; null when no model did.
    read_by: dict[str, str | None] | None = None
    vision_pages: list[int] | None = Field(default=None, exclude=True)
    # A PDF's pages, an image's tiles: the pieces a model reads.
    page_count: int | None = Field(default=None, exclude=True)


class LibrarySource(BaseModel):
    """One row of `library_sources`."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner: UUID
    name: str
    kind: str
    dedupe_key: str | None = None
    url: str | None = None
    size_bytes: int | None = None
    storage_path: str | None = None
    status: str
    error: str | None = None
    summary: str | None = None
    attempts: int = 0
    created_at: datetime
    deleted_at: datetime | None = None
    capture: str | None = None
    starter: bool = False
    transcribed_path: str | None = None
    page_count: int | None = None
    duration_seconds: float | None = None
    version: int = 1
    fetched_at: datetime | None = None
    content_hash: str | None = None
    refetch_requested_at: datetime | None = None
    superseded_by: UUID | None = None
    snapshot_path: str | None = None
    final_url: str | None = None
    checked_at: datetime | None = None
    funded_request_at: datetime | None = None
    funded_cents: Decimal | None = None
    read_by: dict[str, str | None] | None = None
    vision_pages: list[int] | None = None


class NotebookUse(BaseModel):
    id: UUID
    title: str
    source_id: UUID


class ProcessResult(BaseModel):
    """`queue_for_processing`: what moved to `processing`, what was left as
    it was (read, being read, failed), and ids not the owner's."""

    queued: list[UUID] = []
    unchanged: list[UUID] = []
    missing: list[UUID] = []


class LinkResult(BaseModel):
    """`link_many`: what was linked, what was linked before, and the ids
    that cannot be linked (then nothing was)."""

    added: list[UUID] = []
    already: list[UUID] = []
    missing: list[UUID] = []


class Origin(BaseModel):
    """Where a generated entry was made: the notebook's id (null once it is
    deleted) and its title (as it was then, if deleted)."""

    id: UUID | None
    title: str | None


class LibraryEntry(BaseModel):
    """`GET /library`: a library source with the notebooks it is in;
    `origin` is set for generated entries only."""

    id: UUID
    name: str
    kind: str
    status: str
    error: str | None
    size_bytes: int | None
    url: str | None
    created_at: datetime
    capture: str | None = None
    starter: bool = False
    version: int = 1
    fetched_at: datetime | None = None
    final_url: str | None = None
    checked_at: datetime | None = None
    funded_request_at: datetime | None = Field(default=None, exclude=True)
    funded_cents: Decimal | None = Field(default=None, exclude=True)
    snapshot_path: str | None = Field(default=None, exclude=True)
    notebooks: list[NotebookUse]
    origin: Origin | None = None
    # A generated entry's output in rag (`GET /outputs/{id}`); null otherwise.
    output_id: UUID | None = None
    # Set by the API (api/deps.py): where the source opens, and for a
    # converted recording the original as a download.
    preview_url: str | None = None
    original_url: str | None = None
    snapshot_url: str | None = None
    storage_path: str | None = Field(default=None, exclude=True)
    transcribed_path: str | None = Field(default=None, exclude=True)


class TrashEntry(BaseModel):
    """`GET /library/trash`: a deleted library source and when it goes."""

    id: UUID
    name: str
    kind: str
    status: str
    error: str | None
    size_bytes: int | None
    url: str | None
    created_at: datetime
    deleted_at: datetime
    purge_at: datetime
    capture: str | None = None
    starter: bool = False
    version: int = 1
    fetched_at: datetime | None = None
    final_url: str | None = None
    checked_at: datetime | None = None
    funded_request_at: datetime | None = Field(default=None, exclude=True)
    funded_cents: Decimal | None = Field(default=None, exclude=True)
    snapshot_path: str | None = Field(default=None, exclude=True)
    preview_url: str | None = None
    original_url: str | None = None
    snapshot_url: str | None = None
    storage_path: str | None = Field(default=None, exclude=True)
    transcribed_path: str | None = Field(default=None, exclude=True)


class NewLibrarySource(BaseModel):
    id: UUID
    owner: UUID
    name: str
    kind: str
    dedupe_key: str
    url: str | None
    size_bytes: int | None
    storage_path: str
    capture: str | None = None
    starter: bool = False
    page_count: int | None = None
    duration_seconds: float | None = None


class StarterRef(BaseModel):
    """Account's settings row "starter_notebook": the notebook every new
    user gets a copy of, and its owner (the admin who built it)."""

    owner_id: UUID
    notebook_id: UUID


class StarterSource(BaseModel):
    """A source of the starter notebook to copy: its library row and its
    link id there."""

    link_id: UUID
    library: LibrarySource


class StarterCopy(BaseModel):
    """One user's copy of the starter notebook, prepared: the stored
    objects are copied already (keys below), the rows are not."""

    owner: UUID
    source_notebook: UUID
    notebook_id: UUID
    title: str
    # (source, new library id, new link id, storage key, converted key,
    # snapshot key)
    sources: list[tuple[StarterSource, UUID, UUID, str | None, str | None, str | None]]
    # A copy made on request: starter sources the owner still has (by their
    # dedupe key) are linked, restored from the trash if need be, instead of
    # copied: (source, the owner's library id, new link id).
    reuse: list[tuple[StarterSource, UUID, UUID]] = []


class ChunkText(BaseModel):
    """One chunk as read: its id and `index` (`chunks.idx`, what a citation
    carries as `chunk_id` / `chunk_index`), its page (PDFs), its text."""

    chunk_id: UUID
    index: int
    page: int | None
    text: str
    # The vision model read it (an image, or a PDF page read by vision);
    # set by the API from the source's read_by and vision_pages.
    vision: bool = False


# Family rule: after three attempts a job is failed with its last error.
MAX_ATTEMPTS = 3
STALLED = f"processing did not finish in {MAX_ATTEMPTS} attempts (the worker stopped or hung)"


class Repository(Protocol):
    def list_notebooks(self, owner: UUID) -> list[OwnedNotebook]: ...

    def create_notebook(self, owner: UUID, title: str) -> OwnedNotebook: ...

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> OwnedNotebook | None: ...

    def rename_notebook(self, owner: UUID, notebook_id: UUID, title: str) -> OwnedNotebook | None:
        """The owner's notebook with its new title; None when it is not theirs."""
        ...

    def share_notebook(self, owner: UUID, notebook_id: UUID) -> str | None:
        """The notebook's share token, made on the first call and kept after
        (sharing twice gives the same link); None when it is not theirs."""
        ...

    def unshare_notebook(self, owner: UUID, notebook_id: UUID) -> bool:
        """Drop the token: the old link stops working. False when the
        notebook is not theirs."""
        ...

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> None:
        """Delete the notebook: its links go, its library sources stay in
        the library, generated ones included (rag's outputs live on with
        their origin title)."""
        ...

    # -- sources: library sources as linked into a notebook ---------------

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]: ...

    def get_source(self, source_id: UUID) -> StoredSource | None: ...

    def link_source(self, notebook_id: UUID, library_id: UUID) -> tuple[StoredSource, bool]:
        """Link a library source into a notebook; returns the link and
        whether it is new (False: it was already in this notebook)."""
        ...

    def detach_source(self, source_id: UUID) -> None:
        """Remove the link; the library source stays, generated ones too."""
        ...

    def linkable(self, owner: UUID, library_id: UUID) -> bool:
        """The owner's library source can be linked into a notebook: in the
        library (not trashed), or a ready generated one."""
        ...

    def link_many(self, owner: UUID, notebook_id: UUID, library_ids: list[UUID]) -> LinkResult:
        """Link the owner's linkable library sources into the notebook in
        one transaction, in the order given. When any id is not linkable for
        the owner (unknown, someone else's, trashed, an output not ready),
        nothing is linked and those ids are `missing`."""
        ...

    def list_generated(self, owner: UUID) -> list[LibraryEntry]:
        """The owner's ready generated library sources (rag's outputs, not
        trashed), newest first, each with its origin notebook."""
        ...

    # -- the library ---------------------------------------------------------

    def find_library_source(self, owner: UUID, dedupe_key: str) -> LibrarySource | None: ...

    def create_library_source(self, new: NewLibrarySource) -> LibrarySource:
        """Insert a library source in `processing`; when the owner already
        has one with this dedupe key (a concurrent upload), return that one."""
        ...

    def retry_library_source(self, library_id: UUID) -> None:
        """A failed library source uploaded again: back to `added`, read
        again when it is used."""
        ...

    def request_refetch(
        self, library_id: UUID, estimate_cents: Decimal | None = None, funded: bool = False
    ) -> LibrarySource | None:
        """Ask for a web page to be fetched again: a read current version
        goes to `processing` with `refetch_requested_at` set (the worker
        compares and either keeps it or makes a new version); an unread or
        failed one is simply queued. None when it is no web page, an older
        version, or being read already."""
        ...

    def set_fetched(
        self,
        library_id: UUID,
        content_hash: str,
        final_url: str | None,
        snapshot_path: str | None,
    ) -> None:
        """A web page was read: when, the hash of its extracted text, the
        address after redirects and the key of its snapshot."""
        ...

    def set_read_by(
        self,
        library_id: UUID,
        read_by: dict[str, str | None] | None,
        vision_pages: list[int] | None,
    ) -> None:
        """Which models made the source's text, and the PDF pages the vision
        model read; None for both when no model did."""
        ...

    def refetch_unchanged(
        self,
        library_id: UUID,
        snapshot_path: str | None = None,
        final_url: str | None = None,
    ) -> None:
        """The page is as it was: ready again, `checked_at` now, no charge;
        `fetched_at` and an existing snapshot stay. A version read before
        snapshots existed gets `snapshot_path` and `final_url` now (the same
        text, so still a snapshot of what was read)."""
        ...

    def new_version(self, library_id: UUID) -> UUID:
        """The page changed: in one transaction a new row `version + 1` takes
        the dedupe key and every link of the old one and is queued; the old
        row is ready again, read-only (`superseded_by`), its chunks kept.
        Returns the new id."""
        ...

    def queue_for_processing(
        self,
        owner: UUID,
        library_ids: list[UUID],
        estimates: dict[UUID, Decimal] | None = None,
        funded: bool = False,
    ) -> ProcessResult:
        """Move the owner's `added` library sources to `processing`, so a
        worker reads them; the others are left as they are. When any id is
        not the owner's (unknown, someone else's, trashed), nothing is
        queued and those ids are `missing`. Each queued row stores its
        estimated maximum (`funded_cents`); `funded` marks them funded at
        request (`funded_request_at`)."""
        ...

    def is_seeded(self, owner: UUID) -> bool:
        """The owner has been considered for the starter notebook already."""
        ...

    def starter_ref(self) -> StarterRef | None:
        """Account's settings row "starter_notebook"; None when there is none
        or it is malformed."""
        ...

    def starter_sources(self, ref: StarterRef) -> list[StarterSource] | None:
        """The uploads linked into the starter notebook (not trashed, ready,
        never generated rows: rag copies the outputs); None when the
        notebook does not exist or is not its owner's."""
        ...

    def copy_starter(self, plan: StarterCopy) -> dict[str, dict[str, str]] | None:
        """Write the user's copy in one transaction: claim the seed mark,
        the notebook, the library rows (ready, flagged starter), their links
        and their chunks with embeddings, and rag's `output_copies` row for
        the outputs. Returns the id maps written there, or None when the
        owner was considered already or has entries of their own (nothing
        written)."""
        ...

    def starter_copy_wait(self, owner: UUID) -> int:
        """Seconds until the owner may have the starter copied again on
        request (0: now)."""
        ...

    def has_starter_notebook(self, owner: UUID) -> bool:
        """Does the owner hold a notebook made as a starter copy."""
        ...

    def owned_by_dedupe_key(self, owner: UUID, keys: list[str]) -> dict[str, UUID]:
        """The owner's library rows (trashed ones included) with these dedupe
        keys, by key."""
        ...

    def recreate_starter(self, plan: StarterCopy) -> dict[str, dict[str, str]] | None:
        """A copy made on request, in one transaction like `copy_starter`,
        reusing `plan.reuse`; None when another copy was made within the
        hour (nothing written)."""
        ...

    def list_library(self, owner: UUID) -> list[LibraryEntry]: ...

    def get_library_entry(self, owner: UUID, library_id: UUID) -> LibraryEntry | None: ...

    def trash_library_source(self, owner: UUID, library_id: UUID) -> bool:
        """Move to the trash: `deleted_at` set, removed from every notebook,
        chunks and object kept. False when there is no such active entry."""
        ...

    def list_trash(self, owner: UUID) -> list[TrashEntry]: ...

    def restore_library_source(self, owner: UUID, library_id: UUID) -> bool:
        """Back from the trash into the library (in no notebook)."""
        ...

    def purge_library_source(self, owner: UUID, library_id: UUID) -> tuple[bool, list[str]]:
        """Delete a trashed entry now (chunks cascade); returns whether it
        was in the trash and its storage keys (the original, and a
        converted recording) for the caller to remove."""
        ...

    def user_object_keys(self, owner: UUID) -> list[str]:
        """Every stored object of the owner's library, trash included (the
        originals and converted recordings); generated rows' objects are
        rag's."""
        ...

    def delete_user_data(self, owner: UUID) -> None:
        """Delete the owner's library rows (generated ones included, chunks
        cascade), notebooks (their links and rag's rows cascade) and seed
        mark, in one transaction."""
        ...

    def purge_expired(self) -> list[str]:
        """Delete every trashed entry whose owner's retention has elapsed;
        returns their storage keys."""
        ...

    # -- the worker ---------------------------------------------------------

    def get_library_source(self, library_id: UUID) -> LibrarySource | None: ...

    def first_notebook(self, library_id: UUID) -> UUID | None:
        """The notebook it was first added to, for the usage rows."""
        ...

    def set_library_status(
        self, library_id: UUID, status: str, error: str | None = None
    ) -> None: ...

    def release_for_retry(self, library_id: UUID, error: str, delay_seconds: float) -> None:
        """A transient failure: keep `processing` with the error, drop the
        claim, and let no worker take it before `delay_seconds` from now."""
        ...

    def claim_library_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        """Claim one unprocessed library source for this worker and return
        its id, or None when the queue is empty. A claim older than
        `stale_after_seconds` counts as unprocessed again (its worker died),
        unless it has had MAX_ATTEMPTS: then it is failed, so a source that
        kills or hangs its worker cannot take every worker in turn.
        Generated rows are rag's and never claimed; trashed ones wait."""
        ...

    def release_waiting(self, library_id: UUID) -> None:
        """Release the claim without counting the attempt: the owner ran out
        of credit, or the pricing rules lost their exchange rate. The claim
        query skips the source until it can be paid for again."""
        ...

    def refresh_claim(self, library_id: UUID) -> None:
        """The worker is still at it: move `claimed_at` to now, so a long
        job is not taken over as stale while it makes progress."""
        ...

    def set_library_summary(self, library_id: UUID, summary: str) -> None: ...

    def list_chunks(self, library_id: UUID, offset: int, limit: int) -> tuple[int, list[ChunkText]]:
        """The library source's chunks in order, a page of them, and how many
        there are in all."""
        ...

    def set_transcribed_path(self, library_id: UUID, key: str) -> None:
        """The stored converted recording of an audio source."""
        ...

    def replace_chunks(
        self, library_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None: ...

    def record_usage(
        self,
        user_id: UUID,
        notebook_id: UUID | None,
        action: str,
        action_id: UUID,
        usage: Usage,
    ) -> UsageRecord:
        """Book one model call of a user action (core's `record_usage`: cost
        from the model prices, charge from the pricing rules)."""
        ...

    def pricing_rules(self) -> PricingRules:
        """Account's pricing rules (settings row, cached 30 s)."""
        ...

    def has_exchange_rate(self) -> bool:
        """Do the pricing rules (account's settings row, cached 30 s) have
        `usd_per_eur`: without it no model call can be booked."""
        ...

    def balance_cents(self, user_id: UUID) -> Decimal:
        """The user's balance (core's: credits minus charges)."""
        ...

    def held_cents(self, owner: UUID) -> Decimal:
        """What the owner's started work holds of the balance: the estimated
        maxima of their funded reads still waiting, plus what rag's waiting
        and processing outputs reserve (`outputs.reserved_cents`) and the
        estimated maxima of their running plans' explain steps."""
        ...

    def has_credit(self, user_id: UUID) -> bool:
        """May this user start a model call: a positive balance, for every
        user alike, admins included (core's `has_credit`)."""
        ...

    def admin_role(self, user_id: UUID) -> Role:
        """`users.role` (core's `admin_role`): "user", "viewer" or "admin";
        "user" without a user row."""
        ...

    def admin_stats(self, stale_after_seconds: int) -> AdminStats:
        """Counts over all users for the admin overview; read-only."""
        ...

    def admin_daily(self, days: int) -> list[DailyStats]:
        """One entry per UTC day for the last `days` days including today,
        oldest first, days without sources included; read-only."""
        ...


class AdminStats(BaseModel):
    """`GET /admin/stats` over library sources (generated ones excluded). A
    `processing` one is a pending job until a worker claims it (or its claim
    is stale) and a running job while claimed; `source_bytes` counts rows
    that stored their size."""

    sources: dict[str, int]
    jobs: dict[str, int]
    chunks: int
    source_bytes: int


KINDS = ("pdf", "text", "url", "image", "audio")


class DailyStats(BaseModel):
    """`GET /admin/stats/daily`: library sources created that day (UTC),
    generated ones excluded; `failed` counts those of them now failed."""

    day: date
    sources_created: int
    by_kind: dict[str, int]
    failed: int


class PostgresRepository:
    def __init__(
        self,
        database_url: str,
        *,
        model_prices: ModelPrices,
        service: Literal["ingest", "rag"] = "ingest",
        min_size: int = 1,
        max_size: int = 8,
        connect_timeout: float = 15.0,
    ) -> None:
        from pgvector.psycopg import register_vector
        from psycopg_pool import ConnectionPool

        self._prices = model_prices
        self._service = service
        # Account's pricing rules (margins, fees), re-read every 30 s.
        self._rules = PricingRulesCache()
        self._pool = ConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            configure=register_vector,
            open=True,
        )
        # Fail at startup when the database is unreachable, instead of
        # serving 500s while the pool retries in the background.
        self._pool.wait(timeout=connect_timeout)
        # A connection source for core's PostgresRateLimitStore.
        self.connection = self._pool.connection

    def close(self) -> None:
        self._pool.close()

    def _one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        from psycopg.rows import dict_row

        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def _all(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from psycopg.rows import dict_row

        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    _NOTEBOOK = "id, title, created_at, share_token, starter"

    def list_notebooks(self, owner: UUID) -> list[OwnedNotebook]:
        rows = self._all(
            f"select {self._NOTEBOOK} from notebooks where owner = %(owner)s "
            "order by created_at desc",
            {"owner": owner},
        )
        return [OwnedNotebook(**row) for row in rows]

    def create_notebook(self, owner: UUID, title: str) -> OwnedNotebook:
        row = self._one(
            "insert into notebooks (id, owner, title) values (%(id)s, %(owner)s, %(title)s) "
            f"returning {self._NOTEBOOK}",
            {"id": uuid4(), "owner": owner, "title": title},
        )
        assert row is not None
        return OwnedNotebook(**row)

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> OwnedNotebook | None:
        row = self._one(
            f"select {self._NOTEBOOK} from notebooks where id = %(id)s and owner = %(owner)s",
            {"id": notebook_id, "owner": owner},
        )
        return OwnedNotebook(**row) if row else None

    def rename_notebook(self, owner: UUID, notebook_id: UUID, title: str) -> OwnedNotebook | None:
        row = self._one(
            "update notebooks set title = %(title)s where id = %(id)s and owner = %(owner)s "
            f"returning {self._NOTEBOOK}",
            {"id": notebook_id, "owner": owner, "title": title},
        )
        return OwnedNotebook(**row) if row else None

    def share_notebook(self, owner: UUID, notebook_id: UUID) -> str | None:
        row = self._one(
            "update notebooks set share_token = coalesce(share_token, %(token)s) "
            "where id = %(id)s and owner = %(owner)s returning share_token",
            {"id": notebook_id, "owner": owner, "token": secrets.token_urlsafe(24)},
        )
        return str(row["share_token"]) if row else None

    def unshare_notebook(self, owner: UUID, notebook_id: UUID) -> bool:
        row = self._one(
            "update notebooks set share_token = null where id = %(id)s and owner = %(owner)s "
            "returning id",
            {"id": notebook_id, "owner": owner},
        )
        return row is not None

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> None:
        # Links cascade; rag's outputs keep their generated library source
        # (outputs.notebook_id is set null by rag's foreign key).
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "delete from notebooks where id = %(id)s and owner = %(owner)s",
                {"id": notebook_id, "owner": owner},
            )

    # -- sources ---------------------------------------------------------------

    _SELECT_SOURCES = (
        "select s.id, s.notebook_id, l.name, l.kind, l.status, l.error, s.created_at, "
        "l.id as library_id, l.owner, l.storage_path, l.url, l.summary, l.attempts, l.size_bytes, "
        "l.capture, l.starter, l.transcribed_path, l.version, l.fetched_at, l.final_url, "
        "l.checked_at, l.snapshot_path, l.funded_request_at, l.funded_cents, "
        "l.read_by, l.vision_pages, l.page_count "
        "from sources s join library_sources l on l.id = s.library_source_id"
    )

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]:
        # A generated row's link in its origin notebook (rag writes it under
        # the row's own id) is the output itself, listed among the outputs:
        # never a source there. Links into other notebooks have ids of their
        # own and are listed.
        rows = self._all(
            f"{self._SELECT_SOURCES} where s.notebook_id = %(id)s "
            "and not (l.kind = 'generated' and s.id = l.id) order by s.created_at, s.id",
            {"id": notebook_id},
        )
        return [StoredSource(**row) for row in rows]

    def get_source(self, source_id: UUID) -> StoredSource | None:
        row = self._one(f"{self._SELECT_SOURCES} where s.id = %(id)s", {"id": source_id})
        return StoredSource(**row) if row else None

    def link_source(self, notebook_id: UUID, library_id: UUID) -> tuple[StoredSource, bool]:
        row = self._one(
            "insert into sources (id, notebook_id, library_source_id) "
            "values (%(id)s, %(nb)s, %(lib)s) "
            "on conflict (notebook_id, library_source_id) do nothing returning id",
            {"id": uuid4(), "nb": notebook_id, "lib": library_id},
        )
        created = row is not None
        if row is None:
            row = self._one(
                "select id from sources where notebook_id = %(nb)s and library_source_id = %(lib)s",
                {"nb": notebook_id, "lib": library_id},
            )
        assert row is not None
        source = self.get_source(row["id"])
        assert source is not None
        return source, created

    def detach_source(self, source_id: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("delete from sources where id = %(id)s", {"id": source_id})

    def linkable(self, owner: UUID, library_id: UUID) -> bool:
        row = self._one(
            "select 1 as ok from library_sources l where l.id = %(id)s and l.owner = %(owner)s "
            "and l.deleted_at is null and (l.kind <> 'generated' or l.status = 'ready')",
            {"id": library_id, "owner": owner},
        )
        return row is not None

    def link_many(self, owner: UUID, notebook_id: UUID, library_ids: list[UUID]) -> LinkResult:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "select l.id from library_sources l where l.id = any(%(ids)s) "
                "and l.owner = %(owner)s and l.deleted_at is null "
                "and (l.kind <> 'generated' or l.status = 'ready') for share",
                {"ids": library_ids, "owner": owner},
            )
            found = {row[0] for row in cur.fetchall()}
            missing = [i for i in library_ids if i not in found]
            if missing:
                return LinkResult(missing=missing)
            # sources_link_idx (notebook_id, library_source_id) is unique:
            # a link another request made meanwhile is "already", never doubled.
            cur.execute(
                "insert into sources (id, notebook_id, library_source_id) "
                "select gen_random_uuid(), %(nb)s, unnest(%(ids)s::uuid[]) "
                "on conflict (notebook_id, library_source_id) do nothing "
                "returning library_source_id",
                {"nb": notebook_id, "ids": library_ids},
            )
            new = {row[0] for row in cur.fetchall()}
        return LinkResult(
            added=[i for i in library_ids if i in new],
            already=[i for i in library_ids if i not in new],
        )

    # The origin of an output is rag's: outputs.source_id is the generated
    # row, outputs.notebook_id the notebook it was made in (null once that
    # is deleted), outputs.origin_title the title it had then. Read from
    # outputs, not from a link: the user can unlink an output from its
    # origin notebook.
    _GENERATED_ENTRIES = """
    select l.id, l.name, l.kind, l.status, l.error, l.size_bytes, l.url, l.created_at,
           l.capture, l.starter, l.storage_path, l.transcribed_path,
           o.id as output_id, o.notebook_id as origin_id,
           coalesce(origin.title, o.origin_title) as origin_title,
           coalesce(json_agg(json_build_object('id', n.id, 'title', n.title, 'source_id', s.id)
                             order by s.created_at) filter (where s.id is not null),
                    '[]') as notebooks
      from library_sources l
      left join outputs o on o.source_id = l.id
      left join notebooks origin on origin.id = o.notebook_id
      left join sources s on s.library_source_id = l.id
      left join notebooks n on n.id = s.notebook_id
     where l.owner = %(owner)s and l.kind = 'generated' and l.status = 'ready'
       and l.deleted_at is null
     group by l.id, o.id, o.notebook_id, o.origin_title, origin.title
     order by l.created_at desc, l.id
    """

    def list_generated(self, owner: UUID) -> list[LibraryEntry]:
        rows = self._all(self._GENERATED_ENTRIES, {"owner": owner})
        return [_generated_entry(row) for row in rows]

    # -- the library -----------------------------------------------------------

    # Every library read filters with this: generated rows are rag's.
    _LISTED = "l.kind <> 'generated'"
    # May the worker process this row: its owner has a positive balance
    # (core's expression: credits minus charges).
    # or its read was funded when it was asked for (funded_request_at), or
    # the balance, less what the owner's started work holds, covers this
    # read's estimated maximum (funded_cents, stored when it was queued; 0
    # for rows queued before estimates existed). Started work is the
    # owner's other funded reads still waiting, rag's waiting and
    # processing outputs (`outputs.reserved_cents`) and the explain steps
    # of their running agent plans: the sum rag holds, so neither service
    # lets through what the other already counts as taken.
    _RESERVED = (
        "coalesce((select sum(o.reserved_cents) from outputs o "
        "where o.owner = {owner} and o.status in ('waiting', 'processing') "
        "and o.deleted_at is null), 0) + "
        "coalesce((select sum((s->'estimate'->>'max')::numeric) "
        "from plans p, jsonb_array_elements(p.steps) s "
        "where p.owner = {owner} and p.status = 'running' "
        "and s->>'tool' = 'explain_output' and s->>'state' in ('waiting', 'running')), 0)"
    )
    # One parenthesised sum: the claim subtracts it as a whole.
    _HELD = (
        "(coalesce((select sum(f.funded_cents) from library_sources f "
        "where f.owner = l.owner and f.funded_request_at is not null "
        "and f.status = 'processing' and f.deleted_at is null and f.id <> l.id), 0) + "
        + _RESERVED.format(owner="l.owner")
        + ")"
    )
    _FUNDED = (
        f"(l.funded_request_at is not null or ({funded_sql('l.owner')} and "
        f"{balance_sql('l.owner')} - {_HELD} >= coalesce(l.funded_cents, 0)))"
    )
    _LIBRARY_COLUMNS = (
        "l.id, l.owner, l.name, l.kind, l.dedupe_key, l.url, l.size_bytes, l.storage_path, "
        "l.status, l.error, l.summary, l.attempts, l.created_at, l.deleted_at, l.capture, "
        "l.starter, l.transcribed_path, l.page_count, l.duration_seconds, l.version, "
        "l.fetched_at, l.content_hash, l.refetch_requested_at, l.superseded_by, "
        "l.snapshot_path, l.final_url, l.checked_at, l.funded_request_at, l.funded_cents, "
        "l.read_by, l.vision_pages"
    )
    # Library sources in the library (not in the trash).
    # Older versions of a web page are kept read-only, out of every list.
    _ACTIVE = f"{_LISTED} and l.deleted_at is null and l.superseded_by is null"
    # Days a deleted entry stays in the trash: account's per-user preference,
    # read like core reads users.role; 14 without a user row or a number.
    _TRASH_DAYS = (
        "greatest(0, coalesce((select case when jsonb_typeof(u.preferences -> 'trash_days')"
        " = 'number' then floor((u.preferences ->> 'trash_days')::numeric)::int end"
        " from users u where u.id = l.owner), 14))"
    )

    def find_library_source(self, owner: UUID, dedupe_key: str) -> LibrarySource | None:
        row = self._one(
            f"select {self._LIBRARY_COLUMNS} from library_sources l "
            f"where l.owner = %(owner)s and l.dedupe_key = %(key)s and {self._LISTED}",
            {"owner": owner, "key": dedupe_key},
        )
        return LibrarySource(**row) if row else None

    def create_library_source(self, new: NewLibrarySource) -> LibrarySource:
        self._one(
            "insert into library_sources (id, owner, name, kind, dedupe_key, url, size_bytes, "
            "storage_path, capture, starter, page_count, duration_seconds, status) values "
            "(%(id)s, %(owner)s, %(name)s, %(kind)s, %(key)s, %(url)s, %(size)s, %(path)s, "
            "%(capture)s, %(starter)s, %(pages)s, %(seconds)s, 'added') "
            "on conflict (owner, dedupe_key) where dedupe_key is not null do nothing returning id",
            {
                "id": new.id,
                "owner": new.owner,
                "name": new.name,
                "kind": new.kind,
                "key": new.dedupe_key,
                "url": new.url,
                "size": new.size_bytes,
                "path": new.storage_path,
                "capture": new.capture,
                "starter": new.starter,
                "pages": new.page_count,
                "seconds": new.duration_seconds,
            },
        )
        found = self.find_library_source(new.owner, new.dedupe_key)
        assert found is not None
        return found

    def request_refetch(
        self, library_id: UUID, estimate_cents: Decimal | None = None, funded: bool = False
    ) -> LibrarySource | None:
        row = self._one(
            "update library_sources set status = 'processing', error = null, attempts = 0, "
            "retry_at = null, claimed_at = null, claimed_by = null, "
            "refetch_requested_at = case when status = 'ready' then now() end, "
            "funded_request_at = case when %(funded)s then now() end, "
            "funded_cents = %(estimate)s::numeric "
            "where id = %(id)s and kind = 'url' and superseded_by is null "
            "and deleted_at is null and status in ('ready', 'added', 'failed') returning id",
            {"id": library_id, "funded": funded, "estimate": estimate_cents},
        )
        return self.get_library_source(library_id) if row else None

    def set_fetched(
        self,
        library_id: UUID,
        content_hash: str,
        final_url: str | None,
        snapshot_path: str | None,
    ) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set fetched_at = now(), checked_at = now(), "
                "content_hash = %(hash)s, final_url = %(final)s, snapshot_path = %(snap)s "
                "where id = %(id)s",
                {
                    "id": library_id,
                    "hash": content_hash,
                    "final": final_url,
                    "snap": snapshot_path,
                },
            )

    def set_read_by(
        self,
        library_id: UUID,
        read_by: dict[str, str | None] | None,
        vision_pages: list[int] | None,
    ) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set read_by = %(read_by)s::jsonb, "
                "vision_pages = %(pages)s where id = %(id)s",
                {
                    "id": library_id,
                    "read_by": json.dumps(read_by) if read_by is not None else None,
                    "pages": vision_pages,
                },
            )

    def refetch_unchanged(
        self,
        library_id: UUID,
        snapshot_path: str | None = None,
        final_url: str | None = None,
    ) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set status = 'ready', checked_at = now(), "
                "refetch_requested_at = null, claimed_at = null, claimed_by = null, error = null, "
                "funded_request_at = null, funded_cents = null, "
                "snapshot_path = coalesce(snapshot_path, %(snap)s), "
                "final_url = coalesce(final_url, %(final)s) "
                "where id = %(id)s",
                {"id": library_id, "snap": snapshot_path, "final": final_url},
            )

    def new_version(self, library_id: UUID) -> UUID:
        new_id = uuid4()
        with self._pool.connection() as conn, conn.cursor() as cur:
            # The dedupe key is unique per owner: the old row gives it up first.
            cur.execute(
                "select dedupe_key, funded_request_at, funded_cents from library_sources "
                "where id = %(id)s for update",
                {"id": library_id},
            )
            row = cur.fetchone()
            key, funded_at, funded = row if row else (None, None, None)
            cur.execute(
                "update library_sources set dedupe_key = null, status = 'ready', "
                "refetch_requested_at = null, claimed_at = null, claimed_by = null, error = null, "
                "funded_request_at = null, funded_cents = null "
                "where id = %(id)s",
                {"id": library_id},
            )
            cur.execute(
                "insert into library_sources (id, owner, name, kind, dedupe_key, url, size_bytes, "
                "storage_path, starter, status, version, funded_request_at, funded_cents) "
                "select %(new)s, owner, name, kind, %(key)s, url, size_bytes, storage_path, "
                "starter, 'processing', version + 1, %(funded_at)s, %(funded)s "
                "from library_sources where id = %(id)s",
                {
                    "new": new_id,
                    "id": library_id,
                    "key": key,
                    "funded_at": funded_at,
                    "funded": funded,
                },
            )
            cur.execute(
                "update library_sources set superseded_by = %(new)s where id = %(id)s",
                {"new": new_id, "id": library_id},
            )
            cur.execute(
                "update sources set library_source_id = %(new)s where library_source_id = %(id)s",
                {"new": new_id, "id": library_id},
            )
        return new_id

    def queue_for_processing(
        self,
        owner: UUID,
        library_ids: list[UUID],
        estimates: dict[UUID, Decimal] | None = None,
        funded: bool = False,
    ) -> ProcessResult:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "select l.id from library_sources l where l.id = any(%(ids)s) "
                "and l.owner = %(owner)s and l.deleted_at is null for update",
                {"ids": library_ids, "owner": owner},
            )
            found = {row[0] for row in cur.fetchall()}
            missing = [i for i in library_ids if i not in found]
            if missing:
                return ProcessResult(missing=missing)
            cur.execute(
                "update library_sources set status = 'processing' "
                "where id = any(%(ids)s) and status = 'added' returning id",
                {"ids": library_ids},
            )
            queued = {row[0] for row in cur.fetchall()}
            for library_id, cents in (estimates or {}).items():
                if library_id in queued:
                    cur.execute(
                        "update library_sources set funded_cents = %(cents)s, "
                        "funded_request_at = case when %(funded)s then now() end "
                        "where id = %(id)s",
                        {"id": library_id, "cents": cents, "funded": funded},
                    )
        return ProcessResult(
            queued=[i for i in library_ids if i in queued],
            unchanged=[i for i in library_ids if i not in queued],
        )

    def retry_library_source(self, library_id: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set status = 'added', error = null, attempts = 0, "
                "claimed_at = null, claimed_by = null, retry_at = null "
                "where id = %(id)s and status = 'failed'",
                {"id": library_id},
            )

    def is_seeded(self, owner: UUID) -> bool:
        row = self._one(
            "select exists (select 1 from library_seeds where owner = %(owner)s) as seeded",
            {"owner": owner},
        )
        return bool(row and row["seeded"])

    def starter_ref(self) -> StarterRef | None:
        row = self._one("select value from settings where key = 'starter_notebook'", {})
        if row is None or not isinstance(row["value"], dict):
            return None
        try:
            return StarterRef.model_validate(row["value"])
        except ValueError:
            log.warning("settings 'starter_notebook' is malformed; no starter is seeded")
            return None

    def starter_sources(self, ref: StarterRef) -> list[StarterSource] | None:
        if self.get_notebook(ref.owner_id, ref.notebook_id) is None:
            return None
        rows = self._all(
            f"select s.id as link_id, {self._LIBRARY_COLUMNS} from sources s "
            "join library_sources l on l.id = s.library_source_id "
            "where s.notebook_id = %(nb)s and l.owner = %(owner)s and l.kind <> 'generated' "
            "and l.status = 'ready' and l.deleted_at is null order by s.created_at, s.id",
            {"nb": ref.notebook_id, "owner": ref.owner_id},
        )
        return [
            StarterSource(link_id=row.pop("link_id"), library=LibrarySource(**row)) for row in rows
        ]

    def copy_starter(self, plan: StarterCopy) -> dict[str, dict[str, str]] | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into library_seeds (owner) values (%(owner)s) "
                "on conflict (owner) do nothing returning owner",
                {"owner": plan.owner},
            )
            if cur.fetchone() is None:
                return None
            cur.execute(
                f"select exists (select 1 from library_sources l "
                f"where l.owner = %(owner)s and {self._LISTED})",
                {"owner": plan.owner},
            )
            row = cur.fetchone()
            if row and row[0]:
                return None  # the mark stays: an owner with entries is not seeded
            return self._write_starter(cur, plan)

    # The limit on copies made on request (the first sign-in's is free).
    STARTER_COPY_INTERVAL_SECONDS = 3600

    def starter_copy_wait(self, owner: UUID) -> int:
        row = self._one(
            "select greatest(0, ceil(extract(epoch from copied_at - now()) + %(interval)s))::int "
            "as wait from library_seeds where owner = %(owner)s and copied_at is not null",
            {"owner": owner, "interval": self.STARTER_COPY_INTERVAL_SECONDS},
        )
        return int(row["wait"]) if row else 0

    def has_starter_notebook(self, owner: UUID) -> bool:
        row = self._one(
            "select exists (select 1 from notebooks where owner = %(owner)s and starter) as found",
            {"owner": owner},
        )
        return bool(row and row["found"])

    def owned_by_dedupe_key(self, owner: UUID, keys: list[str]) -> dict[str, UUID]:
        rows = self._all(
            f"select l.dedupe_key, l.id from library_sources l where l.owner = %(owner)s "
            f"and {self._LISTED} and l.dedupe_key = any(%(keys)s)",
            {"owner": owner, "keys": keys},
        )
        return {str(r["dedupe_key"]): r["id"] for r in rows}

    def recreate_starter(self, plan: StarterCopy) -> dict[str, dict[str, str]] | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into library_seeds (owner, copied_at) values (%(owner)s, now()) "
                "on conflict (owner) do update set copied_at = now() "
                "where library_seeds.copied_at is null "
                "or library_seeds.copied_at <= now() - make_interval(secs => %(interval)s) "
                "returning owner",
                {"owner": plan.owner, "interval": self.STARTER_COPY_INTERVAL_SECONDS},
            )
            if cur.fetchone() is None:
                return None  # another copy within the hour
            return self._write_starter(cur, plan)

    def _write_starter(self, cur: Any, plan: StarterCopy) -> dict[str, dict[str, str]]:
        """The notebook, its copied and its reused sources, their chunks and
        rag's handover row, inside the caller's transaction."""
        source_map: dict[str, str] = {}
        chunk_map: dict[str, str] = {}
        cur.execute(
            "insert into notebooks (id, owner, title, starter) "
            "values (%(id)s, %(owner)s, %(title)s, true)",
            {"id": plan.notebook_id, "owner": plan.owner, "title": plan.title},
        )
        for source, library_id, link_id in plan.reuse:
            # The owner's own copy of this starter source: back from the
            # trash if it is there, linked, its chunks mapped by index.
            cur.execute(
                "update library_sources set deleted_at = null "
                "where id = %(id)s and owner = %(owner)s",
                {"id": library_id, "owner": plan.owner},
            )
            cur.execute(
                "insert into sources (id, notebook_id, library_source_id) "
                "values (%(id)s, %(nb)s, %(lib)s)",
                {"id": link_id, "nb": plan.notebook_id, "lib": library_id},
            )
            cur.execute(
                "select o.id, n.id from chunks o join chunks n "
                "on n.library_source_id = %(new)s and n.idx = o.idx "
                "where o.library_source_id = %(old)s",
                {"old": source.library.id, "new": library_id},
            )
            chunk_map.update({str(o): str(n) for o, n in cur.fetchall()})
            source_map[str(source.link_id)] = str(link_id)
            source_map[str(source.library.id)] = str(library_id)
        for source, library_id, link_id, key, converted, snapshot in plan.sources:
            old = source.library
            cur.execute(
                "insert into library_sources (id, owner, name, kind, dedupe_key, url, "
                "size_bytes, storage_path, transcribed_path, capture, starter, status, "
                "summary, page_count, duration_seconds, version, fetched_at, checked_at, "
                "content_hash, final_url, snapshot_path, read_by, vision_pages) values "
                "(%(id)s, %(owner)s, "
                "%(name)s, %(kind)s, %(key)s, %(url)s, %(size)s, %(path)s, %(converted)s, "
                "%(capture)s, true, 'ready', %(summary)s, %(pages)s, %(seconds)s, "
                "%(version)s, %(fetched)s, %(checked)s, %(hash)s, %(final)s, %(snapshot)s, "
                "%(read_by)s::jsonb, %(vision_pages)s)",
                {
                    "id": library_id,
                    "owner": plan.owner,
                    "name": old.name,
                    "kind": old.kind,
                    "key": old.dedupe_key,
                    "url": old.url,
                    "size": old.size_bytes,
                    "path": key,
                    "converted": converted,
                    "capture": old.capture,
                    "summary": old.summary,
                    "pages": old.page_count,
                    "seconds": old.duration_seconds,
                    "version": old.version,
                    "fetched": old.fetched_at,
                    "checked": old.checked_at,
                    "hash": old.content_hash,
                    "final": old.final_url,
                    "snapshot": snapshot,
                    "read_by": json.dumps(old.read_by) if old.read_by is not None else None,
                    "vision_pages": old.vision_pages,
                },
            )
            cur.execute(
                "insert into sources (id, notebook_id, library_source_id) "
                "values (%(id)s, %(nb)s, %(lib)s)",
                {"id": link_id, "nb": plan.notebook_id, "lib": library_id},
            )
            cur.execute("select id from chunks where library_source_id = %(lib)s", {"lib": old.id})
            old_chunks = [r[0] for r in cur.fetchall()]
            new_chunks = [uuid4() for _ in old_chunks]
            cur.execute(
                "insert into chunks (id, library_source_id, idx, page, text, embedding) "
                "select m.new_id, %(lib)s, c.idx, c.page, c.text, c.embedding "
                "from chunks c join unnest(%(old)s::uuid[], %(new)s::uuid[]) "
                "as m(old_id, new_id) on c.id = m.old_id",
                {"lib": library_id, "old": old_chunks, "new": new_chunks},
            )
            source_map[str(source.link_id)] = str(link_id)
            source_map[str(old.id)] = str(library_id)
            chunk_map.update({str(o): str(n) for o, n in zip(old_chunks, new_chunks, strict=True)})
        # rag's handover: its worker copies the starter's outputs into the
        # new notebook, remapping provenance through these maps.
        cur.execute(
            "insert into output_copies (target_notebook, source_notebook, owner, "
            "source_map, chunk_map) values (%(target)s, %(source)s, %(owner)s, "
            "%(sources)s::jsonb, %(chunks)s::jsonb)",
            {
                "target": plan.notebook_id,
                "source": plan.source_notebook,
                "owner": plan.owner,
                "sources": json.dumps(source_map),
                "chunks": json.dumps(chunk_map),
            },
        )
        return {"source_map": source_map, "chunk_map": chunk_map}

    _LIBRARY_ENTRIES = f"""
    select l.id, l.name, l.kind, l.status, l.error, l.size_bytes, l.url, l.created_at,
           l.capture, l.starter, l.storage_path, l.transcribed_path, l.version, l.fetched_at,
           l.final_url, l.checked_at, l.snapshot_path, l.funded_request_at, l.funded_cents,
           coalesce(json_agg(json_build_object('id', n.id, 'title', n.title, 'source_id', s.id)
                             order by s.created_at) filter (where s.id is not null),
                    '[]') as notebooks
      from library_sources l
      left join sources s on s.library_source_id = l.id
      left join notebooks n on n.id = s.notebook_id
     where l.owner = %(owner)s and {_ACTIVE} {{where}}
     group by l.id
     order by l.created_at desc, l.id
    """

    def list_library(self, owner: UUID) -> list[LibraryEntry]:
        rows = self._all(self._LIBRARY_ENTRIES.format(where=""), {"owner": owner})
        return [LibraryEntry(**row) for row in rows]

    def get_library_entry(self, owner: UUID, library_id: UUID) -> LibraryEntry | None:
        row = self._one(
            self._LIBRARY_ENTRIES.format(where="and l.id = %(id)s"),
            {"owner": owner, "id": library_id},
        )
        return LibraryEntry(**row) if row else None

    def trash_library_source(self, owner: UUID, library_id: UUID) -> bool:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"update library_sources l set deleted_at = now() "
                f"where l.id = %(id)s and l.owner = %(owner)s and {self._ACTIVE}",
                {"id": library_id, "owner": owner},
            )
            if cur.rowcount == 0:
                return False
            cur.execute("delete from sources where library_source_id = %(id)s", {"id": library_id})
            return True

    def list_trash(self, owner: UUID) -> list[TrashEntry]:
        rows = self._all(
            f"select l.id, l.name, l.kind, l.status, l.error, l.size_bytes, l.url, l.created_at, "
            f"l.capture, l.starter, l.storage_path, l.transcribed_path, l.version, l.fetched_at, "
            f"l.final_url, l.checked_at, l.snapshot_path, l.deleted_at, "
            f"l.deleted_at + make_interval(days => {self._TRASH_DAYS}) as purge_at "
            f"from library_sources l where l.owner = %(owner)s and {self._LISTED} "
            f"and l.deleted_at is not null order by l.deleted_at desc, l.id",
            {"owner": owner},
        )
        return [TrashEntry(**row) for row in rows]

    def restore_library_source(self, owner: UUID, library_id: UUID) -> bool:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"update library_sources l set deleted_at = null "
                f"where l.id = %(id)s and l.owner = %(owner)s and {self._LISTED} "
                f"and l.deleted_at is not null",
                {"id": library_id, "owner": owner},
            )
            return cur.rowcount > 0

    def purge_library_source(self, owner: UUID, library_id: UUID) -> tuple[bool, list[str]]:
        rows = self._all(
            f"with recursive gone(id) as ("
            f"  select l.id from library_sources l where l.id = %(id)s and l.owner = %(owner)s"
            f"  and {self._LISTED} and l.deleted_at is not null"
            f"  union select older.id from library_sources older join gone g"
            f"  on older.superseded_by = g.id) "
            f"delete from library_sources l using gone where l.id = gone.id "
            f"returning l.storage_path, l.transcribed_path, l.snapshot_path",
            {"id": library_id, "owner": owner},
        )
        return (bool(rows), list(dict.fromkeys(_keys(rows))))

    def user_object_keys(self, owner: UUID) -> list[str]:
        rows = self._all(
            "select l.storage_path, l.transcribed_path, l.snapshot_path from library_sources l "
            "where l.owner = %(owner)s and l.kind <> 'generated' order by l.created_at, l.id",
            {"owner": owner},
        )
        return _keys(rows)

    def delete_user_data(self, owner: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("delete from library_sources where owner = %(owner)s", {"owner": owner})
            cur.execute("delete from notebooks where owner = %(owner)s", {"owner": owner})
            cur.execute("delete from library_seeds where owner = %(owner)s", {"owner": owner})

    def purge_expired(self) -> list[str]:
        rows = self._all(
            f"with recursive gone(id) as ("
            f"  select l.id from library_sources l where {self._LISTED}"
            f"  and l.deleted_at is not null"
            f"  and l.deleted_at + make_interval(days => {self._TRASH_DAYS}) <= now()"
            f"  union select older.id from library_sources older join gone g"
            f"  on older.superseded_by = g.id) "
            f"delete from library_sources l using gone where l.id = gone.id "
            f"returning l.storage_path, l.transcribed_path, l.snapshot_path",
            {},
        )
        return list(dict.fromkeys(_keys(rows)))

    # -- the worker ------------------------------------------------------------

    def get_library_source(self, library_id: UUID) -> LibrarySource | None:
        row = self._one(
            f"select {self._LIBRARY_COLUMNS} from library_sources l where l.id = %(id)s",
            {"id": library_id},
        )
        return LibrarySource(**row) if row else None

    def first_notebook(self, library_id: UUID) -> UUID | None:
        row = self._one(
            "select notebook_id from sources where library_source_id = %(id)s "
            "order by created_at, id limit 1",
            {"id": library_id},
        )
        return row["notebook_id"] if row else None

    def set_library_status(self, library_id: UUID, status: str, error: str | None = None) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            # A read that ends (ready or failed) gives back what it held.
            cur.execute(
                "update library_sources set status = %(status)s, error = %(error)s, "
                "funded_request_at = case when %(status)s in ('ready', 'failed') then null "
                "else funded_request_at end, "
                "funded_cents = case when %(status)s in ('ready', 'failed') then null "
                "else funded_cents end "
                "where id = %(id)s",
                {"status": status, "error": error, "id": library_id},
            )

    # The queue: `processing` rows that nobody holds. FOR UPDATE SKIP LOCKED
    # lets any number of workers claim concurrently without a broker; the
    # claim itself is the row update, in the same statement. Generated rows
    # are written and finished by rag, never by this worker.
    # Processing needs credit: a source whose owner has none is not claimed
    # (the API shows it as waiting_for_credit) and is taken as soon as the
    # owner's balance is positive again.
    # Core's balance (ledger minus usage), per candidate owner.
    _CLAIM_SQL = f"""
    update library_sources
       set claimed_at = now(), claimed_by = %(worker)s, attempts = attempts + 1
     where id = (
        select l.id from library_sources l
         where l.status = 'processing' and l.kind <> 'generated' and l.deleted_at is null
           and (l.retry_at is null or l.retry_at <= now())
           and (l.claimed_at is null
                or l.claimed_at < now() - make_interval(secs => %(stale)s))
           and l.attempts < %(max)s
           and {_FUNDED}
         order by l.created_at
         for update of l skip locked
         limit 1)
    returning id
    """

    def release_waiting(self, library_id: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set claimed_at = null, claimed_by = null, "
                "attempts = greatest(attempts - 1, 0), error = null where id = %(id)s",
                {"id": library_id},
            )

    def release_for_retry(self, library_id: UUID, error: str, delay_seconds: float) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set error = %(error)s, claimed_at = null, "
                "retry_at = now() + make_interval(secs => %(delay)s) where id = %(id)s",
                {"error": error, "delay": delay_seconds, "id": library_id},
            )

    # A stale claim on a row that has had every attempt: its worker died or
    # hung each time, so the row is failed instead of handed out again.
    _FAIL_STALLED_SQL = """
    update library_sources
       set status = 'failed', error = %(error)s, claimed_at = null, claimed_by = null
     where status = 'processing' and kind <> 'generated' and attempts >= %(max)s
       and claimed_at < now() - make_interval(secs => %(stale)s)
    """

    def claim_library_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        params = {
            "worker": worker_id,
            "stale": stale_after_seconds,
            "max": MAX_ATTEMPTS,
            "error": STALLED,
        }
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(self._FAIL_STALLED_SQL, params)
            cur.execute(self._CLAIM_SQL, params)
            row = cur.fetchone()
            return row[0] if row else None

    def refresh_claim(self, library_id: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set claimed_at = now() "
                "where id = %(id)s and status = 'processing' and claimed_at is not null",
                {"id": library_id},
            )

    def set_library_summary(self, library_id: UUID, summary: str) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set summary = %(summary)s where id = %(id)s",
                {"summary": summary, "id": library_id},
            )

    def list_chunks(self, library_id: UUID, offset: int, limit: int) -> tuple[int, list[ChunkText]]:
        count = self._one(
            "select count(*) as n from chunks where library_source_id = %(lib)s",
            {"lib": library_id},
        )
        rows = self._all(
            "select id as chunk_id, idx as index, page, text from chunks "
            "where library_source_id = %(lib)s order by idx offset %(offset)s limit %(limit)s",
            {"lib": library_id, "offset": offset, "limit": limit},
        )
        return (int(count["n"]) if count else 0), [ChunkText(**row) for row in rows]

    def set_transcribed_path(self, library_id: UUID, key: str) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set transcribed_path = %(key)s where id = %(id)s",
                {"key": key, "id": library_id},
            )

    def replace_chunks(
        self, library_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        import numpy as np

        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("delete from chunks where library_source_id = %(id)s", {"id": library_id})
            cur.executemany(
                "insert into chunks (id, library_source_id, idx, page, text, embedding) "
                "values (%(id)s, %(lib)s, %(idx)s, %(page)s, %(text)s, %(embedding)s)",
                [
                    {
                        "id": uuid4(),
                        "lib": library_id,
                        "idx": chunk.idx,
                        "page": chunk.page,
                        "text": chunk.text,
                        "embedding": np.array(vector, dtype=np.float32),
                    }
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )

    def record_usage(
        self,
        user_id: UUID,
        notebook_id: UUID | None,
        action: str,
        action_id: UUID,
        usage: Usage,
    ) -> UsageRecord:
        with self._pool.connection() as conn:
            return core_record_usage(
                conn,
                user_id,
                notebook_id,
                self._service,
                action,
                action_id,
                usage,
                prices=self._prices,
                rules=self._rules.current(conn),
            )

    def pricing_rules(self) -> PricingRules:
        with self._pool.connection() as conn:
            return self._rules.current(conn)

    def has_exchange_rate(self) -> bool:
        with self._pool.connection() as conn:
            return self._rules.current(conn).usd_per_eur is not None

    def balance_cents(self, user_id: UUID) -> Decimal:
        with self._pool.connection() as conn:
            return Decimal(core_balance_cents(conn, user_id))

    def held_cents(self, owner: UUID) -> Decimal:
        row = self._one(
            "select coalesce(sum(funded_cents), 0) + "
            + self._RESERVED.format(owner="%(owner)s")
            + " as held from library_sources "
            "where owner = %(owner)s and funded_request_at is not null "
            "and status = 'processing' and deleted_at is null",
            {"owner": owner},
        )
        return Decimal(row["held"]) if row else Decimal(0)

    def has_credit(self, user_id: UUID) -> bool:
        with self._pool.connection() as conn:
            return core_has_credit(conn, user_id)

    def admin_role(self, user_id: UUID) -> Role:
        with self._pool.connection() as conn:
            return core_admin_role(conn, user_id)

    _STATS_SQL = f"""
    select count(*) filter (where status = 'processing'),
           count(*) filter (where status = 'ready'),
           count(*) filter (where status = 'added'),
           count(*) filter (where status = 'failed'),
           count(*) filter (where status = 'processing' and {_FUNDED}
                              and (claimed_at is null
                                   or claimed_at < now() - make_interval(secs => %(stale)s))),
           count(*) filter (where status = 'processing' and not {_FUNDED}),
           coalesce(sum(size_bytes), 0),
           (select count(*) from chunks c join library_sources l on l.id = c.library_source_id
             where {_LISTED})
      from library_sources l
     where {_LISTED}
    """

    def admin_stats(self, stale_after_seconds: int) -> AdminStats:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(self._STATS_SQL, {"stale": stale_after_seconds})
            row = cur.fetchone()
        assert row is not None
        processing, ready, added, failed, pending, waiting, size, chunks = (int(v) for v in row)
        return AdminStats(
            sources={"added": added, "processing": processing, "ready": ready, "failed": failed},
            jobs={
                "pending": pending,
                "running": processing - pending - waiting,
                "waiting_for_credit": waiting,
                "failed": failed,
            },
            chunks=chunks,
            source_bytes=size,
        )

    _DAILY_SQL = f"""
    select d.day::date as day,
           count(l.id) as sources_created,
           count(l.id) filter (where l.kind = 'pdf') as pdf,
           count(l.id) filter (where l.kind = 'text') as text,
           count(l.id) filter (where l.kind = 'url') as url,
           count(l.id) filter (where l.kind = 'image') as image,
           count(l.id) filter (where l.kind = 'audio') as audio,
           count(l.id) filter (where l.status = 'failed') as failed
      from generate_series((now() at time zone 'utc')::date - (%(days)s - 1),
                           (now() at time zone 'utc')::date, interval '1 day') as d(day)
      left join library_sources l
        on (l.created_at at time zone 'utc')::date = d.day::date and {_LISTED}
     group by d.day
     order by d.day
    """

    def admin_daily(self, days: int) -> list[DailyStats]:
        rows = self._all(self._DAILY_SQL, {"days": days})
        return [
            DailyStats(
                day=row["day"],
                sources_created=row["sources_created"],
                by_kind={kind: row[kind] for kind in KINDS},
                failed=row["failed"],
            )
            for row in rows
        ]


def _keys(rows: list[dict[str, Any]]) -> list[str]:
    """The stored objects of deleted library rows: the original, a converted
    recording's MP3, a web page's snapshot."""
    return [
        row[column]
        for row in rows
        for column in ("storage_path", "transcribed_path", "snapshot_path")
        if row.get(column)
    ]


def _generated_entry(row: dict[str, Any]) -> LibraryEntry:
    origin = Origin(id=row.pop("origin_id"), title=row.pop("origin_title"))
    return LibraryEntry(**row, origin=origin)
