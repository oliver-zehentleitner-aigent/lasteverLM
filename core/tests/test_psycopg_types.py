"""mypy, not pytest, is the assertion here: core's structural connection types
must accept psycopg connections and pools of every row factory the services
use. psycopg is imported for type checking only: the machine running the
tests may have no libpq, and nothing here needs a database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from lasteverlm_core import (
    AsyncPostgresRateLimitStore,
    PostgresRateLimitStore,
    abalance_cents,
    balance_cents,
)
from lasteverlm_core.usage import AsyncConnection, Connection

if TYPE_CHECKING:
    import psycopg
    from psycopg.rows import DictRow
    from psycopg_pool import AsyncConnectionPool, ConnectionPool


def _tuple_rows(conn: psycopg.Connection[Any], pool: ConnectionPool) -> Connection:
    balance_cents(conn, uuid4())
    PostgresRateLimitStore(pool.connection)
    return conn


def _dict_rows(
    conn: psycopg.Connection[DictRow], pool: ConnectionPool[psycopg.Connection[DictRow]]
) -> Connection:
    balance_cents(conn, uuid4())
    PostgresRateLimitStore(pool.connection)
    return conn


async def _async_dict_rows(
    conn: psycopg.AsyncConnection[DictRow],
    pool: AsyncConnectionPool[psycopg.AsyncConnection[DictRow]],
) -> AsyncConnection:
    await abalance_cents(conn, uuid4())
    AsyncPostgresRateLimitStore(pool.connection)
    return conn


def test_module_imports() -> None:
    assert callable(_tuple_rows) and callable(_dict_rows) and callable(_async_dict_rows)
