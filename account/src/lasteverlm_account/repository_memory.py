"""In-memory repository for tests and for running the service without a database.

Atomicity is a single asyncio lock around every mutating call, which is enough to
make the service-level tests meaningful; the PostgreSQL implementation is the one
that matters for the deployed system and is covered by ``tests/test_postgres.py``
when a database is available.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from lasteverlm_core import DEMO_USER_ID

from .repository import (
    AccessRecord,
    BanRecord,
    BlockRecord,
    CreditTotals,
    LoginRecord,
    UserRecord,
    VisitRecord,
    VisitSummary,
)


@dataclass
class _MagicLink:
    email: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class _Voucher:
    id: uuid.UUID
    amount_cents: int
    created_by: uuid.UUID
    created_at: datetime
    redeemed_by: uuid.UUID | None = None
    redeemed_at: datetime | None = None


@dataclass
class _Ledger:
    user_id: uuid.UUID
    amount_cents: int
    reason: str
    voucher_id: uuid.UUID | None
    created_at: datetime


@dataclass
class MemoryRepository:
    settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    users: dict[uuid.UUID, UserRecord] = field(default_factory=dict)
    logins: list[LoginRecord] = field(default_factory=list)
    magic_links: dict[str, _MagicLink] = field(default_factory=dict)
    vouchers: dict[str, _Voucher] = field(default_factory=dict)
    ledger: list[_Ledger] = field(default_factory=list)
    usage_cost_cents: dict[uuid.UUID, int] = field(default_factory=lambda: defaultdict(int))
    visits: list[VisitRecord] = field(default_factory=list)
    blocks: list[BlockRecord] = field(default_factory=list)
    ip_bans: list[BanRecord] = field(default_factory=list)
    access: list[AccessRecord] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # settings ---------------------------------------------------------------
    async def get_setting(self, key: str) -> dict[str, Any] | None:
        value = self.settings.get(key)
        return dict(value) if value is not None else None

    async def set_setting(self, key: str, value: dict[str, Any]) -> None:
        async with self._lock:
            self.settings[key] = dict(value)

    async def set_setting_if_missing(self, key: str, value: dict[str, Any]) -> bool:
        async with self._lock:
            if key in self.settings:
                return False
            self.settings[key] = dict(value)
            return True

    # users ------------------------------------------------------------------
    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        return self.users.get(user_id)

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def create_user(self, email: str, *, admin: bool, now: datetime) -> UserRecord:
        async with self._lock:
            existing = await self.get_user_by_email(email)
            if existing is not None:
                return existing
            user = UserRecord(
                id=uuid.uuid4(),
                email=email,
                is_admin=admin or not any(u != DEMO_USER_ID for u in self.users),
                created_at=now,
                last_login_at=None,
            )
            self.users[user.id] = user
            return user

    async def ensure_user(
        self, user_id: uuid.UUID, email: str, *, admin: bool, now: datetime
    ) -> UserRecord:
        async with self._lock:
            if user_id not in self.users:
                self.users[user_id] = UserRecord(user_id, email, admin, now, None)
            return self.users[user_id]

    async def record_login(self, user_id: uuid.UUID, at: datetime) -> None:
        async with self._lock:
            user = self.users[user_id]
            self.users[user_id] = replace(user, last_login_at=at)
            self.logins.append(LoginRecord(user_id=user_id, email=user.email, at=at))

    async def list_users(self) -> list[UserRecord]:
        return sorted(self.users.values(), key=lambda u: u.created_at)

    async def list_logins(self, limit: int) -> list[LoginRecord]:
        return sorted(self.logins, key=lambda r: r.at, reverse=True)[:limit]

    # magic links ------------------------------------------------------------
    async def create_magic_link(self, email: str, token_hash: str, expires_at: datetime) -> None:
        async with self._lock:
            self.magic_links[token_hash] = _MagicLink(email=email, expires_at=expires_at)

    async def consume_magic_link(self, token_hash: str, now: datetime) -> str | None:
        async with self._lock:
            link = self.magic_links.get(token_hash)
            if link is None or link.used_at is not None or link.expires_at <= now:
                return None
            link.used_at = now
            return link.email

    async def purge_magic_links(self, now: datetime) -> int:
        async with self._lock:
            stale = [h for h, link in self.magic_links.items() if link.expires_at <= now]
            for h in stale:
                del self.magic_links[h]
            return len(stale)

    # credits ----------------------------------------------------------------
    async def create_voucher(
        self, code_hash: str, amount_cents: int, created_by: uuid.UUID, now: datetime
    ) -> uuid.UUID:
        async with self._lock:
            voucher = _Voucher(uuid.uuid4(), amount_cents, created_by, now)
            self.vouchers[code_hash] = voucher
            return voucher.id

    async def redeem_voucher(self, code_hash: str, user_id: uuid.UUID, now: datetime) -> int | None:
        async with self._lock:
            voucher = self.vouchers.get(code_hash)
            if voucher is None or voucher.redeemed_by is not None:
                return None
            voucher.redeemed_by = user_id
            voucher.redeemed_at = now
            self.ledger.append(_Ledger(user_id, voucher.amount_cents, "voucher", voucher.id, now))
            return voucher.amount_cents

    async def credit_totals(self, user_id: uuid.UUID) -> CreditTotals:
        credited = sum(e.amount_cents for e in self.ledger if e.user_id == user_id)
        return CreditTotals(credited, self.usage_cost_cents.get(user_id, 0))

    async def all_credit_totals(self) -> dict[uuid.UUID, CreditTotals]:
        return {u: await self.credit_totals(u) for u in self.users}

    # visits -----------------------------------------------------------------
    async def add_visit(self, visit: VisitRecord) -> None:
        async with self._lock:
            self.visits.append(visit)

    async def purge_visits(self, before: datetime) -> int:
        async with self._lock:
            kept = [v for v in self.visits if v.at >= before]
            removed = len(self.visits) - len(kept)
            self.visits = kept
            return removed

    async def visit_summary(self, since: datetime) -> list[VisitSummary]:
        groups: dict[tuple[Any, str], list[VisitRecord]] = defaultdict(list)
        for v in self.visits:
            if v.at >= since:
                groups[(v.at.date(), v.path)].append(v)
        return [
            VisitSummary(day=d, path=path, visits=len(vs), unique=len({v.ip_hash for v in vs}))
            for (d, path), vs in sorted(groups.items(), key=lambda kv: kv[0], reverse=True)
        ]

    # access control ---------------------------------------------------------
    async def active_blocks(self, now: datetime) -> list[BlockRecord]:
        return sorted(
            (b for b in self.blocks if b.blocked_until > now), key=lambda b: b.blocked_until
        )

    async def bans(self, *, include_lifted: bool) -> list[BanRecord]:
        rows = [b for b in self.ip_bans if include_lifted or b.lifted_at is None]
        return sorted(rows, key=lambda b: b.created_at, reverse=True)

    async def lift_ban(self, ip: str, now: datetime) -> bool:
        async with self._lock:
            lifted = False
            for i, ban in enumerate(self.ip_bans):
                if ban.ip == ip and ban.lifted_at is None:
                    self.ip_bans[i] = replace(ban, lifted_at=now)
                    lifted = True
            return lifted

    async def access_log(self, limit: int) -> list[AccessRecord]:
        return sorted(self.access, key=lambda a: a.at, reverse=True)[:limit]

    # lifecycle --------------------------------------------------------------
    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None
