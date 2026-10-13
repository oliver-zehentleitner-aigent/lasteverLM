"""PostgreSQL repository on psycopg 3 with an async connection pool.

Plain SQL, no ORM. Every call that has to be atomic runs in one transaction on
one connection. The schema is ``db/migrations/``; the infra repository applies it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any

from lasteverlm_core import DEMO_USER_ID
from lasteverlm_core.ratelimit import LIFT_BAN_SQL, PURGE_SQL
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .repository import (
    AccessRecord,
    BanRecord,
    BlockRecord,
    CreditTotals,
    LoginRecord,
    StatsRecord,
    UserRecord,
    VisitRecord,
    VisitSummary,
    VoucherRecord,
)

DictPool = AsyncConnectionPool[AsyncConnection[DictRow]]


def _user(row: dict[str, Any]) -> UserRecord:
    return UserRecord(
        id=row["id"],
        email=row["email"],
        is_admin=row["is_admin"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


class PostgresRepository:
    def __init__(self, pool: DictPool) -> None:
        self._pool = pool

    @classmethod
    def from_url(cls, database_url: str, *, max_size: int = 8) -> PostgresRepository:
        pool: DictPool = AsyncConnectionPool(
            database_url,
            min_size=1,
            max_size=max_size,
            open=False,
            connection_class=AsyncConnection[DictRow],
            kwargs={"row_factory": dict_row, "autocommit": True},
        )
        return cls(pool)

    async def open(self) -> None:
        await self._pool.open()

    # settings ---------------------------------------------------------------
    async def get_setting(self, key: str) -> dict[str, Any] | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute("select value from settings where key = %s", (key,))
            row = await cur.fetchone()
        return dict(row["value"]) if row else None

    async def set_setting(self, key: str, value: dict[str, Any]) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into settings (key, value, updated_at) values (%s, %s, now())
                   on conflict (key) do update set value = excluded.value, updated_at = now()""",
                (key, Jsonb(value)),
            )

    async def set_setting_if_missing(self, key: str, value: dict[str, Any]) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """insert into settings (key, value, updated_at) values (%s, %s, now())
                   on conflict (key) do nothing""",
                (key, Jsonb(value)),
            )
            return cur.rowcount == 1

    async def delete_setting(self, key: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute("delete from settings where key = %s", (key,))
            return cur.rowcount == 1

    # users ------------------------------------------------------------------
    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute("select * from users where id = %s", (user_id,))
            row = await cur.fetchone()
        return _user(row) if row else None

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute("select * from users where email = %s", (email,))
            row = await cur.fetchone()
        return _user(row) if row else None

    async def create_user(self, email: str, *, admin: bool, now: datetime) -> UserRecord:
        # "First user ever becomes admin" as one statement: the subquery ignores the
        # demo user the migration seeds. The unique index on email covers the race
        # between two first logins of the same address.
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """insert into users (id, email, is_admin, created_at)
                   values (%s, %s, %s or not exists (select 1 from users where id <> %s), %s)
                   on conflict (email) do nothing
                   returning *""",
                (uuid.uuid4(), email, admin, DEMO_USER_ID, now),
            )
            row = await cur.fetchone()
            if row is None:
                cur = await conn.execute("select * from users where email = %s", (email,))
                row = await cur.fetchone()
        assert row is not None
        return _user(row)

    async def ensure_user(
        self, user_id: uuid.UUID, email: str, *, admin: bool, now: datetime
    ) -> UserRecord:
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into users (id, email, is_admin, created_at) values (%s, %s, %s, %s)
                   on conflict (id) do nothing""",
                (user_id, email, admin, now),
            )
            cur = await conn.execute("select * from users where id = %s", (user_id,))
            row = await cur.fetchone()
        assert row is not None
        return _user(row)

    async def record_login(self, user_id: uuid.UUID, at: datetime) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("insert into login_log (user_id, at) values (%s, %s)", (user_id, at))
            await conn.execute("update users set last_login_at = %s where id = %s", (at, user_id))

    async def list_users(self) -> list[UserRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute("select * from users order by created_at")
            rows = await cur.fetchall()
        return [_user(r) for r in rows]

    async def list_logins(self, limit: int) -> list[LoginRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select l.user_id, u.email, l.at from login_log l
                   join users u on u.id = l.user_id
                   order by l.at desc limit %s""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [LoginRecord(r["user_id"], r["email"], r["at"]) for r in rows]

    # magic links ------------------------------------------------------------
    async def create_magic_link(self, email: str, token_hash: str, expires_at: datetime) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into magic_links (id, user_email, token_hash, expires_at)
                   values (%s, %s, %s, %s)""",
                (uuid.uuid4(), email, token_hash, expires_at),
            )

    async def consume_magic_link(self, token_hash: str, now: datetime) -> str | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """update magic_links set used_at = %s
                   where token_hash = %s and used_at is null and expires_at > %s
                   returning user_email""",
                (now, token_hash, now),
            )
            row = await cur.fetchone()
        return str(row["user_email"]) if row else None

    async def purge_magic_links(self, now: datetime) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute("delete from magic_links where expires_at <= %s", (now,))
            return int(cur.rowcount)

    # credits ----------------------------------------------------------------
    async def create_voucher(
        self, code_hash: str, amount_cents: int, created_by: uuid.UUID, now: datetime
    ) -> uuid.UUID:
        voucher_id = uuid.uuid4()
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into vouchers (id, code_hash, amount_cents, created_by, created_at)
                   values (%s, %s, %s, %s, %s)""",
                (voucher_id, code_hash, amount_cents, created_by, now),
            )
        return voucher_id

    async def redeem_voucher(self, code_hash: str, user_id: uuid.UUID, now: datetime) -> int | None:
        # One transaction: the conditional update claims the voucher (two concurrent
        # redeems serialize on the row and the loser sees redeemed_by set), the ledger
        # insert follows only for the winner.
        async with self._pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                """update vouchers set redeemed_by = %s, redeemed_at = %s
                   where code_hash = %s and redeemed_by is null
                   returning id, amount_cents""",
                (user_id, now, code_hash),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            await conn.execute(
                """insert into ledger (user_id, amount_cents, reason, voucher_id, created_at)
                   values (%s, %s, 'voucher', %s, %s)""",
                (user_id, row["amount_cents"], row["id"], now),
            )
            return int(row["amount_cents"])

    async def credit_totals(self, user_id: uuid.UUID) -> CreditTotals:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select coalesce((select sum(amount_cents) from ledger where user_id = %s), 0)
                          as credited,
                          coalesce((select sum(cost_cents) from usage where user_id = %s), 0)
                          as spent""",
                (user_id, user_id),
            )
            row = await cur.fetchone()
        assert row is not None
        return CreditTotals(int(row["credited"]), int(row["spent"]))

    async def all_credit_totals(self) -> dict[uuid.UUID, CreditTotals]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select u.id, coalesce(l.credited, 0) as credited, coalesce(c.spent, 0) as spent
                   from users u
                   left join (select user_id, sum(amount_cents) credited from ledger
                              group by user_id) l on l.user_id = u.id
                   left join (select user_id, sum(cost_cents) spent from usage
                              group by user_id) c on c.user_id = u.id"""
            )
            rows = await cur.fetchall()
        return {r["id"]: CreditTotals(int(r["credited"]), int(r["spent"])) for r in rows}

    async def list_vouchers(self, limit: int) -> list[VoucherRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select v.id, v.amount_cents, c.email as created_by, v.created_at,
                          r.email as redeemed_by, v.redeemed_at
                   from vouchers v
                   join users c on c.id = v.created_by
                   left join users r on r.id = v.redeemed_by
                   order by v.created_at desc, v.id limit %s""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [
            VoucherRecord(
                r["id"],
                int(r["amount_cents"]),
                r["created_by"],
                r["created_at"],
                r["redeemed_by"],
                r["redeemed_at"],
            )
            for r in rows
        ]

    async def stats(self, since: datetime, now: datetime) -> StatsRecord:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select
                     (select count(*) from users where id <> %(demo)s) as users,
                     (select count(*) from login_log where at >= %(since)s) as logins_since,
                     (select count(*) from vouchers) as vouchers_issued,
                     (select count(*) from vouchers where redeemed_at is not null)
                        as vouchers_redeemed,
                     (select coalesce(sum(amount_cents), 0) from ledger) as credits_granted,
                     (select coalesce(sum(cost_cents), 0) from usage) as usage_total,
                     (select coalesce(sum(cost_cents), 0) from usage where created_at >= %(since)s)
                        as usage_since,
                     (select count(*) from ip_blocks where blocked_until > %(now)s)
                        as blocks_active,
                     (select count(*) from ip_bans where lifted_at is null) as bans_active""",
                {"demo": DEMO_USER_ID, "since": since, "now": now},
            )
            r = await cur.fetchone()
        assert r is not None
        return StatsRecord(
            users=int(r["users"]),
            logins_since=int(r["logins_since"]),
            vouchers_issued=int(r["vouchers_issued"]),
            vouchers_redeemed=int(r["vouchers_redeemed"]),
            credits_granted_cents=int(r["credits_granted"]),
            usage_cost_cents_total=int(r["usage_total"]),
            usage_cost_cents_since=int(r["usage_since"]),
            blocks_active=int(r["blocks_active"]),
            bans_active=int(r["bans_active"]),
        )

    # visits -----------------------------------------------------------------
    async def add_visit(self, visit: VisitRecord) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into visit_log (at, path, user_id, ip_hash, ua_family)
                   values (%s, %s, %s, %s, %s)""",
                (visit.at, visit.path, visit.user_id, visit.ip_hash, visit.ua_family),
            )

    async def purge_visits(self, before: datetime) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute("delete from visit_log where at < %s", (before,))
            return int(cur.rowcount)

    async def visit_summary(self, since: datetime) -> list[VisitSummary]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select (at at time zone 'UTC')::date as day, path,
                          count(*) as visits, count(distinct ip_hash) as unique_visitors
                   from visit_log where at >= %s
                   group by 1, 2 order by 1 desc, 2""",
                (since,),
            )
            rows = await cur.fetchall()
        return [
            VisitSummary(r["day"], r["path"], int(r["visits"]), int(r["unique_visitors"]))
            for r in rows
        ]

    # access control, tables owned by core ------------------------------------
    async def active_blocks(self, now: datetime) -> list[BlockRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select ip, blocked_until, strikes, updated_at from ip_blocks
                   where blocked_until > %s order by blocked_until""",
                (now,),
            )
            rows = await cur.fetchall()
        return [
            BlockRecord(str(r["ip"]), r["blocked_until"], int(r["strikes"]), r["updated_at"])
            for r in rows
        ]

    async def bans(self, *, include_lifted: bool) -> list[BanRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select ip, reason, created_at, lifted_at from ip_bans
                   where %s or lifted_at is null order by created_at desc""",
                (include_lifted,),
            )
            rows = await cur.fetchall()
        return [BanRecord(str(r["ip"]), r["reason"], r["created_at"], r["lifted_at"]) for r in rows]

    async def lift_ban(self, ip: str, now: datetime) -> bool:
        # Core's statement, so the admin action and the middleware agree on what "lifted"
        # means. It stamps the database clock; ``now`` is only used by the memory store.
        del now
        async with self._pool.connection() as conn:
            cur = await conn.execute(LIFT_BAN_SQL, {"ip": ip})
            return cur.rowcount > 0

    async def access_log(self, limit: int) -> list[AccessRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select at, ip, method, path, status, user_id, service from access_log
                   order by at desc limit %s""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [
            AccessRecord(
                r["at"],
                str(r["ip"]),
                r["method"],
                r["path"],
                int(r["status"]),
                r["user_id"],
                r["service"],
            )
            for r in rows
        ]

    async def purge_access_tables(self, params: Mapping[str, datetime]) -> tuple[int, int, int]:
        counts: list[int] = []
        async with self._pool.connection() as conn, conn.transaction():
            for statement in PURGE_SQL:  # core's statements, so both sides agree on the rule
                cur = await conn.execute(statement, dict(params))
                counts.append(cur.rowcount)
        return counts[0], counts[1], counts[2]

    # lifecycle --------------------------------------------------------------
    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[DictRow]]:
        """One pooled connection, for core's rate-limit store (dict rows, autocommit)."""
        return self._pool.connection()

    async def ping(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("select 1")

    async def close(self) -> None:
        await self._pool.close()
