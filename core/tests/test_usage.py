from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from lasteverlm_core import (
    BALANCE_SQL,
    USAGE_SQL,
    UnpricedModelError,
    abalance_cents,
    arecord_usage,
    balance_cents,
    record_usage,
)

from .conftest import FakeAsyncConnection, FakeConnection


def test_balance_reads_one_row() -> None:
    user = uuid4()
    conn = FakeConnection(rows=[(250,)])
    assert balance_cents(conn, user) == 250
    sql, params = conn.executed[0]
    assert sql == BALANCE_SQL
    assert params == {"user_id": user}


def test_balance_without_rows_is_zero() -> None:
    assert balance_cents(FakeConnection(rows=[None]), uuid4()) == 0
    assert balance_cents(FakeConnection(rows=[(None,)]), uuid4()) == 0


def test_record_usage_prices_and_inserts(prices: Any) -> None:
    user, notebook = uuid4(), uuid4()
    conn = FakeConnection()
    usage = record_usage(conn, user, notebook, "rag", "llm", "llm", 1000, 2000, prices=prices)
    assert usage.cost_cents == 1
    sql, params = conn.executed[0]
    assert sql == USAGE_SQL
    assert params == usage.model_dump()
    assert params is not None and params["user_id"] == user
    assert params["notebook_id"] == notebook


def test_record_usage_unpriced_model_touches_nothing(prices: Any) -> None:
    conn = FakeConnection()
    with pytest.raises(UnpricedModelError):
        record_usage(conn, uuid4(), None, "ingest", "embedding", "nope", 1, 0, prices=prices)
    assert conn.executed == []


async def test_async_variants(prices: Any) -> None:
    user = uuid4()
    conn = FakeAsyncConnection(rows=[(7,)])
    assert await abalance_cents(conn, user) == 7
    usage = await arecord_usage(
        conn, user, None, "ingest", "embedding", "embed", 500_000, 0, prices=prices
    )
    assert usage.cost_cents == 1
    assert [sql for sql, _ in conn.executed] == [BALANCE_SQL, USAGE_SQL]
