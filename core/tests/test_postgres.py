"""The SQL paths against a real PostgreSQL: usage accounting, the admin and
credit checks, the rate-limit stores, purge and lift_ban. Everything else in
the suite runs against fakes; this file is what `make test-postgres` runs
against a throwaway pgvector container and skips without
`CORE_TEST_DATABASE_URL`.

The database is empty: core's own migrations are applied here, and the
`ledger`, `users` and `settings` tables that `BALANCE_SQL`, `IS_ADMIN_SQL`
and `RULES_SQL` read are created as the columns the account service's
migrations give them,
because core's tests cannot depend on another service's migration files.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from lasteverlm_core import (
    RATE_LIMIT_SETTINGS_KEY,
    AccessLogEntry,
    AsyncPostgresRateLimitStore,
    MemoryRateLimitStore,
    PostgresRateLimitStore,
    PricingRules,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitSettings,
    UnpricedModelError,
    Usage,
    aadmin_role,
    abalance_cents,
    admin_role,
    ahas_credit,
    ais_admin,
    arecord_usage,
    balance_cents,
    has_credit,
    is_admin,
    lift_ban,
    limit_key,
    parse_model_prices,
    purge,
    record_usage,
)

from .test_ratelimit import ok_app, run_asgi

pytestmark = pytest.mark.postgres

MIGRATIONS = sorted((Path(__file__).parent.parent / "db" / "migrations").glob("*.sql"))
LEDGER_MIRROR = (
    "create table if not exists ledger (user_id uuid not null, amount_cents integer not null)"
)
# account's shape: the role, and is_admin a plain column account writes with it
USERS_MIRROR = (
    "create table if not exists users (id uuid primary key,"
    " role text not null default 'user' check (role in ('user', 'viewer', 'admin')),"
    " is_admin boolean not null default false)"
)
SETTINGS_MIRROR = "create table if not exists settings (key text primary key, value jsonb not null)"
TABLES = ("usage", "access_log", "ip_blocks", "ip_bans", "ledger", "users", "settings")
PRICES = parse_model_prices(
    '{"llm": {"in": 30, "out": 150}, "tts": {"in": 2000, "out": 0},'
    ' "stt": {"in": 28000, "out": 0}, "clef": {"in": 10, "out": 0}}'
)
FREE = PricingRules()
T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
SETTINGS = RateLimitSettings(per_minute=3, block_minutes=15, ban_after_strikes=3)


@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get("CORE_TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("CORE_TEST_DATABASE_URL not set; run `make test-postgres`")
    deadline = time.monotonic() + 60
    while True:
        try:
            with psycopg.connect(value, connect_timeout=2) as conn, conn.cursor() as cur:
                cur.execute(LEDGER_MIRROR)
                cur.execute(USERS_MIRROR)
                cur.execute(SETTINGS_MIRROR)
                for path in MIGRATIONS:
                    cur.execute(path.read_text())
            return value
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


@pytest.fixture
def conn(dsn: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(dsn, autocommit=True) as c:
        with c.cursor() as cur:
            cur.execute(f"truncate {', '.join(TABLES)}")
        yield c


@pytest.fixture
def pool(dsn: str, conn: psycopg.Connection[Any]) -> Iterator[ConnectionPool]:
    with ConnectionPool(dsn, min_size=1, max_size=2, open=True) as p:
        yield p


def credit(conn: psycopg.Connection[Any], user: Any, cents: int) -> None:
    conn.execute("insert into ledger (user_id, amount_cents) values (%s, %s)", (user, cents))


# --- usage -------------------------------------------------------------------


def book(
    conn: Any,
    user: Any,
    usage: Usage,
    *,
    action: str = "chat_answer",
    action_id: Any = None,
    service: Any = "rag",
    rules: PricingRules = FREE,
) -> Any:
    return record_usage(
        conn, user, None, service, action, action_id or uuid4(), usage, prices=PRICES, rules=rules
    )


def test_record_usage_and_balance(conn: psycopg.Connection[Any]) -> None:
    user, notebook, action_id = uuid4(), uuid4(), uuid4()
    credit(conn, user, 1000)
    assert balance_cents(conn, user) == 1000
    usage = record_usage(
        conn,
        user,
        notebook,
        "rag",
        "chat_answer",
        action_id,
        Usage("llm", "llm", 1_000_000, 0),
        prices=PRICES,
        rules=PricingRules.parse({"default_margin_pct": 10}),
    )
    assert (usage.cost_cents, usage.charge_cents) == (Decimal(30), Decimal(33))
    assert balance_cents(conn, user) == 967  # the charge, not the cost
    assert balance_cents(conn, uuid4()) == 0
    row = conn.execute(
        "select service, action, action_id, kind, model, cost_cents, charge_cents from usage"
    ).fetchone()
    assert row == ("rag", "chat_answer", action_id, "llm", "llm", 30, 33)


def test_sub_cent_costs_are_kept_exactly(conn: psycopg.Connection[Any]) -> None:
    user = uuid4()
    credit(conn, user, 1)
    for _ in range(3):
        book(conn, user, Usage("embedding", "llm", 100, 0), action="source:pdf")
    assert balance_cents(conn, user) == Decimal("0.991")  # 3 x 0.003, nothing rounded up


def test_a_fee_is_booked_once_per_action(conn: psycopg.Connection[Any]) -> None:
    user, action_id = uuid4(), uuid4()
    credit(conn, user, 100)
    rules = PricingRules.parse({"actions": {"output:audio": {"fixed_cents": 5}}})
    for _ in range(3):  # three TTS segments of one audio output
        book(
            conn,
            user,
            Usage("tts", "tts", 500, 0),
            action="output:audio",
            action_id=action_id,
            rules=rules,
        )
    book(conn, user, Usage("tts", "tts", 500, 0), action="output:audio", rules=rules)
    fees = conn.execute(
        "select count(*), sum(charge_cents), sum(cost_cents) from usage where kind = 'fee'"
    ).fetchone()
    assert fees == (2, 10, 0)  # one per action, two actions
    assert balance_cents(conn, user) == 100 - 4 * 1 - 10  # 500 s x 2000 / 1e6 = 1 cent each


def test_unpriced_model_writes_nothing(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(UnpricedModelError):
        book(conn, uuid4(), Usage("embedding", "none", 1, 0), service="ingest")
    assert conn.execute("select count(*) from usage").fetchone() == (0,)


def test_a_row_from_the_previous_release_is_filled_by_the_trigger(
    conn: psycopg.Connection[Any],
) -> None:
    user = uuid4()
    credit(conn, user, 100)
    # the insert of a pod still on the old code, during the rolling deploy
    conn.execute(
        "insert into usage (user_id, service, kind, model, tokens_in, tokens_out, cost_cents)"
        " values (%s, 'rag', 'llm', 'llm', 1, 0, 7)",
        (user,),
    )
    row = conn.execute("select id, action, action_id, charge_cents from usage").fetchone()
    assert row is not None and row[1:] == ("unknown", row[0], 7)
    assert balance_cents(conn, user) == 93


def test_migration_0006_backfills_existing_rows(dsn: str) -> None:
    # The migrations up to 0005 in a schema of their own, rows as the old
    # code booked them, then 0006 over them.
    before = [m for m in MIGRATIONS if m.name < "0006"]
    billing = next(m for m in MIGRATIONS if m.name.startswith("0006"))
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("drop schema if exists backfill cascade")
        c.execute("create schema backfill")
        c.execute("set search_path to backfill")
        for path in before:
            c.execute(path.read_text())
        user = uuid4()
        for kind in ("llm", "tts", "stt", "decision", "embedding"):
            c.execute(
                "insert into usage (user_id, service, kind, model, tokens_in, tokens_out,"
                " cost_cents) values (%s, 'rag', %s, 'm', 1, 0, 4)",
                (user, kind),
            )
        c.execute(billing.read_text())
        rows = c.execute(
            "select kind, action, action_id = id, charge_cents, cost_cents from usage"
            " order by kind"
        ).fetchall()
        c.execute("drop schema backfill cascade")
    assert rows == [
        ("decision", "output:decision", True, 4, 4),
        ("embedding", "unknown", True, 4, 4),
        ("llm", "unknown", True, 4, 4),
        ("stt", "source:audio", True, 4, 4),
        ("tts", "output:audio", True, 4, 4),
    ]


def test_tts_usage_is_priced_per_second(conn: psycopg.Connection[Any]) -> None:
    user = uuid4()
    usage = book(conn, user, Usage("tts", "tts", 1500, 0), action="output:audio")
    assert usage.cost_cents == 3  # 1500 * 2000 / 1e6
    assert conn.execute("select kind, tokens_in from usage").fetchone() == ("tts", 1500)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "insert into usage (user_id, service, kind, model, tokens_in, tokens_out, cost_cents)"
            " values (%s, 'rag', 'speech', 'tts', 1, 0, 0)",
            (user,),
        )


def test_stt_usage_is_priced_per_second(conn: psycopg.Connection[Any]) -> None:
    usage = book(
        conn, uuid4(), Usage("stt", "stt", 3600, 0), action="source:audio", service="ingest"
    )
    assert usage.cost_cents == Decimal("100.8")  # an hour at 0.00028 USD/s
    assert conn.execute("select kind, tokens_in from usage").fetchone() == ("stt", 3600)


def test_decision_usage_is_priced_per_input_token(conn: psycopg.Connection[Any]) -> None:
    usage = book(conn, uuid4(), Usage("decision", "clef", 2192, 0), action="output:decision")
    assert usage.cost_cents == Decimal("0.02192")
    assert conn.execute("select kind, tokens_in from usage").fetchone() == ("decision", 2192)


def test_admins_need_credit_like_everyone(dsn: str, conn: psycopg.Connection[Any]) -> None:
    admin, user, stranger = uuid4(), uuid4(), uuid4()
    conn.execute(
        "insert into users (id, role, is_admin) values (%s, 'admin', true), (%s, 'user', false)",
        (admin, user),
    )
    assert is_admin(conn, admin) is True
    assert is_admin(conn, user) is False
    assert is_admin(conn, stranger) is False  # no users row
    assert has_credit(conn, admin) is False  # balance 0, no exemption
    assert has_credit(conn, user) is False
    assert has_credit(conn, stranger) is False
    credit(conn, user, 5)
    assert has_credit(conn, user) is True
    book(conn, user, Usage("llm", "llm", 1_000_000, 0))
    assert has_credit(conn, user) is False  # 5 - 30 < 0
    credit(conn, admin, 100)  # a voucher
    assert has_credit(conn, admin) is True
    book(conn, admin, Usage("llm", "llm", 4_000_000, 0))
    assert has_credit(conn, admin) is False  # 100 - 120 < 0
    with psycopg.connect(dsn, row_factory=dict_row) as dconn:
        assert has_credit(dconn, admin) is False and is_admin(dconn, admin) is True


async def test_roles_from_the_users_table(dsn: str, conn: psycopg.Connection[Any]) -> None:
    admin, viewer, user = uuid4(), uuid4(), uuid4()
    conn.execute(
        "insert into users (id, role, is_admin)"
        " values (%s, 'admin', true), (%s, 'viewer', false), (%s, 'user', false)",
        (admin, viewer, user),
    )
    assert [admin_role(conn, u) for u in (admin, viewer, user, uuid4())] == [
        "admin",
        "viewer",
        "user",
        "user",  # no row
    ]
    assert is_admin(conn, admin) is True and is_admin(conn, viewer) is False
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as aconn:
        assert await aadmin_role(aconn, viewer) == "viewer"


async def test_async_admin_and_credit(dsn: str, conn: psycopg.Connection[Any]) -> None:
    admin = uuid4()
    conn.execute("insert into users (id, role, is_admin) values (%s, 'admin', true)", (admin,))
    async with await psycopg.AsyncConnection.connect(dsn) as aconn:
        assert await ais_admin(aconn, admin) is True
        assert await ahas_credit(aconn, admin) is False  # admins need credit too
        credit(conn, admin, 1)
        assert await ahas_credit(aconn, admin) is True
        assert await ahas_credit(aconn, uuid4()) is False


def test_balance_on_a_dict_row_connection(dsn: str, conn: psycopg.Connection[Any]) -> None:
    user = uuid4()
    credit(conn, user, 500)
    with psycopg.connect(dsn, row_factory=dict_row) as dconn:
        book(dconn, user, Usage("embedding", "llm", 100, 0), action="source:pdf")
        dconn.commit()
        assert balance_cents(dconn, user) == Decimal("499.997")


async def test_async_usage(dsn: str, conn: psycopg.Connection[Any]) -> None:
    user = uuid4()
    credit(conn, user, 100)
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as aconn:
        usage = await arecord_usage(
            aconn,
            user,
            None,
            "rag",
            "chat_answer",
            uuid4(),
            Usage("llm", "llm", 0, 100_000),
            prices=PRICES,
            rules=FREE,
        )
        await aconn.commit()
        assert usage.cost_cents == 15
        assert await abalance_cents(aconn, user) == 85


# --- rate limiting -------------------------------------------------------------


def entry(ip: str, at: datetime, status: int = 200) -> AccessLogEntry:
    return AccessLogEntry(
        at=at, ip=ip, path="/x", method="GET", status=status, user_id=None, service="t"
    )


async def test_store_block_strike_ban_lift(
    pool: ConnectionPool, conn: psycopg.Connection[Any]
) -> None:
    store = PostgresRateLimitStore(pool.connection)
    limiter = RateLimiter(store, SETTINGS)
    ip = "203.0.113.7"
    t = T0
    for expected_strikes in (1, 2):
        for _ in range(3):
            await store.log(entry(ip, t))
        decision = await limiter.check(ip, t)
        assert decision.kind == "blocked" and decision.retry_after == 15 * 60
        assert conn.execute("select strikes from ip_blocks where ip = %s", (ip,)).fetchone() == (
            expected_strikes,
        )
        assert (await limiter.check(ip, t + timedelta(minutes=1))).kind == "blocked"
        assert (await limiter.check(ip, t + timedelta(minutes=16))).kind == "allowed"
        t += timedelta(hours=1)
    for _ in range(3):
        await store.log(entry(ip, t))
    assert (await limiter.check(ip, t)).kind == "banned"
    assert (await limiter.check(ip, t + timedelta(days=5))).kind == "banned"
    assert (await limiter.check(ip, t + timedelta(days=90))).kind == "banned"
    assert (await limiter.check(ip, t + timedelta(days=91))).kind == "allowed"  # expired
    assert (await limiter.check("203.0.113.8", t)).kind == "allowed"

    lift_ban(conn, ip)
    assert conn.execute(
        "select lifted_at is not null from ip_bans where ip = %s", (ip,)
    ).fetchone() == (True,)
    assert (await limiter.check(ip, t + timedelta(days=5))).kind == "allowed"


async def test_ipv6_64_key_is_logged_banned_and_lifted(
    pool: ConnectionPool, conn: psycopg.Connection[Any]
) -> None:
    key = limit_key("2001:db8:1:2::7")
    store = PostgresRateLimitStore(pool.connection)
    limiter = RateLimiter(store, SETTINGS)
    await store.log(entry(key, T0))
    assert await store.requests_since(key, T0 - timedelta(minutes=1)) == 1
    await store.ban(key, "test", T0)
    assert (await limiter.check(limit_key("2001:db8:1:2::9"), T0)).kind == "banned"
    assert (await limiter.check(limit_key("2001:db8:1:3::9"), T0)).kind == "allowed"
    assert conn.execute("select ip::text from ip_bans").fetchone() == ("2001:db8:1:2::/64",)
    lift_ban(conn, key)
    assert (await limiter.check(key, T0)).kind == "allowed"


async def test_store_strikes_restart_after_quiet_window(pool: ConnectionPool) -> None:
    store = PostgresRateLimitStore(pool.connection)
    limiter = RateLimiter(store, SETTINGS)
    ip = "198.51.100.1"
    for _ in range(3):
        await store.log(entry(ip, T0))
    await limiter.check(ip, T0)
    later = T0 + timedelta(hours=25)
    for _ in range(3):
        await store.log(entry(ip, later))
    await limiter.check(ip, later)
    assert await store.strike(ip, later, later, later - timedelta(hours=24)) == 2  # one more
    assert await store.blocked_until(ip) == later


async def test_store_ignores_its_own_429s(pool: ConnectionPool) -> None:
    store = PostgresRateLimitStore(pool.connection)
    ip = "198.51.100.2"
    for status in (200, 429, 429, 200):
        await store.log(entry(ip, T0, status))
    assert await store.requests_since(ip, T0 - timedelta(minutes=1)) == 2


async def test_dict_row_pool_and_async_pool(dsn: str, conn: psycopg.Connection[Any]) -> None:
    ip = "198.51.100.3"
    with ConnectionPool(
        dsn, min_size=1, max_size=1, kwargs={"row_factory": dict_row}, open=True
    ) as p:
        store = PostgresRateLimitStore(p.connection)
        await store.log(entry(ip, T0))
        assert await store.requests_since(ip, T0 - timedelta(minutes=1)) == 1
        assert await store.blocked_until(ip) is None
        assert await store.is_banned(ip, T0) is False
        assert await store.strike(ip, T0, T0, T0 - timedelta(hours=24)) == 1
    async with AsyncConnectionPool(
        dsn, min_size=1, max_size=1, kwargs={"row_factory": dict_row}, open=False
    ) as ap:
        astore = AsyncPostgresRateLimitStore(ap.connection)
        await astore.log(entry(ip, T0))
        assert await astore.requests_since(ip, T0 - timedelta(minutes=1)) == 2
        assert await astore.blocked_until(ip) == T0
        await astore.ban(ip, "test", T0)
        assert await astore.is_banned(ip, T0) is True
        assert await astore.is_banned(ip, T0 + timedelta(seconds=1)) is False


def test_purge_keeps_active_bans_up_to_ban_max_days(conn: psycopg.Connection[Any]) -> None:
    old, fresh = T0 - timedelta(days=40), T0 - timedelta(days=1)
    ancient = T0 - timedelta(days=91)
    log = (
        "insert into access_log (at, ip, path, method, status, service) "
        "values (%s, %s, '/', 'GET', 200, 't')"
    )
    block = "insert into ip_blocks (ip, blocked_until, strikes, updated_at) values (%s, %s, 1, %s)"
    ban = "insert into ip_bans (ip, reason, created_at, lifted_at) values (%s, %s, %s, %s)"
    conn.execute(log, (old, "10.0.0.1"))
    conn.execute(log, (fresh, "10.0.0.1"))
    conn.execute(block, ("10.0.0.1", old, old))
    conn.execute(block, ("10.0.0.2", fresh, fresh))
    conn.execute(ban, ("10.0.0.3", "active", old, None))
    conn.execute(ban, ("10.0.0.4", "lifted long ago", old, old))
    conn.execute(ban, ("10.0.0.5", "lifted recently", old, fresh))
    conn.execute(ban, ("10.0.0.6", "active past ban_max_days", ancient, None))
    purge(conn, retention_days=30, ban_max_days=90, now=T0)
    assert conn.execute("select count(*) from access_log").fetchone() == (1,)
    assert conn.execute("select host(ip) from ip_blocks").fetchall() == [("10.0.0.2",)]
    bans = conn.execute("select host(ip) from ip_bans order by ip").fetchall()
    assert bans == [("10.0.0.3",), ("10.0.0.5",)]


async def test_middleware_end_to_end(pool: ConnectionPool, conn: psycopg.Connection[Any]) -> None:
    app = RateLimitMiddleware(
        ok_app,
        RateLimiter(PostgresRateLimitStore(pool.connection), SETTINGS),
        service="t",
        clock=lambda: T0,
    )
    for _ in range(3):
        assert (await run_asgi(app, []))[0] == 204
    status, body = await run_asgi(app, [])
    assert status == 429 and b"too many requests" in body
    rows = conn.execute("select status, host(ip), service from access_log").fetchall()
    assert sorted(r[0] for r in rows) == [204, 204, 204, 429]
    assert {r[1:] for r in rows} == {("10.0.0.5", "t")}
    # the memory store and the PostgreSQL store agree on the same sequence
    mem = RateLimiter(MemoryRateLimitStore(), SETTINGS)
    for _ in range(3):
        await mem.record(entry("10.0.0.5", T0, 204))
    assert (await mem.check("10.0.0.5", T0)).kind == "blocked"


async def test_stores_read_the_stored_rules(dsn: str, conn: psycopg.Connection[Any]) -> None:
    rules = {"per_minute": 1, "block_minutes": 5, "ban_after_strikes": 2, "strike_window_hours": 6}
    with ConnectionPool(dsn, min_size=1, max_size=1, open=True) as p:
        store = PostgresRateLimitStore(p.connection)
        assert await store.rule_overrides() is None
        conn.execute(
            "insert into settings (key, value) values (%s, %s)",
            (RATE_LIMIT_SETTINGS_KEY, Jsonb(rules)),
        )
        assert await store.rule_overrides() == rules
        limiter = RateLimiter(store, SETTINGS)
        await store.log(entry("192.0.2.1", T0))
        decision = await limiter.check("192.0.2.1", T0)
        assert decision.kind == "blocked" and decision.retry_after == 5 * 60
    async with AsyncConnectionPool(
        dsn, min_size=1, max_size=1, kwargs={"row_factory": dict_row}, open=False
    ) as ap:
        assert await AsyncPostgresRateLimitStore(ap.connection).rule_overrides() == rules
