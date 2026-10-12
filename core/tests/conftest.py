"""Fakes shared by the tests: psycopg-shaped connections that record SQL."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import pytest

Executed = list[tuple[str, Mapping[str, Any] | None]]


class FakeCursor:
    """Records every statement; answers `fetchone` from a queue of rows."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.executed: Executed = []

    def execute(self, query: str, params: Mapping[str, Any] | None = None, /) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> Any:
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._cursor = FakeCursor(rows or [])

    @contextmanager
    def cursor(self) -> Iterator[FakeCursor]:
        yield self._cursor

    @property
    def executed(self) -> Executed:
        return self._cursor.executed


class FakeAsyncCursor:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.executed: Executed = []

    async def execute(self, query: str, params: Mapping[str, Any] | None = None, /) -> None:
        self.executed.append((query, params))

    async def fetchone(self) -> Any:
        return self.rows.pop(0) if self.rows else None


class FakeAsyncConnection:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._cursor = FakeAsyncCursor(rows or [])

    @asynccontextmanager
    async def cursor(self) -> Any:
        yield self._cursor

    @property
    def executed(self) -> Executed:
        return self._cursor.executed


@pytest.fixture
def prices() -> Any:
    from lasteverlm_core import parse_model_prices

    return parse_model_prices('{"llm": {"in": 30, "out": 150}, "embed": {"in": 2, "out": 0}}')
