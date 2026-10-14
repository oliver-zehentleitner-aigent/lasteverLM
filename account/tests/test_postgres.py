"""PostgreSQL integration: migrations apply cleanly, voucher redeem is atomic in SQL.

Runs only when ``TEST_DATABASE_URL`` points at an empty, disposable database; the
unit tests cover the service logic against the in-memory repository.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from lasteverlm_core import DEMO_USER_ID, purge_params

from lasteverlm_account.repository import CreditTotals, LoginAttemptRecord, VisitRecord
from lasteverlm_account.repository_postgres import PostgresRepository

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
MIGRATIONS = sorted((Path(__file__).parents[1] / "db" / "migrations").glob("*.sql"))

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set"),
]

# Core's tables, applied before ours in the real migration order. Columns as
# announced by core (core/db/migrations/0002_core_rate_limit.sql).
CORE_TABLES = """
create table if not exists usage (
    id uuid primary key default gen_random_uuid(), user_id uuid not null, notebook_id uuid,
    service text not null,
    kind text not null, model text not null, tokens_in integer not null default 0,
    tokens_out integer not null default 0, cost_cents integer not null default 0,
    created_at timestamptz not null default now()
);
alter table usage alter column cost_cents type numeric using cost_cents::numeric;
alter table usage add column if not exists action text;
alter table usage add column if not exists action_id uuid;
alter table usage add column if not exists charge_cents numeric;
alter table usage add column if not exists cost_usd_cents numeric;
alter table usage add column if not exists usd_per_eur numeric;
create table if not exists access_log (
    id bigserial primary key, at timestamptz not null default now(), ip inet not null,
    path text not null, method text not null, status integer not null, user_id uuid,
    service text not null
);
create table if not exists ip_blocks (
    ip inet primary key, blocked_until timestamptz not null, strikes integer not null default 1,
    updated_at timestamptz not null default now()
);
create table if not exists ip_bans (
    ip inet primary key, reason text not null,
    created_at timestamptz not null default now(), lifted_at timestamptz
)"""


@pytest.fixture
async def repo() -> PostgresRepository:
    assert DATABASE_URL
    repo = PostgresRepository.from_url(DATABASE_URL, max_size=12)
    await repo.open()
    async with repo._pool.connection() as conn:
        await conn.execute(CORE_TABLES)
        for path in MIGRATIONS:
            await conn.execute(path.read_text())
            await conn.execute(path.read_text())  # idempotent
        await conn.execute("delete from ledger where reason <> 'seed'")
        await conn.execute("delete from vouchers")
        await conn.execute("delete from users where id <> %s", (DEMO_USER_ID,))
        await conn.execute("delete from ip_bans")
        await conn.execute("delete from ip_blocks")
    yield repo
    await repo.close()


async def test_demo_user_seeded_with_credit(repo: PostgresRepository) -> None:
    demo = await repo.get_user(DEMO_USER_ID)
    assert demo is not None and demo.email == "demo@localhost" and not demo.is_admin
    assert (await repo.credit_totals(DEMO_USER_ID)).balance_cents == 1000


async def test_first_real_user_is_admin(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    first = await repo.create_user("a@example.org", role="user", now=now)
    second = await repo.create_user("b@example.org", role="user", now=now)
    # The demo user exists before anyone logs in and must not count as "first user".
    assert first.is_admin is True
    assert second.is_admin is False


async def test_redeem_is_atomic_under_concurrency(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("admin@example.org", role="admin", now=now)
    users = [await repo.create_user(f"u{i}@example.org", role="user", now=now) for i in range(10)]
    code_hash = uuid.uuid4().hex
    await repo.create_voucher(code_hash, 700, admin.id, now)

    results = await asyncio.gather(*(repo.redeem_voucher(code_hash, u.id, now) for u in users))
    assert sorted(r for r in results if r is not None) == [700]
    totals = await repo.all_credit_totals()
    assert sum(t.credited_cents for u, t in totals.items() if u != DEMO_USER_ID) == 700


async def test_lift_ban_marks_only_the_active_one(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    async with repo._pool.connection() as conn:
        await conn.execute(
            "insert into ip_bans (ip, reason, lifted_at) values (%s, %s, %s)",
            ("203.0.113.8", "old", now),
        )
        await conn.execute(
            "insert into ip_bans (ip, reason) values (%s, %s)", ("203.0.113.9", "third block")
        )
    assert [b.ip for b in await repo.bans(include_lifted=False)] == ["203.0.113.9"]
    assert await repo.lift_ban("203.0.113.9", now) is True
    assert await repo.lift_ban("203.0.113.9", now) is False
    assert await repo.bans(include_lifted=False) == []
    assert len(await repo.bans(include_lifted=True)) == 2


async def test_purge_access_tables_keeps_active_bans(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    old, fresh = now - timedelta(days=31), now - timedelta(days=29)
    async with repo._pool.connection() as conn:
        await conn.execute("delete from access_log where service = 'test'")
        for at in (old, fresh):
            await conn.execute(
                "insert into access_log (at, ip, path, method, status, service)"
                " values (%s, '203.0.113.1', '/', 'GET', 200, 'test')",
                (at,),
            )
            await conn.execute(
                "insert into ip_blocks (ip, blocked_until, updated_at) values (%s, %s, %s)",
                (f"203.0.113.{10 if at == old else 11}", at, at),
            )
            await conn.execute(
                "insert into ip_bans (ip, reason, lifted_at) values (%s, 'lifted', %s)",
                (f"203.0.113.{20 if at == old else 21}", at),
            )
        await conn.execute("insert into ip_bans (ip, reason) values ('203.0.113.9', 'active')")
        await conn.execute(
            "insert into ip_bans (ip, reason, created_at) values ('203.0.113.8', 'expired', %s)",
            (now - timedelta(days=91),),
        )
    assert await repo.purge_access_tables(purge_params(30, 90, now)) == (1, 1, 2)
    async with repo._pool.connection() as conn:
        cur = await conn.execute("select count(*) as n from access_log where service = 'test'")
        row = await cur.fetchone()
        assert row is not None and row["n"] == 1
    assert [str(b.ip) for b in await repo.active_blocks(fresh - timedelta(seconds=1))] == [
        "203.0.113.11"
    ]
    assert sorted(b.reason for b in await repo.bans(include_lifted=True)) == ["active", "lifted"]


async def test_delete_setting_reports_whether_a_row_went(repo: PostgresRepository) -> None:
    await repo.set_setting("smtp", {"host": "old.test", "password": "old"})
    assert await repo.delete_setting("smtp") is True
    assert await repo.delete_setting("smtp") is False
    assert await repo.get_setting("smtp") is None


async def test_voucher_list_and_stats(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("admin@pg.test", role="admin", now=now - timedelta(days=2))
    user = await repo.create_user("user@pg.test", role="user", now=now)
    await repo.record_login(admin.id, now - timedelta(days=2))
    await repo.record_login(user.id, now)
    open_id = await repo.create_voucher("hash-open", 500, admin.id, now - timedelta(minutes=1))
    used_id = await repo.create_voucher("hash-used", 300, admin.id, now)
    assert await repo.redeem_voucher("hash-used", user.id, now) == 300
    async with repo._pool.connection() as conn:
        await conn.execute("delete from usage where user_id = %s", (user.id,))
        await conn.execute(
            """insert into usage (user_id, service, kind, model, cost_cents, created_at)
               values (%s, 'rag', 'llm', 'm', 120, %s), (%s, 'rag', 'llm', 'm', 80, %s)""",
            (user.id, now - timedelta(hours=30), user.id, now - timedelta(hours=1)),
        )

    rows = await repo.list_vouchers(10)
    assert [(v.id, v.created_by, v.redeemed_by) for v in rows[:2]] == [
        (used_id, "admin@pg.test", "user@pg.test"),
        (open_id, "admin@pg.test", None),
    ]
    assert rows[0].redeemed_at is not None and rows[1].redeemed_at is None
    assert (await repo.list_vouchers(1))[0].id == used_id

    s = await repo.stats(now - timedelta(hours=24), now)
    assert s.users == 3  # admin, user and the seeded demo user, which also holds the seed credit
    assert s.logins_since == 1
    assert (s.vouchers_issued, s.vouchers_redeemed) == (2, 1)
    assert s.credits_granted_cents == 1000 + 300  # demo seed plus the redeemed voucher
    assert (s.usage_cost_cents_total, s.usage_cost_cents_since) == (200, 80)
    assert s.bans_active == 0 and s.blocks_active == 0


async def test_delete_voucher_states(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("admin2@pg.test", role="admin", now=now)
    open_id = await repo.create_voucher("hash-del-open", 100, admin.id, now)
    used_id = await repo.create_voucher("hash-del-used", 100, admin.id, now)
    assert await repo.redeem_voucher("hash-del-used", admin.id, now) == 100
    assert await repo.delete_voucher(open_id) == "deleted"
    assert await repo.delete_voucher(open_id) == "missing"
    assert await repo.delete_voucher(used_id) == "redeemed"
    assert await repo.credit_totals(admin.id) == CreditTotals(100, 0)


async def test_login_attempts_keep_the_plain_ip_and_are_purged(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    async with repo._pool.connection() as conn:
        await conn.execute("delete from login_attempts")
    await repo.add_login_attempt(
        LoginAttemptRecord(now - timedelta(days=31), "old@pg.test", "203.0.113.1", "refused")
    )
    await repo.add_login_attempt(LoginAttemptRecord(now, "new@pg.test", "2001:db8::7", "allowed"))
    rows = await repo.list_login_attempts(10)
    assert [(a.email, a.ip, a.outcome) for a in rows] == [
        ("new@pg.test", "2001:db8::7", "allowed"),
        ("old@pg.test", "203.0.113.1", "refused"),
    ]
    assert await repo.purge_login_attempts(now - timedelta(days=30)) == 1
    assert [a.email for a in await repo.list_login_attempts(10)] == ["new@pg.test"]


async def test_ratelimit_override_is_what_core_store_reads(repo: PostgresRepository) -> None:
    from lasteverlm_core import RATE_LIMIT_SETTINGS_KEY, AsyncPostgresRateLimitStore, RateLimitRules

    store = AsyncPostgresRateLimitStore(repo.connection)
    await repo.delete_setting(RATE_LIMIT_SETTINGS_KEY)
    assert await store.rule_overrides() is None
    rules = RateLimitRules(
        per_minute=7, block_minutes=1, ban_after_strikes=1, strike_window_hours=1
    )
    await repo.set_setting(RATE_LIMIT_SETTINGS_KEY, rules.as_json())
    assert RateLimitRules.parse(await store.rule_overrides()) == rules
    await repo.delete_setting(RATE_LIMIT_SETTINGS_KEY)


async def test_daily_and_usage_stats(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    today = now.astimezone(UTC).date()
    admin = await repo.create_user("stats-admin@pg.test", role="admin", now=now)
    user = await repo.create_user("stats-user@pg.test", role="user", now=now)
    await repo.record_login(user.id, now)
    await repo.add_visit(VisitRecord(now, "/", None, "h", "other"))
    await repo.add_visit(VisitRecord(now - timedelta(days=1), "/", None, "h", "other"))
    await repo.create_voucher("hash-stats", 250, admin.id, now)
    assert await repo.redeem_voucher("hash-stats", user.id, now) == 250
    async with repo._pool.connection() as conn:
        await conn.execute("delete from usage")
        await conn.execute(
            """insert into usage (user_id, service, kind, model, cost_cents, created_at) values
               (%s, 'rag', 'llm', 'big', 30, %s), (%s, 'rag', 'llm', 'big', 10, %s),
               (%s, 'ingest', 'embedding', 'emb', 4, %s)""",
            (user.id, now, user.id, now, admin.id, now),
        )

    days = {d.day: d for d in await repo.daily_stats(now - timedelta(days=2))}
    assert days[today].logins >= 1 and days[today].visits >= 1
    assert days[today].usage_cost_cents == 44 and days[today].credits_granted_cents >= 250
    assert (today - timedelta(days=1)) in days

    models = await repo.usage_by_model()
    assert [(m.model, m.kind, m.calls, m.cost_cents) for m in models] == [
        ("big", "llm", 2, 40),
        ("emb", "embedding", 1, 4),
    ]
    top = await repo.top_users_by_usage(10)
    assert [(t.email, t.usage_cents, t.balance_cents) for t in top][:2] == [
        ("stats-user@pg.test", 40, 210),
        ("stats-admin@pg.test", 4, -4),
    ]


async def test_preferences_round_trip(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    user = await repo.create_user("prefs@pg.test", role="user", now=now)
    assert user.preferences == {}
    await repo.set_preferences(user.id, {"ui_language": "de", "audio_voice": "ryan"})
    stored = await repo.get_user(user.id)
    assert stored is not None and stored.preferences == {"ui_language": "de", "audio_voice": "ryan"}
    assert (await repo.get_user_by_email("prefs@pg.test")).preferences["ui_language"] == "de"  # type: ignore[union-attr]


async def test_count_allowed_attempts_per_address(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    async with repo._pool.connection() as conn:
        await conn.execute("delete from login_attempts where email like 'quota%%'")
    for minutes, outcome in ((5, "allowed"), (30, "allowed"), (90, "allowed"), (1, "refused")):
        await repo.add_login_attempt(
            LoginAttemptRecord(
                now - timedelta(minutes=minutes),
                "quota@pg.test",
                "203.0.113.1",
                "allowed" if outcome == "allowed" else "refused",
            )
        )
    await repo.add_login_attempt(
        LoginAttemptRecord(now, "quota-other@pg.test", "203.0.113.1", "allowed")
    )
    assert await repo.count_allowed_attempts("quota@pg.test", now - timedelta(hours=1)) == 2


async def test_roles_round_trip_and_is_admin_stays_in_sync(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("roles-admin@pg.test", role="admin", now=now)
    viewer = await repo.create_user("roles-viewer@pg.test", role="viewer", now=now)
    plain = await repo.create_user("roles-user@pg.test", role="user", now=now)
    assert (admin.role, admin.is_admin) == ("admin", True)
    assert (viewer.role, viewer.is_admin) == ("viewer", False)
    assert (plain.role, plain.is_admin) == ("user", False)
    assert await repo.count_admins() >= 1
    before = await repo.count_admins()
    assert await repo.set_role(plain.id, "admin") is True
    assert await repo.count_admins() == before + 1
    stored = await repo.get_user(plain.id)
    assert stored is not None and (stored.role, stored.is_admin) == ("admin", True)
    assert await repo.set_role(uuid.uuid4(), "viewer") is False


async def test_delete_user_keeps_vouchers_and_attempts_as_history(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("del-admin@pg.test", role="admin", now=now)
    user = await repo.create_user("del-user@pg.test", role="user", now=now)
    await repo.record_login(user.id, now)
    await repo.add_login_attempt(
        LoginAttemptRecord(now, "del-user@pg.test", "203.0.113.1", "allowed")
    )
    await repo.create_voucher("hash-del-by-admin", 100, admin.id, now)
    await repo.create_voucher("hash-del-by-user", 100, user.id, now)
    assert await repo.redeem_voucher("hash-del-by-admin", user.id, now) == 100
    await repo.add_visit(VisitRecord(now, "/", user.id, "h", "other"))
    async with repo._pool.connection() as conn:
        await conn.execute(
            """insert into usage (user_id, service, kind, model, cost_cents, created_at)
               values (%s, 'rag', 'llm', 'm', 3, %s)""",
            (user.id, now),
        )

    assert await repo.delete_user(user.id) is True
    assert await repo.delete_user(user.id) is False
    assert await repo.get_user(user.id) is None
    vouchers = {v.created_by: v for v in await repo.list_vouchers(50) if v.redeemed_by is None}
    assert "" in vouchers  # the voucher the deleted user created, creator blank
    assert any(a.email == "del-user@pg.test" for a in await repo.list_login_attempts(50))
    async with repo._pool.connection() as conn:
        cur = await conn.execute("select count(*) as n from usage where user_id = %s", (user.id,))
        assert (await cur.fetchone())["n"] == 0  # type: ignore[index]
        cur = await conn.execute(
            "select count(*) as n from visit_log where user_id = %s", (user.id,)
        )
        assert (await cur.fetchone())["n"] == 0  # type: ignore[index]
        cur = await conn.execute(
            "select count(*) as n from login_log where user_id = %s", (user.id,)
        )
        assert (await cur.fetchone())["n"] == 0  # type: ignore[index]


async def test_voucher_code_enc_and_sent_fields(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("vc-admin@pg.test", role="admin", now=now)
    vid = await repo.create_voucher("hash-vc-1", 300, admin.id, now, code_enc="sealed")
    old = await repo.create_voucher("hash-vc-old", 300, admin.id, now)
    got = await repo.get_voucher(vid)
    assert got is not None and got.code_enc == "sealed" and got.sent_to is None
    assert (await repo.get_voucher(old)).code_enc is None  # type: ignore[union-attr]
    assert await repo.get_voucher(uuid.uuid4()) is None
    await repo.mark_voucher_sent(vid, "friend@pg.test", now)
    got = await repo.get_voucher(vid)
    assert got is not None and got.sent_to == "friend@pg.test" and got.sent_at is not None
    assert await repo.count_voucher_mails("friend@pg.test", now - timedelta(hours=1)) == 1
    assert await repo.count_voucher_mails("friend@pg.test", now + timedelta(seconds=1)) == 0
    listed = {v.id: v for v in await repo.list_vouchers(200)}
    assert listed[vid].code_enc == "sealed" and listed[vid].sent_to == "friend@pg.test"


async def test_infra_costs_and_paid_vouchers(repo: PostgresRepository) -> None:
    from datetime import date

    from lasteverlm_account.repository import InfraCostRecord

    async with repo._pool.connection() as conn:
        await conn.execute("delete from infra_costs")
    month = date(2026, 9, 1)
    line = InfraCostRecord(uuid.uuid4(), month, "vultr", "postgres", 1500, "USD")
    assert await repo.upsert_infra_costs("vultr", [line]) == 1
    await repo.upsert_infra_costs(
        "vultr", [InfraCostRecord(uuid.uuid4(), month, "vultr", "postgres", 1600, "USD")]
    )
    rows = await repo.list_infra_costs(month, date(2026, 9, 30))
    assert [(r.item, r.amount_cents) for r in rows] == [("postgres", 1600)]
    manual = InfraCostRecord(uuid.uuid4(), date(2026, 9, 15), "manual", "domain", 1200, "EUR")
    assert await repo.add_infra_cost(manual) is True
    assert (
        await repo.add_infra_cost(
            InfraCostRecord(uuid.uuid4(), date(2026, 9, 15), "manual", "domain", 1, "EUR")
        )
        is False
    )
    assert await repo.delete_infra_cost(rows[0].id) == "not_manual"
    assert await repo.delete_infra_cost(manual.id) == "deleted"
    assert await repo.delete_infra_cost(manual.id) == "missing"

    now = datetime.now(UTC)
    admin = await repo.create_user("fin-admin@pg.test", role="admin", now=now)
    vid = await repo.create_voucher("hash-fin-paid", 500, admin.id, now, paid=True)
    assert (await repo.get_voucher(vid)).paid is True  # type: ignore[union-attr]
    assert await repo.set_voucher_paid(vid, False) is True
    assert (await repo.get_voucher(vid)).paid is False  # type: ignore[union-attr]
    assert await repo.set_voucher_paid(uuid.uuid4(), True) is False


async def test_finance_aggregates_on_charge_and_cost(repo: PostgresRepository) -> None:
    from datetime import date
    from decimal import Decimal

    now = datetime.now(UTC)
    today = now.astimezone(UTC).date()
    user = await repo.create_user("fin-user@pg.test", role="user", now=now)
    a1 = uuid.uuid4()
    async with repo._pool.connection() as conn:
        await conn.execute("delete from usage")
        await conn.execute(
            """insert into usage (user_id, service, kind, model, cost_cents, charge_cents,
                                  action, action_id, created_at)
               values (%s, 'rag', 'llm', 'big', 4, 5.5, 'chat_answer', %s, %s),
                      (%s, 'rag', 'fee', 'fee', 0, 2, 'chat_answer', %s, %s),
                      (%s, 'rag', 'llm', 'big', 3, 3, 'demo_seed', %s, %s)""",
            (user.id, a1, now, user.id, a1, now, DEMO_USER_ID, uuid.uuid4(), now),
        )
    totals = await repo.credit_totals(user.id)
    assert totals.usage_cents == Decimal("7.5")
    groups = {g.key: g for g in await repo.usage_groups(today, today, "action")}
    assert groups["chat_answer"].calls == 1 and groups["chat_answer"].actions == 1
    assert groups["chat_answer"].charge_cents == Decimal("7.5")
    assert {g.key for g in await repo.usage_groups(today, today, "user")} >= {"fin-user@pg.test"}
    periods = await repo.usage_periods(today, today, "month")
    demo = [p for p in periods if p.demo]
    assert demo and demo[0].cost_cents == 3 and demo[0].period == today.replace(day=1)
    averages = {a.action: a for a in await repo.action_averages(now - timedelta(days=1))}
    assert averages["chat_answer"].avg_cost_cents == 4  # the fee row is excluded
    money = await repo.voucher_money(date(2000, 1, 1), today)
    assert money.issued_paid_cents >= 0


async def test_migrations_seed_the_pricing_rate_once(repo: PostgresRepository) -> None:
    from lasteverlm_core import PRICING_SETTINGS_KEY, PricingRules

    seeded = await repo.get_setting(PRICING_SETTINGS_KEY)
    assert seeded is not None and PricingRules.parse(seeded).usd_per_eur is not None
    await repo.set_setting(
        PRICING_SETTINGS_KEY, {"usd_per_eur": 1.2, "default_margin_pct": 5, "actions": {}}
    )
    async with repo._pool.connection() as conn:
        for path in MIGRATIONS:
            await conn.execute(path.read_text())  # a re-run never overwrites the admin's row
    assert (await repo.get_setting(PRICING_SETTINGS_KEY)) == {
        "usd_per_eur": 1.2,
        "default_margin_pct": 5,
        "actions": {},
    }


async def test_action_samples_group_per_action_id(repo: PostgresRepository) -> None:
    now = datetime.now(UTC)
    user = await repo.create_user("samples@pg.test", role="user", now=now)
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    async with repo._pool.connection() as conn:
        await conn.execute("delete from usage")
        await conn.execute(
            """insert into usage (user_id, service, kind, model, tokens_in, cost_cents, action,
                                  action_id, created_at)
               values (%(u)s, 'rag', 'llm', 'big', 100, 2, 'output:audio', %(a1)s, %(t)s),
                      (%(u)s, 'rag', 'tts', 'voice', 90, 3, 'output:audio', %(a1)s, %(t)s),
                      (%(u)s, 'rag', 'fee', 'fee', 0, 0, 'output:audio', %(a1)s, %(t)s),
                      (%(u)s, 'rag', 'llm', 'big', 50, 4, 'chat_answer', %(a2)s, %(t)s),
                      (%(u)s, 'rag', 'llm', 'big', 50, 9, 'unknown', %(a2)s, %(t)s)""",
            {"u": user.id, "a1": a1, "a2": a2, "t": now},
        )
    samples = sorted(await repo.action_samples(now - timedelta(days=1)), key=lambda s: s.action)
    assert [(s.action, s.cost_cents, s.seconds) for s in samples] == [
        ("chat_answer", 4, 0),
        ("output:audio", 5, 90),
    ]
    assert samples[1].model in ("big", "voice")


async def test_notebook_readiness_reads_ingest_tables(repo: PostgresRepository) -> None:
    async with repo._pool.connection() as conn:
        await conn.execute(
            """create table if not exists notebooks (id uuid primary key, owner uuid not null);
               create table if not exists sources (
                   id uuid primary key, notebook_id uuid not null references notebooks (id)
                   on delete cascade, status text not null)"""
        )
        owner, nb, empty = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await conn.execute(
            "insert into notebooks values (%s, %s), (%s, %s)", (nb, owner, empty, owner)
        )
        for status in ("ready", "ready", "processing"):
            await conn.execute(
                "insert into sources values (%s, %s, %s)", (uuid.uuid4(), nb, status)
            )
    got = await repo.notebook_readiness(nb)
    assert got is not None and (got.owner_id, got.sources, got.ready) == (owner, 3, 2)
    assert (await repo.notebook_readiness(empty)).sources == 0  # type: ignore[union-attr]
    assert await repo.notebook_readiness(uuid.uuid4()) is None
