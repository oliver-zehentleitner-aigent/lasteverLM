"""Dependency states for /healthz: concurrency, timeout, cache, the three checks."""

from __future__ import annotations

import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

import httpx2 as httpx
from openai import OpenAI

from lasteverlm_core import (
    DependencyProbe,
    Health,
    S3Storage,
    apostgres_check,
    inference_check,
    postgres_check,
    storage_check,
)

from .test_storage import SETTINGS, StubClient


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_states_ok_down_and_only_the_dependencies_given() -> None:
    def broken() -> None:
        raise RuntimeError("connection refused")

    async def fine() -> None:
        return None

    probe = DependencyProbe({"postgres": fine, "storage": broken, "inference": lambda: False})
    assert await probe.states() == {"postgres": "ok", "storage": "down", "inference": "down"}
    assert await DependencyProbe({"postgres": fine}).states() == {"postgres": "ok"}


async def test_a_hanging_check_is_down_after_the_timeout_and_does_not_hold_the_others() -> None:
    release = threading.Event()

    def hangs() -> None:
        release.wait(5)

    probe = DependencyProbe({"inference": hangs, "postgres": lambda: None}, timeout=0.1)
    started = time.monotonic()
    states = await probe.states()
    release.set()
    assert states == {"inference": "down", "postgres": "ok"}
    assert time.monotonic() - started < 1


async def test_results_are_cached_for_the_ttl() -> None:
    calls = 0

    def counted() -> None:
        nonlocal calls
        calls += 1

    clock = Clock()
    probe = DependencyProbe({"postgres": counted}, ttl=15, clock=clock)
    await probe.states()
    clock.now += 14.9
    await probe.states()
    assert calls == 1
    clock.now += 0.2
    await probe.states()
    assert calls == 2


async def test_postgres_checks_select_one_sync_and_async() -> None:
    executed: list[str] = []

    class Conn:
        def execute(self, sql: str) -> None:
            executed.append(sql)

    class AConn:
        async def execute(self, sql: str) -> None:
            executed.append(sql)

    @contextmanager
    def connection() -> Iterator[Conn]:
        yield Conn()

    @asynccontextmanager
    async def aconnection() -> AsyncIterator[AConn]:
        yield AConn()

    probe = DependencyProbe({"postgres": postgres_check(connection)})
    assert await probe.states() == {"postgres": "ok"}
    assert await DependencyProbe({"postgres": apostgres_check(aconnection)}).states() == {
        "postgres": "ok"
    }
    assert executed == ["select 1", "select 1"]


async def test_storage_check_heads_the_bucket() -> None:
    client = StubClient()
    storage = S3Storage(SETTINGS, client=client)
    assert await DependencyProbe({"storage": storage_check(storage)}).states() == {"storage": "ok"}
    assert client.calls[-1] == ("head_bucket", {"Bucket": "lasteverlm"})
    client.fail = True
    assert await DependencyProbe({"storage": storage_check(storage)}).states() == {
        "storage": "down"
    }


def models_client(status: int, seen: list[httpx.Request]) -> OpenAI:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"object": "list", "data": []})

    return OpenAI(
        base_url="http://fake/v1",
        api_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


async def test_inference_check_lists_the_models_once() -> None:
    seen: list[httpx.Request] = []
    ok = DependencyProbe({"inference": inference_check(models_client(200, seen))})
    assert await ok.states() == {"inference": "ok"}
    assert seen[0].url.path == "/v1/models"
    seen.clear()
    down = DependencyProbe({"inference": inference_check(models_client(503, seen))})
    assert await down.states() == {"inference": "down"}
    assert len(seen) == 1  # no retries


def test_health_carries_the_states_and_stays_ok() -> None:
    health = Health.from_env({}, dependencies={"postgres": "down"})
    assert health.status == "ok"
    assert health.model_dump(mode="json")["dependencies"] == {"postgres": "down"}
    assert Health.from_env({}).dependencies == {}
    assert "dependencies" not in Health.from_env({}).model_dump(mode="json")  # body as before
