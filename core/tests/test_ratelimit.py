from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from lasteverlm_core import (
    RATE_LIMIT_RULE_BOUNDS,
    RATE_LIMIT_SETTINGS_KEY,
    RULES_TTL_SECONDS,
    AccessLogEntry,
    AuthSettings,
    MemoryRateLimitStore,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitRules,
    RateLimitSettings,
    client_ip,
    issue_jwt,
    lift_ban,
    purge,
    purge_params,
)
from lasteverlm_core.ratelimit import PURGE_SQL

from .conftest import FakeConnection

T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
SETTINGS = RateLimitSettings(per_minute=3, block_minutes=15, ban_after_strikes=3)


def entry(ip: str, at: datetime, status: int = 200, path: str = "/x") -> AccessLogEntry:
    return AccessLogEntry(
        at=at, ip=ip, path=path, method="GET", status=status, user_id=None, service="t"
    )


async def fill(store: MemoryRateLimitStore, ip: str, n: int, at: datetime) -> None:
    for _ in range(n):
        await store.log(entry(ip, at))


async def test_under_limit_allowed_over_limit_blocked_with_strike() -> None:
    store = MemoryRateLimitStore()
    limiter = RateLimiter(store, SETTINGS)
    await fill(store, "10.0.0.1", 2, T0)
    assert (await limiter.check("10.0.0.1", T0)).kind == "allowed"
    await fill(store, "10.0.0.1", 1, T0)
    decision = await limiter.check("10.0.0.1", T0)
    assert decision.kind == "blocked"
    assert decision.retry_after == 15 * 60
    assert store.blocks["10.0.0.1"][:2] == (T0 + timedelta(minutes=15), 1)
    assert (await limiter.check("10.0.0.2", T0)).kind == "allowed"


async def test_block_holds_without_new_strikes_then_expires() -> None:
    store = MemoryRateLimitStore()
    limiter = RateLimiter(store, SETTINGS)
    await fill(store, "ip", 3, T0)
    assert (await limiter.check("ip", T0)).kind == "blocked"
    later = T0 + timedelta(minutes=5)
    decision = await limiter.check("ip", later)
    assert decision.kind == "blocked" and decision.retry_after == 10 * 60
    assert store.blocks["ip"][1] == 1
    # 429 answers written during the block do not count toward the window
    await store.log(entry("ip", later, status=429))
    assert (await limiter.check("ip", T0 + timedelta(minutes=16))).kind == "allowed"


async def test_third_strike_in_window_bans() -> None:
    store = MemoryRateLimitStore()
    limiter = RateLimiter(store, SETTINGS)
    t = T0
    for expected in (1, 2):
        await fill(store, "ip", 3, t)
        assert (await limiter.check("ip", t)).kind == "blocked"
        assert store.blocks["ip"][1] == expected
        t += timedelta(hours=1)
    await fill(store, "ip", 3, t)
    assert (await limiter.check("ip", t)).kind == "banned"
    assert "3 rate-limit strikes" in store.bans["ip"]
    assert (await limiter.check("ip", t + timedelta(days=30))).kind == "banned"


async def test_strikes_restart_after_a_quiet_window() -> None:
    store = MemoryRateLimitStore()
    limiter = RateLimiter(store, SETTINGS)
    await fill(store, "ip", 3, T0)
    await limiter.check("ip", T0)
    later = T0 + timedelta(hours=25)
    await fill(store, "ip", 3, later)
    await limiter.check("ip", later)
    assert store.blocks["ip"][1] == 1


async def test_healthz_sampled() -> None:
    store = MemoryRateLimitStore()
    limiter = RateLimiter(store, RateLimitSettings(healthz_sample=10))
    for _ in range(25):
        await limiter.record(entry("ip", T0, path="/api/x/healthz"))
    await limiter.record(entry("ip", T0, path="/api/x/notebooks"))
    assert len(store.entries) == 3 + 1


def test_client_ip_prefers_forwarded_header_when_trusted() -> None:
    scope: dict[str, Any] = {
        "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
        "client": ("10.1.1.1", 1234),
    }
    assert client_ip(scope) == "203.0.113.9"
    assert client_ip(scope, trust_forwarded=False) == "10.1.1.1"
    assert client_ip({"headers": [(b"x-forwarded-for", b"garbage")]}) == "0.0.0.0"
    assert client_ip({"client": ("testclient", 1)}) == "0.0.0.0"
    assert client_ip({"headers": [(b"x-forwarded-for", b"2001:db8::1")]}) == "2001:db8::1"


async def run_asgi(
    app: Any, headers: list[tuple[bytes, bytes]], path: str = "/x"
) -> tuple[int, bytes]:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "client": ("10.0.0.5", 1),
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return int(status), body


async def ok_app(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_middleware_logs_passes_and_blocks() -> None:
    store = MemoryRateLimitStore()
    secret = "a-secret-long-enough-for-hs256-signing"
    user = uuid4()
    app = RateLimitMiddleware(
        ok_app,
        RateLimiter(store, SETTINGS),
        service="t",
        auth=AuthSettings(jwt_secret=secret, demo_token=None),
        clock=lambda: T0,
    )
    auth = [(b"authorization", f"Bearer {issue_jwt(user, secret)}".encode())]
    for _ in range(3):
        assert (await run_asgi(app, auth))[0] == 204
    assert store.entries[0].user_id == user and store.entries[0].status == 204
    assert store.entries[0].ip == "10.0.0.5"
    status, body = await run_asgi(app, [(b"authorization", b"Bearer junk")])
    assert status == 429 and b"too many requests" in body
    assert store.entries[-1].status == 429 and store.entries[-1].user_id is None

    await store.ban("10.0.0.5", "test", T0)
    status, body = await run_asgi(app, [])
    assert status == 403 and b"banned" in body


async def test_middleware_ignores_non_http() -> None:
    seen: list[str] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    mw = RateLimitMiddleware(app, RateLimiter(MemoryRateLimitStore(), SETTINGS), service="t")
    await mw({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert seen == ["lifespan"]


def test_purge_and_lift_ban_sql() -> None:
    conn = FakeConnection()
    purge(conn, retention_days=30, now=T0)
    assert [sql for sql, _ in conn.executed] == list(PURGE_SQL)
    expected = {"cutoff": T0 - timedelta(days=30), "ban_cutoff": T0 - timedelta(days=90)}
    assert all(params == expected for _, params in conn.executed)
    assert purge_params(7, 14, T0) == {
        "cutoff": T0 - timedelta(days=7),
        "ban_cutoff": T0 - timedelta(days=14),
    }
    lift_ban(conn, "10.0.0.1")
    assert conn.executed[-1][1] == {"ip": "10.0.0.1"}


async def test_postgres_store_reads_tuple_and_dict_rows() -> None:
    from contextlib import contextmanager

    from lasteverlm_core import PostgresRateLimitStore

    for rows in (
        [(1,), (T0,), (5,), (2,)],
        [{"banned": 1}, {"blocked_until": T0}, {"requests": 5}, {"strikes": 2}],
    ):
        conn = FakeConnection(rows=list(rows))

        @contextmanager
        def connect(conn: FakeConnection = conn) -> Any:
            yield conn

        store = PostgresRateLimitStore(connect)
        assert await store.is_banned("ip", T0) is True
        assert await store.blocked_until("ip") == T0
        assert await store.requests_since("ip", T0) == 5
        assert await store.strike("ip", T0, T0, T0) == 2


def test_settings_from_env_reads_ban_max_days() -> None:
    assert RateLimitSettings.from_env({}).ban_max_days == 90
    settings = RateLimitSettings.from_env({"BAN_MAX_DAYS": "14", "RETENTION_DAYS": "7"})
    assert (settings.retention_days, settings.ban_max_days) == (7, 14)


async def test_ban_expires_after_ban_max_days() -> None:
    store = MemoryRateLimitStore()
    limiter = RateLimiter(store, SETTINGS)
    await store.ban("10.0.0.9", "test", T0)
    assert (await limiter.check("10.0.0.9", T0 + timedelta(days=90))).kind == "banned"
    assert (await limiter.check("10.0.0.9", T0 + timedelta(days=90, seconds=1))).kind == "allowed"


# --- runtime rules ---------------------------------------------------------------

RULES = {"per_minute": 1, "block_minutes": 5, "ban_after_strikes": 2, "strike_window_hours": 6}


def test_rules_parse_and_bounds() -> None:
    rules = RateLimitRules.parse(RULES)
    assert rules == RateLimitRules(1, 5, 2, 6) and rules.as_json() == RULES
    assert RateLimitRules.parse(json.dumps(RULES)) == rules
    assert RateLimitRules.from_settings(SETTINGS) == RateLimitRules(3, 15, 3, 24)
    assert RATE_LIMIT_SETTINGS_KEY == "ratelimit"
    assert set(RATE_LIMIT_RULE_BOUNDS) == set(RULES)
    for name, (low, high) in RATE_LIMIT_RULE_BOUNDS.items():
        assert RateLimitRules.parse({**RULES, name: low}).as_json()[name] == low
        assert RateLimitRules.parse({**RULES, name: high}).as_json()[name] == high
        for bad in (low - 1, high + 1):
            with pytest.raises(ValueError, match=f"{name} must be between"):
                RateLimitRules.parse({**RULES, name: bad})
        for bad_type in (True, 1.5, "3", None):
            with pytest.raises(ValueError, match=f"{name} must be an integer"):
                RateLimitRules.parse({**RULES, name: bad_type})
    with pytest.raises(ValueError, match="exactly the fields"):
        RateLimitRules.parse({k: v for k, v in RULES.items() if k != "per_minute"})
    with pytest.raises(ValueError, match="exactly the fields"):
        RateLimitRules.parse({**RULES, "ban_max_days": 1})
    with pytest.raises(ValueError, match="must be an object"):
        RateLimitRules.parse([1, 2, 3, 4])


async def test_stored_rules_override_env_and_refresh_after_ttl() -> None:
    store = MemoryRateLimitStore(overrides=RULES)
    limiter = RateLimiter(store, SETTINGS)
    await fill(store, "ip", 1, T0)
    decision = await limiter.check("ip", T0)
    assert decision.kind == "blocked" and decision.retry_after == 5 * 60  # stored values
    assert limiter.rules == RateLimitRules(1, 5, 2, 6)
    store.overrides = None
    assert await limiter.current_rules(T0 + timedelta(seconds=RULES_TTL_SECONDS - 1)) == (
        RateLimitRules(1, 5, 2, 6)  # cached within the TTL
    )
    later = T0 + timedelta(seconds=RULES_TTL_SECONDS)
    assert await limiter.current_rules(later) == RateLimitRules.from_settings(SETTINGS)


async def test_unusable_rules_fall_back_to_env_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryRateLimitStore(overrides={**RULES, "per_minute": 0})
    limiter = RateLimiter(store, SETTINGS)
    defaults = RateLimitRules.from_settings(SETTINGS)
    with caplog.at_level(logging.WARNING, logger="lasteverlm_core.ratelimit"):
        for i in range(3):
            t = T0 + timedelta(seconds=i * RULES_TTL_SECONDS)
            assert await limiter.current_rules(t) == defaults
    assert len(caplog.records) == 1 and "per_minute must be between" in caplog.text

    class Broken(MemoryRateLimitStore):
        async def rule_overrides(self) -> Any:
            raise RuntimeError('relation "settings" does not exist')

    broken = RateLimiter(Broken(), SETTINGS)
    assert await broken.current_rules(T0) == defaults
    assert (await broken.check("ip", T0)).kind == "allowed"
