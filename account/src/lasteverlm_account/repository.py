"""Storage interface. Two implementations: PostgreSQL for deployment, in-memory for tests.

All multi-step mutations that must be atomic (consuming a magic link, redeeming a
voucher, creating the first user) are single repository calls, so each
implementation can make them atomic in its own way and the service layer stays
free of transaction handling.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    email: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None
    preferences: dict[str, Any] = field(default_factory=dict)  # the stored jsonb, as is
    role: str = "user"  # 'user' | 'viewer' | 'admin'; is_admin is kept equal to role == 'admin'


@dataclass(frozen=True)
class LoginRecord:
    user_id: uuid.UUID
    email: str
    at: datetime


@dataclass(frozen=True)
class LoginAttemptRecord:
    """A request for a sign-in link, allowed or refused, with the plain client address."""

    at: datetime
    email: str
    ip: str
    outcome: Literal["allowed", "refused"]


@dataclass(frozen=True)
class VisitRecord:
    at: datetime
    path: str
    user_id: uuid.UUID | None
    ip_hash: str
    ua_family: str


@dataclass(frozen=True)
class VisitSummary:
    """Visits per UTC day and path; ``unique`` counts distinct daily visitor hashes."""

    day: date
    path: str
    visits: int
    unique: int


@dataclass(frozen=True)
class BlockRecord:
    """A temporary block written by core's rate-limit middleware."""

    ip: str
    blocked_until: datetime
    strikes: int
    updated_at: datetime


@dataclass(frozen=True)
class BanRecord:
    ip: str
    reason: str
    created_at: datetime
    lifted_at: datetime | None


@dataclass(frozen=True)
class AccessRecord:
    """One request as logged by core's middleware. The only place a raw IP is kept."""

    at: datetime
    ip: str
    method: str
    path: str
    status: int
    user_id: uuid.UUID | None
    service: str


@dataclass(frozen=True)
class VoucherRecord:
    """One voucher as the admin list shows it. The code is stored as a hash (redeem) and,
    since 0008, encrypted (``code_enc``, None for older rows); the service decrypts."""

    id: uuid.UUID
    amount_cents: int
    created_by: str  # email
    created_at: datetime
    redeemed_by: str | None  # email
    redeemed_at: datetime | None
    code_enc: str | None = None
    sent_to: str | None = None
    sent_at: datetime | None = None
    paid: bool = False


@dataclass(frozen=True)
class InfraCostRecord:
    id: uuid.UUID
    date: date  # first day of the month for 'vultr', any day for 'manual'
    source: str  # 'vultr' | 'manual'
    item: str
    amount_cents: int
    currency: str  # 'USD' | 'EUR'


@dataclass(frozen=True)
class DailyStatsRecord:
    """One UTC day of the overview charts; the repository returns only days with activity."""

    day: date
    logins: int
    visits: int
    usage_cost_cents: int
    credits_granted_cents: int


@dataclass(frozen=True)
class ModelUsageRecord:
    model: str
    kind: str
    calls: int
    cost_cents: int


@dataclass(frozen=True)
class UserUsageRecord:
    email: str
    usage_cents: int
    balance_cents: int


@dataclass(frozen=True)
class StatsRecord:
    """Counters for the admin overview; `since` is the 24 h window the caller passes."""

    users: int  # every row, the seeded demo user included (it holds and spends credit)
    logins_since: int
    vouchers_issued: int
    vouchers_redeemed: int
    credits_granted_cents: int  # sum of the ledger, the demo seed included
    usage_cost_cents_total: int  # core's usage rows
    usage_cost_cents_since: int
    blocks_active: int
    bans_active: int


@dataclass(frozen=True)
class CreditTotals:
    """Credits and what the user was charged (core's usage.charge_cents, sub-cent exact)."""

    credited_cents: int
    usage_cents: Decimal  # charged, not the real cost

    @property
    def balance_cents(self) -> int:
        """Whole cents the user can still spend: rounded down, never in the user's favour."""
        return math.floor(self.credited_cents - Decimal(self.usage_cents))

    @property
    def usage_cents_whole(self) -> int:
        return math.ceil(Decimal(self.usage_cents))


@dataclass(frozen=True)
class UsageGroupRecord:
    key: str
    calls: int  # usage rows except fixed fees
    actions: int  # distinct actions
    cost_cents: Decimal  # real cost
    charge_cents: Decimal  # charged to users


@dataclass(frozen=True)
class UsagePeriodRecord:
    period: date  # first day of the day or month
    demo: bool  # the shared demo user's usage, paid by seed credit, not money
    cost_cents: Decimal
    charge_cents: Decimal


@dataclass(frozen=True)
class ActionAverageRecord:
    action: str
    actions: int
    avg_cost_cents: Decimal  # mean real cost of one action, fees excluded


@dataclass(frozen=True)
class VoucherMoneyRecord:
    issued_paid_cents: int
    issued_free_cents: int
    redeemed_paid_cents: int
    redeemed_free_cents: int


class Repository(Protocol):
    # settings ---------------------------------------------------------------
    async def get_setting(self, key: str) -> dict[str, Any] | None: ...
    async def set_setting(self, key: str, value: dict[str, Any]) -> None: ...
    async def set_setting_if_missing(self, key: str, value: dict[str, Any]) -> bool: ...
    async def delete_setting(self, key: str) -> bool: ...

    # users ------------------------------------------------------------------
    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None: ...
    async def get_user_by_email(self, email: str) -> UserRecord | None: ...
    async def create_user(self, email: str, *, role: str, now: datetime) -> UserRecord:
        """Create a user with ``role``; the very first real user is an admin regardless."""
        ...

    async def set_role(self, user_id: uuid.UUID, role: str) -> bool:
        """Change a user's role (and is_admin with it); False when the user does not exist."""
        ...

    async def count_admins(self) -> int: ...
    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """Hard delete of the user's own rows: the user (ledger and login log cascade), the
        usage rows, the visit log's reference; vouchers stay as history without the reference.
        login_attempts keep the e-mail. False when there is no such user."""
        ...

    async def record_login(self, user_id: uuid.UUID, at: datetime) -> None: ...
    async def set_preferences(self, user_id: uuid.UUID, preferences: dict[str, Any]) -> None:
        """Replace the stored preferences object; the service merges before calling."""
        ...

    async def list_users(self) -> list[UserRecord]: ...
    async def list_logins(self, limit: int) -> list[LoginRecord]: ...
    async def add_login_attempt(self, attempt: LoginAttemptRecord) -> None: ...
    async def list_login_attempts(self, limit: int) -> list[LoginAttemptRecord]: ...
    async def count_allowed_attempts(self, email: str, since: datetime) -> int:
        """Sign-in links sent to this address since `since`; the per-address quota."""
        ...

    async def purge_login_attempts(self, before: datetime) -> int: ...

    # magic links ------------------------------------------------------------
    async def create_magic_link(
        self, email: str, token_hash: str, expires_at: datetime
    ) -> None: ...
    async def consume_magic_link(self, token_hash: str, now: datetime) -> str | None:
        """Mark the link used and return its email, or None if unknown, used or expired."""
        ...

    async def purge_magic_links(self, now: datetime) -> int: ...

    # credits ----------------------------------------------------------------
    async def create_voucher(
        self,
        code_hash: str,
        amount_cents: int,
        created_by: uuid.UUID,
        now: datetime,
        code_enc: str | None = None,
        paid: bool = False,
    ) -> uuid.UUID: ...
    async def set_voucher_paid(self, voucher_id: uuid.UUID, paid: bool) -> bool: ...
    async def upsert_infra_costs(self, source: str, lines: list[InfraCostRecord]) -> int:
        """Insert or update by (date, source, item); returns the rows written."""
        ...

    async def add_infra_cost(self, record: InfraCostRecord) -> bool:
        """False when (date, source, item) exists already."""
        ...

    async def delete_infra_cost(self, cost_id: uuid.UUID) -> str:
        """'deleted' | 'not_manual' | 'missing'."""
        ...

    async def list_infra_costs(self, since: date, until: date) -> list[InfraCostRecord]: ...
    async def usage_groups(self, since: date, until: date, group: str) -> list[UsageGroupRecord]:
        """Usage of [since, until] (UTC days) grouped by day | action | model | user | service."""
        ...

    async def usage_periods(self, since: date, until: date, period: str) -> list[UsagePeriodRecord]:
        """Cost and charge per day or month, the demo user's share apart."""
        ...

    async def action_averages(self, since: datetime) -> list[ActionAverageRecord]: ...
    async def voucher_money(self, since: date, until: date) -> VoucherMoneyRecord: ...
    async def get_voucher(self, voucher_id: uuid.UUID) -> VoucherRecord | None: ...
    async def mark_voucher_sent(self, voucher_id: uuid.UUID, email: str, at: datetime) -> None: ...
    async def count_voucher_mails(self, email: str, since: datetime) -> int:
        """Vouchers sent to this address since `since` (the per-address mail quota)."""
        ...

    async def redeem_voucher(self, code_hash: str, user_id: uuid.UUID, now: datetime) -> int | None:
        """Redeem atomically: mark the voucher and credit the ledger, or return None."""
        ...

    async def credit_totals(self, user_id: uuid.UUID) -> CreditTotals: ...
    async def all_credit_totals(self) -> dict[uuid.UUID, CreditTotals]: ...
    async def list_vouchers(self, limit: int) -> list[VoucherRecord]:
        """Newest first, creator and redeemer resolved to e-mail addresses."""
        ...

    async def stats(self, since: datetime, now: datetime) -> StatsRecord: ...
    async def daily_stats(self, since: datetime) -> list[DailyStatsRecord]:
        """Per UTC day from `since`, days with activity only, oldest first."""
        ...

    async def usage_by_model(self) -> list[ModelUsageRecord]:
        """Core's usage rows grouped by model and kind, highest cost first."""
        ...

    async def top_users_by_usage(self, limit: int) -> list[UserUsageRecord]: ...
    async def delete_voucher(
        self, voucher_id: uuid.UUID
    ) -> Literal["deleted", "redeemed", "missing"]:
        """Remove an open voucher. A redeemed one is history (it backs a ledger row) and stays."""
        ...

    # visits -----------------------------------------------------------------
    async def add_visit(self, visit: VisitRecord) -> None: ...
    async def purge_visits(self, before: datetime) -> int: ...
    async def visit_summary(self, since: datetime) -> list[VisitSummary]: ...

    # access control, tables owned by core: read, and lift bans -----------------
    async def active_blocks(self, now: datetime) -> list[BlockRecord]: ...
    async def bans(self, *, include_lifted: bool) -> list[BanRecord]: ...
    async def lift_ban(self, ip: str, now: datetime) -> bool:
        """Set lifted_at on the active ban for this ip; False if there is none."""
        ...

    async def access_log(self, limit: int) -> list[AccessRecord]: ...
    async def purge_access_tables(self, params: Mapping[str, datetime]) -> tuple[int, int, int]:
        """Core's retention rule with ``params`` from ``lasteverlm_core.purge_params``: drop
        access_log rows, stale blocks and lifted bans older than ``cutoff``, and bans older
        than ``ban_cutoff`` whether lifted or not. Returns the three counts."""
        ...

    # lifecycle --------------------------------------------------------------
    async def ping(self) -> None: ...
    async def close(self) -> None: ...
