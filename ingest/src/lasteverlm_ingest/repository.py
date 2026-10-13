"""All database access, behind one interface.

The schema is owned by the infra repository (migrations); this module only
reads and writes it. Services share the database and never call each
other, so the tables below are the contract with rag and account.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from lasteverlm_core import Chunk, ModelPrices, Notebook, Source, UsageRecord
from lasteverlm_core import has_credit as core_has_credit
from lasteverlm_core import is_admin as core_is_admin
from lasteverlm_core import record_usage as core_record_usage
from pydantic import BaseModel, ConfigDict


class StoredSource(Source):
    """A source row with the fields the API does not expose."""

    model_config = ConfigDict(from_attributes=True)

    owner: UUID
    storage_path: str | None
    summary: str | None = None
    attempts: int = 0
    size_bytes: int | None = None


class Repository(Protocol):
    def list_notebooks(self, owner: UUID) -> list[Notebook]: ...

    def create_notebook(self, owner: UUID, title: str) -> Notebook: ...

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> Notebook | None: ...

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> list[str]:
        """Delete the notebook (sources and chunks cascade) and return the
        storage keys of its sources so the caller can remove the objects."""
        ...

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]: ...

    def create_source(
        self,
        notebook_id: UUID,
        source_id: UUID,
        name: str,
        kind: str,
        storage_path: str | None,
        size_bytes: int | None = None,
    ) -> StoredSource: ...

    def get_source(self, source_id: UUID) -> StoredSource | None: ...

    def delete_source(self, source_id: UUID) -> None: ...

    def set_source_status(self, source_id: UUID, status: str, error: str | None = None) -> None: ...

    def claim_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        """Claim one unprocessed source for this worker and return its id,
        or None when the queue is empty. A source whose claim is older than
        `stale_after_seconds` counts as unprocessed again (its worker died)."""
        ...

    def set_source_summary(self, source_id: UUID, summary: str) -> None: ...

    def replace_chunks(
        self, source_id: UUID, notebook_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None: ...

    def record_usage(
        self,
        user_id: UUID,
        notebook_id: UUID | None,
        kind: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> UsageRecord:
        """Price and write one `usage` row (core's `record_usage`)."""
        ...

    def has_credit(self, user_id: UUID) -> bool:
        """May this user start a model call: an admin always, anyone else
        with a positive balance (core's `has_credit`)."""
        ...

    def is_admin(self, user_id: UUID) -> bool:
        """`users.is_admin` (core's `is_admin`); false without a user row."""
        ...

    def admin_stats(self, stale_after_seconds: int) -> AdminStats:
        """Counts over all users for the admin overview; read-only."""
        ...


class AdminStats(BaseModel):
    """`GET /admin/stats`. A `processing` source is a pending job until a
    worker claims it (or its claim is stale) and a running job while
    claimed; `source_bytes` counts rows that stored their size."""

    sources: dict[str, int]
    jobs: dict[str, int]
    chunks: int
    source_bytes: int


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

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> list[str]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "select storage_path from sources where notebook_id = %(id)s "
                "and storage_path is not null",
                {"id": notebook_id},
            )
            keys = [row[0] for row in cur.fetchall()]
            cur.execute(
                "delete from notebooks where id = %(id)s and owner = %(owner)s",
                {"id": notebook_id, "owner": owner},
            )
            return keys

    _SELECT_SOURCES = (
        "select s.id, s.notebook_id, s.name, s.kind, s.status, s.error, s.created_at, "
        "s.storage_path, s.summary, s.attempts, n.owner "
        "from sources s join notebooks n on n.id = s.notebook_id"
    )

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]:
        rows = self._all(
            f"{self._SELECT_SOURCES} where s.notebook_id = %(id)s order by s.created_at",
            {"id": notebook_id},
        )
        return [StoredSource(**row) for row in rows]

    def create_source(
        self,
        notebook_id: UUID,
        source_id: UUID,
        name: str,
        kind: str,
        storage_path: str | None,
        size_bytes: int | None = None,
    ) -> StoredSource:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into sources"
                " (id, notebook_id, name, kind, storage_path, size_bytes, status)"
                " values (%(id)s, %(nb)s, %(name)s, %(kind)s, %(path)s, %(size)s, 'processing')",
                {
                    "id": source_id,
                    "nb": notebook_id,
                    "name": name,
                    "kind": kind,
                    "path": storage_path,
                    "size": size_bytes,
                },
            )
        source = self.get_source(source_id)
        assert source is not None
        return source

    def get_source(self, source_id: UUID) -> StoredSource | None:
        row = self._one(
            f"{self._SELECT_SOURCES} where s.id = %(id)s",
            {"id": source_id},
        )
        return StoredSource(**row) if row else None

    def delete_source(self, source_id: UUID) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("delete from sources where id = %(id)s", {"id": source_id})

    def set_source_status(self, source_id: UUID, status: str, error: str | None = None) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update sources set status = %(status)s, error = %(error)s where id = %(id)s",
                {"status": status, "error": error, "id": source_id},
            )

    # The queue: `processing` rows that nobody holds. FOR UPDATE SKIP LOCKED
    # lets any number of workers claim concurrently without a broker; the
    # claim itself is the row update, in the same statement.
    _CLAIM_SQL = """
    update sources
       set claimed_at = now(), claimed_by = %(worker)s, attempts = attempts + 1
     where id = (
        select id from sources
         where status = 'processing'
           and (claimed_at is null or claimed_at < now() - make_interval(secs => %(stale)s))
         order by created_at
         for update skip locked
         limit 1)
    returning id
    """

    def claim_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(self._CLAIM_SQL, {"worker": worker_id, "stale": stale_after_seconds})
            row = cur.fetchone()
            return row[0] if row else None

    def set_source_summary(self, source_id: UUID, summary: str) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "update sources set summary = %(summary)s where id = %(id)s",
                {"summary": summary, "id": source_id},
            )

    def replace_chunks(
        self, source_id: UUID, notebook_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        import numpy as np

        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute("delete from chunks where source_id = %(id)s", {"id": source_id})
            cur.executemany(
                "insert into chunks (id, source_id, notebook_id, idx, page, text, embedding) "
                "values (%(id)s, %(source)s, %(nb)s, %(idx)s, %(page)s, %(text)s, %(embedding)s)",
                [
                    {
                        "id": uuid4(),
                        "source": source_id,
                        "nb": notebook_id,
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
        kind: str,
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
                kind,  # type: ignore[arg-type]
                model,
                tokens_in,
                tokens_out,
                prices=self._prices,
            )

    def has_credit(self, user_id: UUID) -> bool:
        with self._pool.connection() as conn:
            return core_has_credit(conn, user_id)

    def is_admin(self, user_id: UUID) -> bool:
        with self._pool.connection() as conn:
            return core_is_admin(conn, user_id)

    _STATS_SQL = """
    select count(*) filter (where status = 'processing'),
           count(*) filter (where status = 'ready'),
           count(*) filter (where status = 'failed'),
           count(*) filter (where status = 'processing'
                              and (claimed_at is null
                                   or claimed_at < now() - make_interval(secs => %(stale)s))),
           coalesce(sum(size_bytes), 0),
           (select count(*) from chunks)
      from sources
    """

    def admin_stats(self, stale_after_seconds: int) -> AdminStats:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(self._STATS_SQL, {"stale": stale_after_seconds})
            row = cur.fetchone()
        assert row is not None
        processing, ready, failed, pending, size, chunks = (int(v) for v in row)
        return AdminStats(
            sources={"processing": processing, "ready": ready, "failed": failed},
            jobs={"pending": pending, "running": processing - pending, "failed": failed},
            chunks=chunks,
            source_bytes=size,
        )
