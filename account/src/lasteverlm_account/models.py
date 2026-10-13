"""API schemas, prefix ``/api/account``, as fixed in the family's ``docs/architecture.md`` v1."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from lasteverlm_core import AdminUser, User
from pydantic import BaseModel, Field, StringConstraints

__all__ = ["AdminUser", "User"]

# Shape only: one @, no whitespace, something on both sides. Deliverability is the
# mail server's call, and reserved names such as demo@localhost must stay valid here.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$"
    ),
]


class RequestLinkBody(BaseModel):
    email: Email


class LoginResponse(BaseModel):
    jwt: str
    user: User


class RedeemBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class VisitBody(BaseModel):
    path: str = Field(min_length=1, max_length=512)


# --- admin -------------------------------------------------------------------


class AdminUserView(AdminUser):
    """Core's AdminUser plus what the Users page shows per user: credits granted (the
    sum of the user's ledger rows, vouchers and the demo seed alike)."""

    granted_cents: int


class Smtp(BaseModel):
    """The mail configuration in effect, read-only; the password is never returned.
    An empty ``host`` means SMTP is not configured."""

    host: str
    port: int
    username: str
    from_address: str
    starttls: bool


AllowKind = Literal["domain", "address"]


class Allowlist(BaseModel):
    """Who may sign in besides ADMIN_EMAILS: listed domains and listed single addresses."""

    allowed_domains: list[str]
    allowed_addresses: list[str]


class DomainAdd(BaseModel):
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]


class AddressAdd(BaseModel):
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]


class AdminLogin(BaseModel):
    user_id: uuid.UUID
    email: str
    at: datetime


class RateLimitRulesView(BaseModel):
    """The rate-limit rule in force. The first four are editable at run time (stored under
    the ``ratelimit`` settings key, read by core's middleware in every service within 30 s);
    ``ban_max_days`` and ``retention_days`` come from the environment only."""

    per_minute: int
    block_minutes: int
    ban_after_strikes: int
    strike_window_hours: int
    ban_max_days: int
    retention_days: int


class RateLimitRulesUpdate(BaseModel):
    """Bounds are core's ``RATE_LIMIT_RULE_BOUNDS``; a value outside them is a 422."""

    per_minute: int
    block_minutes: int
    ban_after_strikes: int
    strike_window_hours: int


class AdminLoginAttempt(BaseModel):
    """A request for a sign-in link. Holds the plain client IP (context/privacy.md)."""

    at: datetime
    email: str
    ip: str
    outcome: Literal["allowed", "refused"]


class AdminVisit(BaseModel):
    day: date
    path: str
    visits: int
    unique: int


class AdminBlock(BaseModel):
    ip: str
    blocked_until: datetime
    strikes: int
    updated_at: datetime


class AdminBan(BaseModel):
    ip: str
    reason: str
    created_at: datetime
    lifted_at: datetime | None


class AdminAccess(BaseModel):
    at: datetime
    ip: str
    method: str
    path: str
    status: int
    user_id: uuid.UUID | None
    service: str


class CreateVouchersBody(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)  # null uses the configured default
    count: int = Field(default=1, ge=1, le=100)


class CreateVouchersResponse(BaseModel):
    codes: list[str]  # shown exactly once; only their hashes are stored


class AdminVoucher(BaseModel):
    """A voucher in the admin list. The code is not here: only its hash is stored, and the
    plain code was shown once, at creation."""

    id: uuid.UUID
    amount_cents: int
    created_by: str
    created_at: datetime
    redeemed_by: str | None
    redeemed_at: datetime | None
    status: Literal["open", "redeemed"]


class VoucherCounts(BaseModel):
    issued: int
    redeemed: int
    open: int


class UsageCost(BaseModel):
    total: int
    last_24h: int


class DailyStat(BaseModel):
    day: date
    logins: int
    visits: int
    usage_cost_cents: int
    credits_granted_cents: int


class DailyStats(BaseModel):
    """Every UTC day of the window, zeros included, oldest first, today last."""

    days: list[DailyStat]


class ModelUsage(BaseModel):
    model: str
    kind: str
    calls: int
    cost_cents: int


class UserUsage(BaseModel):
    email: str
    usage_cents: int
    balance_cents: int


class UsageStats(BaseModel):
    """Core's usage rows by model and kind (cost descending) and the ten heaviest users."""

    by_model: list[ModelUsage]
    top_users: list[UserUsage]


class AdminStats(BaseModel):
    """The admin overview. Usage comes from core's `usage` rows, written by ingest and rag."""

    users: int
    logins_24h: int
    vouchers: VoucherCounts
    credits_granted_cents: int
    usage_cost_cents: UsageCost
    blocks_active: int
    bans_active: int


class Health(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    error: str
