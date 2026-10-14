"""PostgreSQL repository on psycopg 3 with an async connection pool.

Plain SQL, no ORM. Every call that has to be atomic runs in one transaction on
one connection. The schema is ``db/migrations/``; the infra repository applies it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from datetime import date, datetime
from typing import Any, Literal

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
    DailyStatsRecord,
    InfraCostRecord,
    LoginAttemptRecord,
    LoginRecord,
    ModelUsageRecord,
    StatsRecord,
    UserRecord,
    UserUsageRecord,
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
        preferences=dict(row.get("preferences") or {}),
        role=str(row.get("role") or ("admin" if row["is_admin"] else "user")),
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

    async def create_user(self, email: str, *, role: str, now: datetime) -> UserRecord:
        # "First real user becomes admin" as one statement: the subquery ignores the demo
        # user the migration seeds. The unique index on email covers the race between two
        # first logins of the same address. is_admin is written alongside role (core reads it).
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """with wanted as (
                       select case when %(role)s = 'admin'
                                     or not exists (select 1 from users where id <> %(demo)s)
                                   then 'admin' else %(role)s end as role)
                   insert into users (id, email, role, is_admin, created_at)
                   select %(id)s, %(email)s, role, role = 'admin', %(now)s from wanted
                   on conflict (email) do nothing
                   returning *""",
                {
                    "id": uuid.uuid4(),
                    "email": email,
                    "role": role,
                    "demo": DEMO_USER_ID,
                    "now": now,
                },
            )
            row = await cur.fetchone()
            if row is None:
                cur = await conn.execute("select * from users where email = %s", (email,))
                row = await cur.fetchone()
        assert row is not None
        return _user(row)

    async def set_role(self, user_id: uuid.UUID, role: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "update users set role = %s, is_admin = (%s = 'admin') where id = %s",
                (role, role, user_id),
            )
            return cur.rowcount == 1

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                "update vouchers set created_by = null where created_by = %s", (user_id,)
            )
            await conn.execute(
                "update vouchers set redeemed_by = null where redeemed_by = %s", (user_id,)
            )
            await conn.execute("delete from usage where user_id = %s", (user_id,))
            await conn.execute("update visit_log set user_id = null where user_id = %s", (user_id,))
            cur = await conn.execute("delete from users where id = %s", (user_id,))
            return cur.rowcount == 1

    async def count_admins(self) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute("select count(*) as n from users where role = 'admin'")
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def set_preferences(self, user_id: uuid.UUID, preferences: dict[str, Any]) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "update users set preferences = %s where id = %s", (Jsonb(preferences), user_id)
            )

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

    async def add_login_attempt(self, attempt: LoginAttemptRecord) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "insert into login_attempts (at, email, ip, outcome) values (%s, %s, %s, %s)",
                (attempt.at, attempt.email, attempt.ip, attempt.outcome),
            )

    async def list_login_attempts(self, limit: int) -> list[LoginAttemptRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select at, email, ip, outcome from login_attempts
                   order by at desc, id desc limit %s""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [
            LoginAttemptRecord(
                r["at"],
                r["email"],
                str(r["ip"]),
                "allowed" if r["outcome"] == "allowed" else "refused",
            )
            for r in rows
        ]

    async def count_allowed_attempts(self, email: str, since: datetime) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select count(*) as n from login_attempts
                   where email = %s and outcome = 'allowed' and at >= %s""",
                (email, since),
            )
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def purge_login_attempts(self, before: datetime) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute("delete from login_attempts where at < %s", (before,))
            return int(cur.rowcount)

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
        self,
        code_hash: str,
        amount_cents: int,
        created_by: uuid.UUID,
        now: datetime,
        code_enc: str | None = None,
        paid: bool = False,
    ) -> uuid.UUID:
        voucher_id = uuid.uuid4()
        async with self._pool.connection() as conn:
            await conn.execute(
                """insert into vouchers
                       (id, code_hash, code_enc, amount_cents, created_by, created_at, paid)
                   values (%s, %s, %s, %s, %s, %s, %s)""",
                (voucher_id, code_hash, code_enc, amount_cents, created_by, now, paid),
            )
        return voucher_id

    _VOUCHER_SELECT = """select v.id, v.amount_cents, c.email as created_by, v.created_at,
                                r.email as redeemed_by, v.redeemed_at, v.code_enc, v.sent_to,
                                v.sent_at, v.paid
                         from vouchers v
                         left join users c on c.id = v.created_by
                         left join users r on r.id = v.redeemed_by"""

    @staticmethod
    def _voucher(r: dict[str, Any]) -> VoucherRecord:
        return VoucherRecord(
            r["id"],
            int(r["amount_cents"]),
            r["created_by"] or "",
            r["created_at"],
            r["redeemed_by"],
            r["redeemed_at"],
            r["code_enc"],
            r["sent_to"],
            r["sent_at"],
            bool(r["paid"]),
        )

    async def set_voucher_paid(self, voucher_id: uuid.UUID, paid: bool) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "update vouchers set paid = %s where id = %s", (paid, voucher_id)
            )
            return cur.rowcount == 1

    async def upsert_infra_costs(self, source: str, lines: list[InfraCostRecord]) -> int:
        async with self._pool.connection() as conn, conn.transaction():
            for line in lines:
                await conn.execute(
                    """insert into infra_costs (id, date, source, item, amount_cents, currency)
                       values (%s, %s, %s, %s, %s, %s)
                       on conflict (date, source, item) do update
                       set amount_cents = excluded.amount_cents,
                           currency = excluded.currency, updated_at = now()""",
                    (line.id, line.date, source, line.item, line.amount_cents, line.currency),
                )
        return len(lines)

    async def add_infra_cost(self, record: InfraCostRecord) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """insert into infra_costs (id, date, source, item, amount_cents, currency)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (date, source, item) do nothing""",
                (
                    record.id,
                    record.date,
                    record.source,
                    record.item,
                    record.amount_cents,
                    record.currency,
                ),
            )
            return cur.rowcount == 1

    async def delete_infra_cost(self, cost_id: uuid.UUID) -> str:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "delete from infra_costs where id = %s and source = 'manual'", (cost_id,)
            )
            if cur.rowcount == 1:
                return "deleted"
            cur = await conn.execute("select 1 from infra_costs where id = %s", (cost_id,))
            return "not_manual" if await cur.fetchone() else "missing"

    async def list_infra_costs(self, since: date, until: date) -> list[InfraCostRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select id, date, source, item, amount_cents, currency from infra_costs
                   where date between %s and %s order by date, source, item""",
                (since, until),
            )
            rows = await cur.fetchall()
        return [
            InfraCostRecord(
                r["id"], r["date"], r["source"], r["item"], int(r["amount_cents"]), r["currency"]
            )
            for r in rows
        ]

    async def get_voucher(self, voucher_id: uuid.UUID) -> VoucherRecord | None:
        async with self._pool.connection() as conn:
            cur = await conn.execute(self._VOUCHER_SELECT + " where v.id = %s", (voucher_id,))
            row = await cur.fetchone()
        return self._voucher(row) if row else None

    async def mark_voucher_sent(self, voucher_id: uuid.UUID, email: str, at: datetime) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "update vouchers set sent_to = %s, sent_at = %s where id = %s",
                (email, at, voucher_id),
            )

    async def count_voucher_mails(self, email: str, since: datetime) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "select count(*) as n from vouchers where sent_to = %s and sent_at >= %s",
                (email, since),
            )
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

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

    async def delete_voucher(
        self, voucher_id: uuid.UUID
    ) -> Literal["deleted", "redeemed", "missing"]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "delete from vouchers where id = %s and redeemed_at is null", (voucher_id,)
            )
            if cur.rowcount == 1:
                return "deleted"
            cur = await conn.execute("select 1 from vouchers where id = %s", (voucher_id,))
            return "redeemed" if await cur.fetchone() else "missing"

    async def list_vouchers(self, limit: int) -> list[VoucherRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                self._VOUCHER_SELECT + " order by v.created_at desc, v.id limit %s", (limit,)
            )
            rows = await cur.fetchall()
        return [self._voucher(r) for r in rows]

    async def stats(self, since: datetime, now: datetime) -> StatsRecord:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select
                     (select count(*) from users) as users,
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
                {"since": since, "now": now},
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

    async def daily_stats(self, since: datetime) -> list[DailyStatsRecord]:
        # One statement: each source aggregated per UTC day, joined on the day.
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """with l as (select (at at time zone 'UTC')::date d, count(*) n
                              from login_log where at >= %(since)s group by 1),
                        v as (select (at at time zone 'UTC')::date d, count(*) n
                              from visit_log where at >= %(since)s group by 1),
                        u as (select (created_at at time zone 'UTC')::date d, sum(cost_cents) n
                              from usage where created_at >= %(since)s group by 1),
                        g as (select (created_at at time zone 'UTC')::date d, sum(amount_cents) n
                              from ledger where created_at >= %(since)s group by 1)
                   select d, coalesce(l.n, 0) logins, coalesce(v.n, 0) visits,
                          coalesce(u.n, 0) usage_cost, coalesce(g.n, 0) granted
                   from (select d from l union select d from v
                         union select d from u union select d from g) days
                   left join l using (d) left join v using (d)
                   left join u using (d) left join g using (d)
                   order by d""",
                {"since": since},
            )
            rows = await cur.fetchall()
        return [
            DailyStatsRecord(
                r["d"], int(r["logins"]), int(r["visits"]), int(r["usage_cost"]), int(r["granted"])
            )
            for r in rows
        ]

    async def usage_by_model(self) -> list[ModelUsageRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute("""select model, kind, count(*) calls, sum(cost_cents) cost
                   from usage group by model, kind order by cost desc, model, kind""")
            rows = await cur.fetchall()
        return [
            ModelUsageRecord(r["model"], r["kind"], int(r["calls"]), int(r["cost"])) for r in rows
        ]

    async def top_users_by_usage(self, limit: int) -> list[UserUsageRecord]:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """select u.email, c.spent as usage_cents,
                          coalesce(l.credited, 0) - c.spent as balance_cents
                   from (select user_id, sum(cost_cents) spent from usage group by user_id) c
                   join users u on u.id = c.user_id
                   left join (select user_id, sum(amount_cents) credited from ledger
                              group by user_id) l on l.user_id = u.id
                   order by c.spent desc, u.email limit %s""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [
            UserUsageRecord(r["email"], int(r["usage_cents"]), int(r["balance_cents"]))
            for r in rows
        ]

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
