"""Usage accounting against the shared `usage` and `ledger` tables.

Services call these, never write `usage` by hand. The connection is
whatever psycopg 3 connection the service already holds, sync (ingest,
rag) or async (account); the SQL is the same and is exported for a
service that needs to embed it in a larger statement. Core opens no
connections and owns no pool.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from .models import ROLES, USAGE_ACTIONS, Role, UsageRecord, UsageService, is_usage_action
from .pricing import ModelPrices, cost_cents

if TYPE_CHECKING:
    from .billing import PricingRules
    from .providers.base import Usage

_COLUMN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?")


def balance_sql(user_column: str) -> str:
    """The balance of the user in `user_column` as a SQL expression: credits
    minus charges. Usage rows are the only debit. `user_column` is a column
    reference such as `l.owner` (or a placeholder such as `%(user_id)s`),
    for a statement that checks many users at once.

    Rows booked by a release before migration 0006 have no `charge_cents`
    for the moment of the rolling deploy; their cost is their charge."""
    if not (_COLUMN.fullmatch(user_column) or user_column == "%(user_id)s"):
        raise ValueError(f"not a column reference: {user_column!r}")
    return (
        f"(coalesce((select sum(amount_cents) from ledger where user_id = {user_column}), 0)"
        " - coalesce((select sum(coalesce(charge_cents, cost_cents)) from usage"
        f" where user_id = {user_column}), 0))"
    )


def funded_sql(user_column: str) -> str:
    """`balance_sql(user_column) > 0` as a SQL expression: may this user start a model call."""
    return f"({balance_sql(user_column)} > 0)"


BALANCE_SQL = f"select {balance_sql('%(user_id)s')} as balance_cents"

# The admin flag gates the admin endpoints only, never the credit check.
# `users` is account's table; a user without a row (only possible before
# account has written it) is no admin.
IS_ADMIN_SQL = """
select coalesce((select is_admin from users where id = %(user_id)s), false) as is_admin
"""
# The role decides read access to the admin area (viewer, admin); a user
# without a row is a plain user.
ROLE_SQL = """
select coalesce((select role from users where id = %(user_id)s), 'user') as role
"""
# The same rule for every user, admins included: a positive balance.
HAS_CREDIT_SQL = f"select {funded_sql('%(user_id)s')} as has_credit"

USAGE_SQL = """
insert into usage (user_id, notebook_id, service, action, action_id, kind, model,
                   tokens_in, tokens_out, cost_cents, charge_cents)
values (%(user_id)s, %(notebook_id)s, %(service)s, %(action)s, %(action_id)s, %(kind)s,
        %(model)s, %(tokens_in)s, %(tokens_out)s, %(cost_cents)s, %(charge_cents)s)
"""
# An action's fixed fee, once per action_id however many calls it books
# (the partial unique index of migration 0006).
FEE_SQL = USAGE_SQL.rstrip() + "\non conflict (action_id) where kind = 'fee' do nothing\n"


class Cursor(Protocol):
    def execute(self, query: str, params: Mapping[str, Any] | None = ..., /) -> Any: ...
    def fetchone(self) -> Any: ...


class Connection(Protocol):
    """The slice of `psycopg.Connection` this module uses, whatever its row factory."""

    def cursor(self) -> AbstractContextManager[Cursor]: ...


class AsyncCursor(Protocol):
    async def execute(self, query: str, params: Mapping[str, Any] | None = ..., /) -> Any: ...
    async def fetchone(self) -> Any: ...


class AsyncConnection(Protocol):
    """The slice of `psycopg.AsyncConnection` this module uses."""

    def cursor(self) -> AbstractAsyncContextManager[AsyncCursor]: ...


def _priced(
    user_id: UUID,
    notebook_id: UUID | None,
    service: UsageService,
    action: str,
    action_id: UUID,
    usage: Usage,
    prices: ModelPrices,
    rules: PricingRules,
) -> tuple[UsageRecord, UsageRecord | None]:
    """The usage row and, when the action has a fixed fee, its fee row."""
    if not is_usage_action(action):
        raise ValueError(f"unknown action {action!r}; known: {', '.join(sorted(USAGE_ACTIONS))}")
    cost = cost_cents(prices, usage.model, usage.tokens_in, usage.tokens_out)
    row = UsageRecord(
        user_id=user_id,
        notebook_id=notebook_id,
        service=service,
        action=action,
        action_id=action_id,
        kind=usage.kind,
        model=usage.model,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        cost_cents=cost,
        charge_cents=rules.charge_cents(action, cost),
    )
    fixed = rules.fixed_cents(action)
    if not fixed:
        return row, None
    fee = row.model_copy(
        update={
            "kind": "fee",
            "model": "fee",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_cents": Decimal(0),
            "charge_cents": fixed,
        }
    )
    return row, fee


def scalar(row: Any, name: str) -> Any:
    """The one value of a one-column row, whatever the connection's row factory.

    psycopg returns tuples by default and mappings under `dict_row`; the
    services use both, so every scalar query here aliases its column and
    reads it by name when the row is a mapping.
    """
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row[name]
    return row[0]


def _balance(row: Any) -> Decimal:
    value = scalar(row, "balance_cents")
    return Decimal(value) if value is not None else Decimal(0)


def balance_cents(conn: Connection, user_id: UUID) -> Decimal:
    """`sum(ledger.amount_cents) - sum(usage.charge_cents)` for one user, exact."""
    with conn.cursor() as cur:
        cur.execute(BALANCE_SQL, {"user_id": user_id})
        return _balance(cur.fetchone())


def is_admin(conn: Connection, user_id: UUID) -> bool:
    """`users.is_admin` for one user; false when the user has no row."""
    with conn.cursor() as cur:
        cur.execute(IS_ADMIN_SQL, {"user_id": user_id})
        return bool(scalar(cur.fetchone(), "is_admin"))


def _role(row: Any) -> Role:
    value = scalar(row, "role")
    for role in ROLES:
        if value == role:
            return role
    # the column's check constraint makes this unreachable; fail loud anyway
    raise ValueError(f"unknown role {value!r} in users.role")


def admin_role(conn: Connection, user_id: UUID) -> Role:
    """`users.role` for one user: "user", "viewer" or "admin"; "user" without a row."""
    with conn.cursor() as cur:
        cur.execute(ROLE_SQL, {"user_id": user_id})
        return _role(cur.fetchone())


def has_credit(conn: Connection, user_id: UUID) -> bool:
    """May this user start a model call: `balance_cents > 0`, for every user
    alike. The check every service runs before a model call."""
    with conn.cursor() as cur:
        cur.execute(HAS_CREDIT_SQL, {"user_id": user_id})
        return bool(scalar(cur.fetchone(), "has_credit"))


def record_usage(
    conn: Connection,
    user_id: UUID,
    notebook_id: UUID | None,
    service: UsageService,
    action: str,
    action_id: UUID,
    usage: Usage,
    *,
    prices: ModelPrices,
    rules: PricingRules,
) -> UsageRecord:
    """Book one model call of a user action; returns the usage row written.

    Fixes `cost_cents` (the call's units at `prices`) and `charge_cents`
    (the cost under `rules`) now, so a later change of either never
    rewrites history. When the action has a fixed fee, books it as a
    "fee" row once per `action_id`, whichever call comes first. Raises
    `ValueError` for an unknown action and `UnpricedModelError` for an
    unpriced model, both before touching the database. The caller owns
    the transaction.
    """
    row, fee = _priced(user_id, notebook_id, service, action, action_id, usage, prices, rules)
    with conn.cursor() as cur:
        cur.execute(USAGE_SQL, row.model_dump())
        if fee is not None:
            cur.execute(FEE_SQL, fee.model_dump())
    return row


async def abalance_cents(conn: AsyncConnection, user_id: UUID) -> Decimal:
    """`balance_cents` for an async psycopg connection."""
    async with conn.cursor() as cur:
        await cur.execute(BALANCE_SQL, {"user_id": user_id})
        return _balance(await cur.fetchone())


async def ais_admin(conn: AsyncConnection, user_id: UUID) -> bool:
    """`is_admin` for an async psycopg connection."""
    async with conn.cursor() as cur:
        await cur.execute(IS_ADMIN_SQL, {"user_id": user_id})
        return bool(scalar(await cur.fetchone(), "is_admin"))


async def aadmin_role(conn: AsyncConnection, user_id: UUID) -> Role:
    """`admin_role` for an async psycopg connection."""
    async with conn.cursor() as cur:
        await cur.execute(ROLE_SQL, {"user_id": user_id})
        return _role(await cur.fetchone())


async def ahas_credit(conn: AsyncConnection, user_id: UUID) -> bool:
    """`has_credit` for an async psycopg connection."""
    async with conn.cursor() as cur:
        await cur.execute(HAS_CREDIT_SQL, {"user_id": user_id})
        return bool(scalar(await cur.fetchone(), "has_credit"))


async def arecord_usage(
    conn: AsyncConnection,
    user_id: UUID,
    notebook_id: UUID | None,
    service: UsageService,
    action: str,
    action_id: UUID,
    usage: Usage,
    *,
    prices: ModelPrices,
    rules: PricingRules,
) -> UsageRecord:
    """`record_usage` for an async psycopg connection."""
    row, fee = _priced(user_id, notebook_id, service, action, action_id, usage, prices, rules)
    async with conn.cursor() as cur:
        await cur.execute(USAGE_SQL, row.model_dump())
        if fee is not None:
            await cur.execute(FEE_SQL, fee.model_dump())
    return row
