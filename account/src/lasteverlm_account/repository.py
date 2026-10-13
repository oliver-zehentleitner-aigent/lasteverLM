"""Storage interface. Two implementations: PostgreSQL for deployment, in-memory for tests.

All multi-step mutations that must be atomic (consuming a magic link, redeeming a
voucher, creating the first user) are single repository calls, so each
implementation can make them atomic in its own way and the service layer stays
free of transaction handling.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    email: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


@dataclass(frozen=True)
class LoginRecord:
    user_id: uuid.UUID
    email: str
    at: datetime


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
class CreditTotals:
    credited_cents: int
    usage_cents: int

    @property
    def balance_cents(self) -> int:
        return self.credited_cents - self.usage_cents


class Repository(Protocol):
    # settings ---------------------------------------------------------------
    async def get_setting(self, key: str) -> dict[str, Any] | None: ...
    async def set_setting(self, key: str, value: dict[str, Any]) -> None: ...
    async def set_setting_if_missing(self, key: str, value: dict[str, Any]) -> bool: ...

    # users ------------------------------------------------------------------
    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None: ...
    async def get_user_by_email(self, email: str) -> UserRecord | None: ...
    async def create_user(self, email: str, *, admin: bool, now: datetime) -> UserRecord:
        """Create a user. The very first user ever created is an admin regardless of ``admin``."""
        ...

    async def ensure_user(
        self, user_id: uuid.UUID, email: str, *, admin: bool, now: datetime
    ) -> UserRecord: ...
    async def record_login(self, user_id: uuid.UUID, at: datetime) -> None: ...
    async def list_users(self) -> list[UserRecord]: ...
    async def list_logins(self, limit: int) -> list[LoginRecord]: ...

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
        self, code_hash: str, amount_cents: int, created_by: uuid.UUID, now: datetime
    ) -> uuid.UUID: ...
    async def redeem_voucher(self, code_hash: str, user_id: uuid.UUID, now: datetime) -> int | None:
        """Redeem atomically: mark the voucher and credit the ledger, or return None."""
        ...

    async def credit_totals(self, user_id: uuid.UUID) -> CreditTotals: ...
    async def all_credit_totals(self) -> dict[uuid.UUID, CreditTotals]: ...

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
