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

from datetime import date, datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from lasteverlm_core import Chunk, ModelPrices, Notebook, Role, Source, UsageKind, UsageRecord
from lasteverlm_core import admin_role as core_admin_role
from lasteverlm_core import has_credit as core_has_credit
from lasteverlm_core import record_usage as core_record_usage
from pydantic import BaseModel, ConfigDict, Field


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
    demo: bool = False
    transcribed_path: str | None = None


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
    demo: bool = False
    transcribed_path: str | None = None


class NotebookUse(BaseModel):
    id: UUID
    title: str
    source_id: UUID


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
    demo: bool = False
    notebooks: list[NotebookUse]
    origin: Origin | None = None
    # A generated entry's output in rag (`GET /outputs/{id}`); null otherwise.
    output_id: UUID | None = None
    # Set by the API (api/deps.py): where the source opens, and for a
    # converted recording the original as a download.
    preview_url: str | None = None
    original_url: str | None = None
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
    demo: bool = False
    preview_url: str | None = None
    original_url: str | None = None
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
    demo: bool = False


# Family rule: after three attempts a job is failed with its last error.
MAX_ATTEMPTS = 3
STALLED = f"processing did not finish in {MAX_ATTEMPTS} attempts (the worker stopped or hung)"


class Repository(Protocol):
    def list_notebooks(self, owner: UUID) -> list[Notebook]: ...

    def create_notebook(self, owner: UUID, title: str) -> Notebook: ...

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> Notebook | None: ...

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
        """A failed library source uploaded again: back to `processing`."""
        ...

    def claim_seed(self, owner: UUID) -> bool:
        """Mark the owner as considered for the demo library; True only the
        first time and only when the owner has no library source yet (in
        the library or the trash), i.e. when the caller should seed."""
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

    def wait_for_credit(self, library_id: UUID) -> None:
        """Release the claim without counting the attempt: the owner ran out
        of credit, and the claim query skips the source until they have
        some again."""
        ...

    def refresh_claim(self, library_id: UUID) -> None:
        """The worker is still at it: move `claimed_at` to now, so a long
        job is not taken over as stale while it makes progress."""
        ...

    def set_library_summary(self, library_id: UUID, summary: str) -> None: ...

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
        kind: UsageKind,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> UsageRecord:
        """Price and write one `usage` row (core's `record_usage`)."""
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

    def list_notebooks(self, owner: UUID) -> list[Notebook]:
        rows = self._all(
            "select id, title, created_at from notebooks where owner = %(owner)s "
            "order by created_at desc",
            {"owner": owner},
        )
        return [Notebook(**row) for row in rows]

    def create_notebook(self, owner: UUID, title: str) -> Notebook:
        row = self._one(
            "insert into notebooks (id, owner, title) values (%(id)s, %(owner)s, %(title)s) "
            "returning id, title, created_at",
            {"id": uuid4(), "owner": owner, "title": title},
        )
        assert row is not None
        return Notebook(**row)

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> Notebook | None:
        row = self._one(
            "select id, title, created_at from notebooks where id = %(id)s and owner = %(owner)s",
            {"id": notebook_id, "owner": owner},
        )
        return Notebook(**row) if row else None

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
        "l.capture, l.demo, l.transcribed_path "
        "from sources s join library_sources l on l.id = s.library_source_id"
    )

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]:
        rows = self._all(
            f"{self._SELECT_SOURCES} where s.notebook_id = %(id)s order by s.created_at, s.id",
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
           l.capture, l.demo, l.storage_path, l.transcribed_path,
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
    # May the worker process this row: a sponsored demo seed, or an owner
    # with a positive balance (core's rule, ledger minus usage).
    _FUNDED = (
        "(l.demo or coalesce((select sum(amount_cents) from ledger where user_id = l.owner), 0)"
        " - coalesce((select sum(cost_cents) from usage where user_id = l.owner), 0) > 0)"
    )
    _LIBRARY_COLUMNS = (
        "l.id, l.owner, l.name, l.kind, l.dedupe_key, l.url, l.size_bytes, l.storage_path, "
        "l.status, l.error, l.summary, l.attempts, l.created_at, l.deleted_at, l.capture, "
        "l.demo, l.transcribed_path"
    )
    # Library sources in the library (not in the trash).
    _ACTIVE = f"{_LISTED} and l.deleted_at is null"
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
            "storage_path, capture, demo, status) values (%(id)s, %(owner)s, %(name)s, "
            "%(kind)s, %(key)s, %(url)s, %(size)s, %(path)s, %(capture)s, %(demo)s, "
            "'processing') "
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
                "demo": new.demo,
            },
        )
        found = self.find_library_source(new.owner, new.dedupe_key)
        assert found is not None
        return found

    def retry_library_source(self, library_id: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update library_sources set status = 'processing', error = null, attempts = 0, "
                "claimed_at = null, claimed_by = null, retry_at = null "
                "where id = %(id)s and status = 'failed'",
                {"id": library_id},
            )

    def claim_seed(self, owner: UUID) -> bool:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into library_seeds (owner) values (%(owner)s) "
                "on conflict (owner) do nothing returning owner",
                {"owner": owner},
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                f"select exists (select 1 from library_sources l "
                f"where l.owner = %(owner)s and {self._LISTED})",
                {"owner": owner},
            )
            row = cur.fetchone()
            return not (row and row[0])

    _LIBRARY_ENTRIES = f"""
    select l.id, l.name, l.kind, l.status, l.error, l.size_bytes, l.url, l.created_at,
           l.capture, l.demo, l.storage_path, l.transcribed_path,
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
            f"l.capture, l.demo, l.storage_path, l.transcribed_path, l.deleted_at, "
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
        row = self._one(
            f"delete from library_sources l where l.id = %(id)s and l.owner = %(owner)s "
            f"and {self._LISTED} and l.deleted_at is not null "
            f"returning l.storage_path, l.transcribed_path",
            {"id": library_id, "owner": owner},
        )
        return (row is not None, _keys([row] if row else []))

    def user_object_keys(self, owner: UUID) -> list[str]:
        rows = self._all(
            "select l.storage_path, l.transcribed_path from library_sources l "
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
            f"delete from library_sources l where {self._LISTED} and l.deleted_at is not null "
            f"and l.deleted_at + make_interval(days => {self._TRASH_DAYS}) <= now() "
            f"returning l.storage_path, l.transcribed_path",
            {},
        )
        return _keys(rows)

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
            cur.execute(
                "update library_sources set status = %(status)s, error = %(error)s "
                "where id = %(id)s",
                {"status": status, "error": error, "id": library_id},
            )

    # The queue: `processing` rows that nobody holds. FOR UPDATE SKIP LOCKED
    # lets any number of workers claim concurrently without a broker; the
    # claim itself is the row update, in the same statement. Generated rows
    # are written and finished by rag, never by this worker.
    # Processing needs credit: a source whose owner has none is not claimed
    # (the API shows it as waiting_for_credit) and is taken as soon as the
    # owner's balance is positive again; the demo seeds are sponsored.
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

    def wait_for_credit(self, library_id: UUID) -> None:
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
        kind: UsageKind,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> UsageRecord:
        with self._pool.connection() as conn:
            return core_record_usage(
                conn,
                user_id,
                notebook_id,
                self._service,
                kind,
                model,
                tokens_in,
                tokens_out,
                prices=self._prices,
            )

    def has_credit(self, user_id: UUID) -> bool:
        with self._pool.connection() as conn:
            return core_has_credit(conn, user_id)

    def admin_role(self, user_id: UUID) -> Role:
        with self._pool.connection() as conn:
            return core_admin_role(conn, user_id)

    _STATS_SQL = f"""
    select count(*) filter (where status = 'processing'),
           count(*) filter (where status = 'ready'),
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
        processing, ready, failed, pending, waiting, size, chunks = (int(v) for v in row)
        return AdminStats(
            sources={"processing": processing, "ready": ready, "failed": failed},
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
    """The stored objects of deleted library rows: the original and, for a
    converted recording, the converted file."""
    return [
        row[column]
        for row in rows
        for column in ("storage_path", "transcribed_path")
        if row[column]
    ]


def _generated_entry(row: dict[str, Any]) -> LibraryEntry:
    origin = Origin(id=row.pop("origin_id"), title=row.pop("origin_title"))
    return LibraryEntry(**row, origin=origin)
