"""Rate limiting, blocking and banning per client IP, with the access log.

The fine layer of the family's two-layer scheme (parent:
docs/architecture.md, "Rate limiting"); the coarse one is ingress-nginx.
Every API service loads `RateLimitMiddleware`. State lives in PostgreSQL,
in three tables of core's migration, so all replicas of all services
share one view of a client:

- `access_log`: one row per request (sampled for `/healthz`). The
  sliding window is a count over it.
- `ip_blocks`: over the limit means 429 for `BLOCK_MINUTES` and one
  strike; strikes reset after `STRIKE_WINDOW_HOURS` of quiet.
- `ip_bans`: the `BAN_AFTER_STRIKES`th strike within the window. 403 on
  everything until an admin lifts the ban.

The rules are in `RateLimiter`, pure over a `RateLimitStore`; the
middleware only adapts ASGI to them. Raw IPs exist only here, for this
purpose, and `purge` removes them after `RETENTION_DAYS`.
"""

from __future__ import annotations

import ipaddress
import itertools
import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

import anyio

from .auth import AuthError, AuthSettings, current_user
from .settings import env_int
from .usage import AsyncConnection, Connection

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

UNKNOWN_IP = "0.0.0.0"


@dataclass(frozen=True)
class RateLimitSettings:
    per_minute: int = 120
    block_minutes: int = 15
    ban_after_strikes: int = 3
    strike_window_hours: int = 24
    healthz_sample: int = 100
    retention_days: int = 30

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RateLimitSettings:
        return cls(
            per_minute=env_int("RATE_LIMIT_PER_MINUTE", cls.per_minute, env),
            block_minutes=env_int("BLOCK_MINUTES", cls.block_minutes, env),
            ban_after_strikes=env_int("BAN_AFTER_STRIKES", cls.ban_after_strikes, env),
            strike_window_hours=env_int("STRIKE_WINDOW_HOURS", cls.strike_window_hours, env),
            healthz_sample=env_int("ACCESS_LOG_HEALTHZ_SAMPLE", cls.healthz_sample, env),
            retention_days=env_int("RETENTION_DAYS", cls.retention_days, env),
        )


@dataclass(frozen=True)
class AccessLogEntry:
    at: datetime
    ip: str
    path: str
    method: str
    status: int
    user_id: UUID | None
    service: str


@dataclass(frozen=True)
class Decision:
    """`allowed`, `blocked` (429, `retry_after` seconds) or `banned` (403)."""

    kind: Literal["allowed", "blocked", "banned"]
    retry_after: int = 0

    @property
    def status(self) -> int:
        return {"allowed": 200, "blocked": 429, "banned": 403}[self.kind]


ALLOWED = Decision("allowed")
BANNED = Decision("banned")


class RateLimitStore(Protocol):
    """What the rules need from storage. Implemented over PostgreSQL and in memory."""

    async def is_banned(self, ip: str) -> bool: ...
    async def blocked_until(self, ip: str) -> datetime | None: ...
    async def requests_since(self, ip: str, since: datetime) -> int: ...
    async def strike(
        self, ip: str, blocked_until: datetime, now: datetime, window_start: datetime
    ) -> int:
        """Block `ip` until `blocked_until` and count a strike at `now`.

        Returns the strikes on record, restarted at one when the previous
        strike was before `window_start`.
        """
        ...

    async def ban(self, ip: str, reason: str) -> None: ...
    async def log(self, entry: AccessLogEntry) -> None: ...


class RateLimiter:
    """The block and ban rules over a store. One instance per process."""

    def __init__(self, store: RateLimitStore, settings: RateLimitSettings) -> None:
        self._store = store
        self._settings = settings
        self._healthz_counter = itertools.count()

    @property
    def settings(self) -> RateLimitSettings:
        return self._settings

    async def check(self, ip: str, now: datetime) -> Decision:
        s = self._settings
        if await self._store.is_banned(ip):
            return BANNED
        until = await self._store.blocked_until(ip)
        if until is not None and until > now:
            return Decision("blocked", _retry_after(until, now))
        if await self._store.requests_since(ip, now - timedelta(minutes=1)) < s.per_minute:
            return ALLOWED
        until = now + timedelta(minutes=s.block_minutes)
        window_start = now - timedelta(hours=s.strike_window_hours)
        strikes = await self._store.strike(ip, until, now, window_start)
        if strikes >= s.ban_after_strikes:
            reason = f"{strikes} rate-limit strikes within {s.strike_window_hours}h"
            await self._store.ban(ip, reason)
            return BANNED
        return Decision("blocked", _retry_after(until, now))

    async def record(self, entry: AccessLogEntry) -> None:
        """Write the access-log row; `/healthz` rows are sampled 1 in `healthz_sample`."""
        if entry.path.endswith("/healthz") and (
            next(self._healthz_counter) % max(self._settings.healthz_sample, 1)
        ):
            return
        await self._store.log(entry)


def _retry_after(until: datetime, now: datetime) -> int:
    return max(1, int((until - now).total_seconds() + 0.999))


def client_ip(scope: Scope, trust_forwarded: bool = True) -> str:
    """The client address: first `X-Forwarded-For` entry when trusted, else the peer.

    Only the ingress sets the header in the cluster; a service reachable
    directly (local runs) passes `trust_forwarded=False`. Anything that
    is not an IP address becomes `UNKNOWN_IP`, so a malformed header
    cannot break the request or the `inet` column.
    """
    candidate: str | None = None
    if trust_forwarded:
        for name, value in scope.get("headers", ()):
            if name == b"x-forwarded-for":
                candidate = value.decode("latin-1").split(",")[0].strip()
                break
    if candidate is None:
        client = scope.get("client")
        candidate = client[0] if client else None
    try:
        return str(ipaddress.ip_address(candidate or ""))
    except ValueError:
        return UNKNOWN_IP


class RateLimitMiddleware:
    """Pure ASGI middleware: `check` before the app, `record` after it.

    `service` names the writer in `access_log`. With `auth`, the row
    carries the user the bearer token resolves to; an invalid token is
    logged as anonymous and left for the app to reject.
    """

    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter,
        *,
        service: str,
        auth: AuthSettings | None = None,
        trust_forwarded: bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._app = app
        self._limiter = limiter
        self._service = service
        self._auth = auth
        self._trust_forwarded = trust_forwarded
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        now = self._clock()
        ip = client_ip(scope, self._trust_forwarded)
        decision = await self._limiter.check(ip, now)
        status = decision.status
        if decision.kind == "allowed":

            async def send_and_note(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = int(message["status"])
                await send(message)

            try:
                await self._app(scope, receive, send_and_note)
            except Exception:
                status = 500
                raise
            finally:
                await self._record(scope, ip, status, now)
        else:
            await _send_json(send, decision)
            await self._record(scope, ip, status, now)

    async def _record(self, scope: Scope, ip: str, status: int, now: datetime) -> None:
        await self._limiter.record(
            AccessLogEntry(
                at=now,
                ip=ip,
                path=scope.get("path", ""),
                method=scope.get("method", ""),
                status=status,
                user_id=self._user_id(scope),
                service=self._service,
            )
        )

    def _user_id(self, scope: Scope) -> UUID | None:
        if self._auth is None:
            return None
        header = next(
            (v.decode("latin-1") for k, v in scope.get("headers", ()) if k == b"authorization"),
            None,
        )
        try:
            return current_user(header, self._auth).user_id
        except AuthError:
            return None


async def _send_json(send: Send, decision: Decision) -> None:
    body = json.dumps(
        {"error": "too many requests" if decision.kind == "blocked" else "banned"}
    ).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if decision.kind == "blocked":
        headers.append((b"retry-after", str(decision.retry_after).encode()))
    await send({"type": "http.response.start", "status": decision.status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


# --- stores -----------------------------------------------------------------

IS_BANNED_SQL = "select 1 from ip_bans where ip = %(ip)s and lifted_at is null"
BLOCKED_UNTIL_SQL = "select blocked_until from ip_blocks where ip = %(ip)s"
# 429s are the limiter's own answers and must not keep a client over the limit.
REQUESTS_SINCE_SQL = """
select count(*) from access_log
where ip = %(ip)s and at >= %(since)s and status <> 429
"""
STRIKE_SQL = """
insert into ip_blocks (ip, blocked_until, strikes, updated_at)
values (%(ip)s, %(blocked_until)s, 1, %(now)s)
on conflict (ip) do update set
    blocked_until = excluded.blocked_until,
    strikes = case when ip_blocks.updated_at < %(window_start)s then 1
                   else ip_blocks.strikes + 1 end,
    updated_at = excluded.updated_at
returning strikes
"""
BAN_SQL = """
insert into ip_bans (ip, reason) values (%(ip)s, %(reason)s)
on conflict (ip) do update set reason = excluded.reason, created_at = now(), lifted_at = null
"""
LIFT_BAN_SQL = "update ip_bans set lifted_at = now() where ip = %(ip)s and lifted_at is null"
ACCESS_LOG_SQL = """
insert into access_log (at, ip, path, method, status, user_id, service)
values (%(at)s, %(ip)s, %(path)s, %(method)s, %(status)s, %(user_id)s, %(service)s)
"""
# Raw IPs are kept for the security purpose only. An active ban stays until
# an admin lifts it; everything else older than the cutoff goes.
PURGE_SQL = (
    "delete from access_log where at < %(cutoff)s",
    "delete from ip_blocks where updated_at < %(cutoff)s",
    "delete from ip_bans where lifted_at is not null and lifted_at < %(cutoff)s",
)


def purge(conn: Connection, retention_days: int = 30, now: datetime | None = None) -> None:
    """Remove rows older than `retention_days` from the three tables. The caller commits."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    with conn.cursor() as cur:
        for statement in PURGE_SQL:
            cur.execute(statement, {"cutoff": cutoff})


def lift_ban(conn: Connection, ip: str) -> None:
    """Lift an active ban; the admin panel's action. The caller commits."""
    with conn.cursor() as cur:
        cur.execute(LIFT_BAN_SQL, {"ip": ip})


def _strike_params(
    ip: str, blocked_until: datetime, now: datetime, window_start: datetime
) -> dict[str, Any]:
    return {"ip": ip, "blocked_until": blocked_until, "now": now, "window_start": window_start}


class PostgresRateLimitStore:
    """Over a sync psycopg connection source, e.g. `ConnectionPool.connection`.

    Each call takes one connection, runs one statement and commits; the
    blocking driver runs in a worker thread so the event loop stays free.
    """

    def __init__(self, connect: Callable[[], AbstractContextManager[Connection]]) -> None:
        self._connect = connect

    def _run(self, sql: str, params: Mapping[str, Any], fetch: bool) -> Any:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() if fetch else None

    async def _query(self, sql: str, params: Mapping[str, Any], fetch: bool) -> Any:
        return await anyio.to_thread.run_sync(self._run, sql, params, fetch)

    async def is_banned(self, ip: str) -> bool:
        return await self._query(IS_BANNED_SQL, {"ip": ip}, True) is not None

    async def blocked_until(self, ip: str) -> datetime | None:
        row = await self._query(BLOCKED_UNTIL_SQL, {"ip": ip}, True)
        return row[0] if row else None

    async def requests_since(self, ip: str, since: datetime) -> int:
        row = await self._query(REQUESTS_SINCE_SQL, {"ip": ip, "since": since}, True)
        return int(row[0]) if row else 0

    async def strike(
        self, ip: str, blocked_until: datetime, now: datetime, window_start: datetime
    ) -> int:
        params = _strike_params(ip, blocked_until, now, window_start)
        row = await self._query(STRIKE_SQL, params, True)
        return int(row[0]) if row else 1

    async def ban(self, ip: str, reason: str) -> None:
        await self._query(BAN_SQL, {"ip": ip, "reason": reason}, False)

    async def log(self, entry: AccessLogEntry) -> None:
        await self._query(ACCESS_LOG_SQL, entry.__dict__, False)


class AsyncPostgresRateLimitStore:
    """Over an async psycopg connection source, e.g. `AsyncConnectionPool.connection`."""

    def __init__(self, connect: Callable[[], AbstractAsyncContextManager[AsyncConnection]]) -> None:
        self._connect = connect

    async def _query(self, sql: str, params: Mapping[str, Any], fetch: bool) -> Any:
        async with self._connect() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone() if fetch else None

    async def is_banned(self, ip: str) -> bool:
        return await self._query(IS_BANNED_SQL, {"ip": ip}, True) is not None

    async def blocked_until(self, ip: str) -> datetime | None:
        row = await self._query(BLOCKED_UNTIL_SQL, {"ip": ip}, True)
        return row[0] if row else None

    async def requests_since(self, ip: str, since: datetime) -> int:
        row = await self._query(REQUESTS_SINCE_SQL, {"ip": ip, "since": since}, True)
        return int(row[0]) if row else 0

    async def strike(
        self, ip: str, blocked_until: datetime, now: datetime, window_start: datetime
    ) -> int:
        params = _strike_params(ip, blocked_until, now, window_start)
        row = await self._query(STRIKE_SQL, params, True)
        return int(row[0]) if row else 1

    async def ban(self, ip: str, reason: str) -> None:
        await self._query(BAN_SQL, {"ip": ip, "reason": reason}, False)

    async def log(self, entry: AccessLogEntry) -> None:
        await self._query(ACCESS_LOG_SQL, entry.__dict__, False)


@dataclass
class MemoryRateLimitStore:
    """In memory, per process: for tests and local runs without PostgreSQL."""

    entries: list[AccessLogEntry] = field(default_factory=list)
    # ip -> (blocked_until, strikes, last strike at)
    blocks: dict[str, tuple[datetime, int, datetime]] = field(default_factory=dict)
    bans: dict[str, str] = field(default_factory=dict)

    async def is_banned(self, ip: str) -> bool:
        return ip in self.bans

    async def blocked_until(self, ip: str) -> datetime | None:
        block = self.blocks.get(ip)
        return block[0] if block else None

    async def requests_since(self, ip: str, since: datetime) -> int:
        return sum(1 for e in self.entries if e.ip == ip and e.at >= since and e.status != 429)

    async def strike(
        self, ip: str, blocked_until: datetime, now: datetime, window_start: datetime
    ) -> int:
        previous = self.blocks.get(ip)
        strikes = 1 if previous is None or previous[2] < window_start else previous[1] + 1
        self.blocks[ip] = (blocked_until, strikes, now)
        return strikes

    async def ban(self, ip: str, reason: str) -> None:
        self.bans[ip] = reason

    async def log(self, entry: AccessLogEntry) -> None:
        self.entries.append(entry)
