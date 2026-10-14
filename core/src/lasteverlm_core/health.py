"""The dependency states a service reports on `/healthz`.

`DependencyProbe` runs one check per dependency the service uses, all at
once, each bounded by `DEPENDENCY_TIMEOUT_SECONDS`, and caches the
result for `DEPENDENCY_CACHE_SECONDS`, so the liveness probe and the
admin view polling `/healthz` do not hammer the database, the bucket or
the inference API. A check that raises, returns `False` or runs out of
time is `"down"`; nothing here raises. The checks for the three
dependencies are built by `postgres_check` / `apostgres_check`,
`storage_check` and `inference_check`.
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, Protocol

import anyio
from openai import OpenAI

from .models import Dependency, DependencyState

log = logging.getLogger(__name__)

DEPENDENCY_TIMEOUT_SECONDS = 2.0
DEPENDENCY_CACHE_SECONDS = 15.0

# A check is a callable, sync or async, that raises (or returns `False`)
# when its dependency is unusable.
Check = Callable[[], Any]


class DependencyProbe:
    """The cached state of every dependency in `checks`.

    `await probe.states()` answers from the cache while it is younger than
    `ttl` seconds; otherwise it runs every check concurrently, a sync one
    in a worker thread that is abandoned at the timeout (its own client
    timeout ends it later), an async one cancelled at the timeout.
    """

    def __init__(
        self,
        checks: Mapping[Dependency, Check],
        *,
        timeout: float = DEPENDENCY_TIMEOUT_SECONDS,
        ttl: float = DEPENDENCY_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._checks = dict(checks)
        self._timeout = timeout
        self._ttl = ttl
        self._clock = clock
        self._cached: dict[Dependency, DependencyState] | None = None
        self._checked_at = 0.0
        self._lock: anyio.Lock | None = None

    async def states(self) -> dict[Dependency, DependencyState]:
        if self._fresh():
            return dict(self._cached or {})
        if self._lock is None:
            self._lock = anyio.Lock()
        async with self._lock:  # one refresh at a time; the others read its result
            if not self._fresh():
                self._cached = await self._run()
                self._checked_at = self._clock()
        return dict(self._cached or {})

    def _fresh(self) -> bool:
        return self._cached is not None and self._clock() - self._checked_at < self._ttl

    async def _run(self) -> dict[Dependency, DependencyState]:
        states: dict[Dependency, DependencyState] = {}

        async def one(name: Dependency, check: Check) -> None:
            states[name] = "down"
            with anyio.move_on_after(self._timeout) as scope:
                try:
                    if inspect.iscoroutinefunction(check):
                        result = await check()
                    else:
                        result = await anyio.to_thread.run_sync(check, abandon_on_cancel=True)
                except Exception as exc:
                    log.warning("dependency %s is down: %s", name, exc)
                    return
                if result is False:
                    log.warning("dependency %s is down: its check said so", name)
                else:
                    states[name] = "ok"
            if scope.cancelled_caught:
                log.warning("dependency %s is down: no answer within %ss", name, self._timeout)

        async with anyio.create_task_group() as group:
            for name, check in self._checks.items():
                group.start_soon(one, name, check)
        return {name: states[name] for name in self._checks}


def postgres_check(connection: Callable[[], AbstractContextManager[Any]]) -> Check:
    """`select 1` on a connection from `connection()`, sync (ingest, rag).
    Pass a factory with its own short wait, e.g. `lambda: pool.connection(timeout=2)`,
    so an exhausted pool does not hold the abandoned thread for long."""

    def check() -> None:
        with connection() as conn:
            conn.execute("select 1")

    return check


def apostgres_check(
    connection: Callable[[], AbstractAsyncContextManager[Any]],
) -> Callable[[], Awaitable[None]]:
    """`select 1` on a connection from `connection()`, async (account)."""

    async def check() -> None:
        async with connection() as conn:
            await conn.execute("select 1")

    return check


class Pingable(Protocol):
    """What `storage_check` needs: `S3Storage.ping`."""

    def ping(self) -> None: ...


def storage_check(storage: Pingable) -> Check:
    """A HEAD on the bucket through `S3Storage.ping`."""
    return storage.ping


def inference_check(client: OpenAI, timeout: float = DEPENDENCY_TIMEOUT_SECONDS) -> Check:
    """`GET /models` on the inference API, one attempt, `timeout` seconds."""
    probe_client = client.with_options(timeout=timeout, max_retries=0)

    def check() -> None:
        probe_client.models.list()

    return check
