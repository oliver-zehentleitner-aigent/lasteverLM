"""Usage accounting against the shared `usage` and `ledger` tables.

Services call these, never write `usage` by hand. The connection is
whatever psycopg 3 connection the service already holds, sync (ingest,
rag) or async (account); the SQL is the same and is exported for a
service that needs to embed it in a larger statement. Core opens no
connections and owns no pool.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, Protocol
from uuid import UUID

from .models import UsageKind, UsageRecord, UsageService
from .pricing import ModelPrices, cost_cents

# Credits minus priced usage. Usage rows are the only debit.
BALANCE_SQL = """
select coalesce((select sum(amount_cents) from ledger where user_id = %(user_id)s), 0)
     - coalesce((select sum(cost_cents) from usage where user_id = %(user_id)s), 0)
    as balance_cents
"""

USAGE_SQL = """
insert into usage (user_id, notebook_id, service, kind, model, tokens_in, tokens_out, cost_cents)
values (%(user_id)s, %(notebook_id)s, %(service)s, %(kind)s, %(model)s,
        %(tokens_in)s, %(tokens_out)s, %(cost_cents)s)
"""


class Cursor(Protocol):
    def execute(self, query: str, params: Mapping[str, Any] | None = ..., /) -> Any: ...
    def fetchone(self) -> Any: ...


class Connection(Protocol):
    """The slice of `psycopg.Connection` this module uses, whatever its row factory."""

    def cursor(self) -> AbstractContextManager[Cursor]: ...


class AsyncCursor(Protocol):
    async def execute(self, query: str, params: Mapping[str, Any] | None = ..., /) -> Any: ...
    async def fetchone(self) -> Any: ...


class AsyncConnection(Protocol):
    """The slice of `psycopg.AsyncConnection` this module uses."""

    def cursor(self) -> AbstractAsyncContextManager[AsyncCursor]: ...


def _priced(
    user_id: UUID,
    notebook_id: UUID | None,
    service: UsageService,
    kind: UsageKind,
    model: str,
    tokens_in: int,
    tokens_out: int,
    prices: ModelPrices,
) -> UsageRecord:
    return UsageRecord(
        user_id=user_id,
        notebook_id=notebook_id,
        service=service,
        kind=kind,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_cents=cost_cents(prices, model, tokens_in, tokens_out),
    )


def scalar(row: Any, name: str) -> Any:
    """The one value of a one-column row, whatever the connection's row factory.

    psycopg returns tuples by default and mappings under `dict_row`; the
    services use both, so every scalar query here aliases its column and
    reads it by name when the row is a mapping.
    """
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row[name]
    return row[0]


def _balance(row: Any) -> int:
    value = scalar(row, "balance_cents")
    return int(value) if value is not None else 0


def balance_cents(conn: Connection, user_id: UUID) -> int:
    """`sum(ledger.amount_cents) - sum(usage.cost_cents)` for one user."""
    with conn.cursor() as cur:
        cur.execute(BALANCE_SQL, {"user_id": user_id})
        return _balance(cur.fetchone())


def record_usage(
    conn: Connection,
    user_id: UUID,
    notebook_id: UUID | None,
    service: UsageService,
    kind: UsageKind,
    model: str,
    tokens_in: int,
    tokens_out: int,
    *,
    prices: ModelPrices,
) -> UsageRecord:
    """Price one model call and insert its `usage` row; returns what was written.

    Raises `UnpricedModelError` before touching the database when the
    model has no price. The caller owns the transaction.
    """
    usage = _priced(user_id, notebook_id, service, kind, model, tokens_in, tokens_out, prices)
    with conn.cursor() as cur:
        cur.execute(USAGE_SQL, usage.model_dump())
    return usage


async def abalance_cents(conn: AsyncConnection, user_id: UUID) -> int:
    """`balance_cents` for an async psycopg connection."""
    async with conn.cursor() as cur:
        await cur.execute(BALANCE_SQL, {"user_id": user_id})
        return _balance(await cur.fetchone())


async def arecord_usage(
    conn: AsyncConnection,
    user_id: UUID,
    notebook_id: UUID | None,
    service: UsageService,
    kind: UsageKind,
    model: str,
    tokens_in: int,
    tokens_out: int,
    *,
    prices: ModelPrices,
) -> UsageRecord:
    """`record_usage` for an async psycopg connection."""
    usage = _priced(user_id, notebook_id, service, kind, model, tokens_in, tokens_out, prices)
    async with conn.cursor() as cur:
        await cur.execute(USAGE_SQL, usage.model_dump())
    return usage
