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
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Any, Literal

from lasteverlm_core import DEMO_USER_ID

from .repository import (
    AccessRecord,
    BanRecord,
    BlockRecord,
    CreditTotals,
    DailyStatsRecord,
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


@dataclass
class _MagicLink:
    email: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class _Voucher:
    id: uuid.UUID
    amount_cents: int
    created_by: uuid.UUID | None
    created_at: datetime
    redeemed_by: uuid.UUID | None = None
    redeemed_at: datetime | None = None
    code_enc: str | None = None
    sent_to: str | None = None
    sent_at: datetime | None = None


@dataclass
class _Usage:
    """A row of core's `usage` table as ingest/rag write it; tests fill this directly."""

    user_id: uuid.UUID
    cost_cents: int
    created_at: datetime
    model: str = "model"
    kind: str = "llm"


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
    login_attempts: list[LoginAttemptRecord] = field(default_factory=list)
    magic_links: dict[str, _MagicLink] = field(default_factory=dict)
    vouchers: dict[str, _Voucher] = field(default_factory=dict)
    ledger: list[_Ledger] = field(default_factory=list)
    usage: list[_Usage] = field(default_factory=list)
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

    async def delete_setting(self, key: str) -> bool:
        async with self._lock:
            return self.settings.pop(key, None) is not None

    # users ------------------------------------------------------------------
    async def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        return self.users.get(user_id)

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def create_user(self, email: str, *, role: str, now: datetime) -> UserRecord:
        async with self._lock:
            existing = await self.get_user_by_email(email)
            if existing is not None:
                return existing
            if not any(u != DEMO_USER_ID for u in self.users):
                role = "admin"  # the first real user
            user = UserRecord(
                id=uuid.uuid4(),
                email=email,
                is_admin=role == "admin",
                created_at=now,
                last_login_at=None,
                role=role,
            )
            self.users[user.id] = user
            return user

    async def set_role(self, user_id: uuid.UUID, role: str) -> bool:
        async with self._lock:
            user = self.users.get(user_id)
            if user is None:
                return False
            self.users[user_id] = replace(user, role=role, is_admin=role == "admin")
            return True

    async def count_admins(self) -> int:
        return sum(1 for u in self.users.values() if u.role == "admin")

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        async with self._lock:
            if user_id not in self.users:
                return False
            del self.users[user_id]
            self.logins = [r for r in self.logins if r.user_id != user_id]
            self.ledger = [e for e in self.ledger if e.user_id != user_id]
            self.usage = [u for u in self.usage if u.user_id != user_id]
            for v in self.vouchers.values():
                if v.created_by == user_id:
                    v.created_by = None
                if v.redeemed_by == user_id:
                    v.redeemed_by = None
            self.visits = [
                replace(v, user_id=None) if v.user_id == user_id else v for v in self.visits
            ]
            return True

    async def set_preferences(self, user_id: uuid.UUID, preferences: dict[str, Any]) -> None:
        async with self._lock:
            self.users[user_id] = replace(self.users[user_id], preferences=dict(preferences))

    async def record_login(self, user_id: uuid.UUID, at: datetime) -> None:
        async with self._lock:
            user = self.users[user_id]
            self.users[user_id] = replace(user, last_login_at=at)
            self.logins.append(LoginRecord(user_id=user_id, email=user.email, at=at))

    async def list_users(self) -> list[UserRecord]:
        return sorted(self.users.values(), key=lambda u: u.created_at)

    async def list_logins(self, limit: int) -> list[LoginRecord]:
        return sorted(self.logins, key=lambda r: r.at, reverse=True)[:limit]

    async def add_login_attempt(self, attempt: LoginAttemptRecord) -> None:
        async with self._lock:
            self.login_attempts.append(attempt)

    async def list_login_attempts(self, limit: int) -> list[LoginAttemptRecord]:
        return sorted(self.login_attempts, key=lambda r: r.at, reverse=True)[:limit]

    async def count_allowed_attempts(self, email: str, since: datetime) -> int:
        return sum(
            1
            for a in self.login_attempts
            if a.email == email and a.outcome == "allowed" and a.at >= since
        )

    async def purge_login_attempts(self, before: datetime) -> int:
        async with self._lock:
            kept = [a for a in self.login_attempts if a.at >= before]
            removed = len(self.login_attempts) - len(kept)
            self.login_attempts = kept
            return removed

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
        self,
        code_hash: str,
        amount_cents: int,
        created_by: uuid.UUID,
        now: datetime,
        code_enc: str | None = None,
    ) -> uuid.UUID:
        async with self._lock:
            voucher = _Voucher(uuid.uuid4(), amount_cents, created_by, now, code_enc=code_enc)
            self.vouchers[code_hash] = voucher
            return voucher.id

    def _record(self, v: _Voucher) -> VoucherRecord:
        return VoucherRecord(
            v.id,
            v.amount_cents,
            self._email(v.created_by) or "",
            v.created_at,
            self._email(v.redeemed_by),
            v.redeemed_at,
            v.code_enc,
            v.sent_to,
            v.sent_at,
        )

    async def get_voucher(self, voucher_id: uuid.UUID) -> VoucherRecord | None:
        for v in self.vouchers.values():
            if v.id == voucher_id:
                return self._record(v)
        return None

    async def mark_voucher_sent(self, voucher_id: uuid.UUID, email: str, at: datetime) -> None:
        async with self._lock:
            for v in self.vouchers.values():
                if v.id == voucher_id:
                    v.sent_to, v.sent_at = email, at

    async def count_voucher_mails(self, email: str, since: datetime) -> int:
        return sum(
            1
            for v in self.vouchers.values()
            if v.sent_to == email and v.sent_at is not None and v.sent_at >= since
        )

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
        spent = sum(u.cost_cents for u in self.usage if u.user_id == user_id)
        return CreditTotals(credited, spent)

    async def all_credit_totals(self) -> dict[uuid.UUID, CreditTotals]:
        return {u: await self.credit_totals(u) for u in self.users}

    async def delete_voucher(
        self, voucher_id: uuid.UUID
    ) -> Literal["deleted", "redeemed", "missing"]:
        async with self._lock:
            for code_hash, voucher in self.vouchers.items():
                if voucher.id == voucher_id:
                    if voucher.redeemed_at is not None:
                        return "redeemed"
                    del self.vouchers[code_hash]
                    return "deleted"
            return "missing"

    def _email(self, user_id: uuid.UUID | None) -> str | None:
        return self.users[user_id].email if user_id in self.users else None

    async def list_vouchers(self, limit: int) -> list[VoucherRecord]:
        rows = sorted(self.vouchers.values(), key=lambda v: v.created_at, reverse=True)[:limit]
        return [self._record(v) for v in rows]

    async def stats(self, since: datetime, now: datetime) -> StatsRecord:
        return StatsRecord(
            users=len(self.users),
            logins_since=sum(1 for r in self.logins if r.at >= since),
            vouchers_issued=len(self.vouchers),
            vouchers_redeemed=sum(1 for v in self.vouchers.values() if v.redeemed_at is not None),
            credits_granted_cents=sum(e.amount_cents for e in self.ledger),
            usage_cost_cents_total=sum(u.cost_cents for u in self.usage),
            usage_cost_cents_since=sum(u.cost_cents for u in self.usage if u.created_at >= since),
            blocks_active=sum(1 for b in self.blocks if b.blocked_until > now),
            bans_active=sum(1 for b in self.ip_bans if b.lifted_at is None),
        )

    async def daily_stats(self, since: datetime) -> list[DailyStatsRecord]:
        days: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
        for r in self.logins:
            if r.at >= since:
                days[r.at.astimezone(UTC).date()][0] += 1
        for v in self.visits:
            if v.at >= since:
                days[v.at.astimezone(UTC).date()][1] += 1
        for u in self.usage:
            if u.created_at >= since:
                days[u.created_at.astimezone(UTC).date()][2] += u.cost_cents
        for e in self.ledger:
            if e.created_at >= since:
                days[e.created_at.astimezone(UTC).date()][3] += e.amount_cents
        return [DailyStatsRecord(d, *days[d]) for d in sorted(days)]

    async def usage_by_model(self) -> list[ModelUsageRecord]:
        groups: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for u in self.usage:
            groups[(u.model, u.kind)][0] += 1
            groups[(u.model, u.kind)][1] += u.cost_cents
        rows = [ModelUsageRecord(m, k, calls, cost) for (m, k), (calls, cost) in groups.items()]
        return sorted(rows, key=lambda r: (-r.cost_cents, r.model, r.kind))

    async def top_users_by_usage(self, limit: int) -> list[UserUsageRecord]:
        totals = await self.all_credit_totals()
        rows = [
            UserUsageRecord(self.users[u].email, t.usage_cents, t.balance_cents)
            for u, t in totals.items()
            if t.usage_cents > 0
        ]
        return sorted(rows, key=lambda r: (-r.usage_cents, r.email))[:limit]

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

    async def purge_access_tables(self, params: Mapping[str, datetime]) -> tuple[int, int, int]:
        cutoff, ban_cutoff = params["cutoff"], params["ban_cutoff"]
        async with self._lock:
            before = len(self.access), len(self.blocks), len(self.ip_bans)
            self.access = [a for a in self.access if a.at >= cutoff]
            self.blocks = [b for b in self.blocks if b.updated_at >= cutoff]
            self.ip_bans = [
                b
                for b in self.ip_bans
                if (b.lifted_at is None or b.lifted_at >= cutoff) and b.created_at >= ban_cutoff
            ]
            after = len(self.access), len(self.blocks), len(self.ip_bans)
            return before[0] - after[0], before[1] - after[1], before[2] - after[2]

    # lifecycle --------------------------------------------------------------
    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None
