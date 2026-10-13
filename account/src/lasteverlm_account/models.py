"""API schemas, prefix ``/api/account``, as fixed in the family's ``docs/architecture.md`` v1."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from lasteverlm_core import AdminUser
from lasteverlm_core import User as CoreUser
from pydantic import BaseModel, Field, StringConstraints

__all__ = ["AdminUser", "CoreUser"]

# Shape only: one @, no whitespace, something on both sides. Deliverability is the
# mail server's call, and reserved names such as demo@localhost must stay valid here.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$"
    ),
]


LanguageCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=35, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    ),
]
VoiceId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9_-]{1,64}$")]


class Preferences(BaseModel):
    """Per-user preferences. ``null`` means not set: the web's default language, the
    source's language for output, the platform's default voice, 14 days in the trash,
    automatic PDF capture, the system theme."""

    ui_language: Literal["de", "en"] | None = None
    output_language: LanguageCode | None = None
    audio_voice: VoiceId | None = None
    trash_days: Annotated[int, Field(ge=1, le=365)] | None = None  # null: 14, applied by ingest
    pdf_capture: Literal["auto", "text", "vision"] | None = None  # null: auto
    theme: Literal["system", "light", "dark"] | None = None  # null: system; the web applies it


class PreferencesUpdate(BaseModel):
    """Partial update: a key present (with a value or null) is applied, an absent key kept."""

    ui_language: Literal["de", "en"] | None = None
    output_language: LanguageCode | None = None
    audio_voice: VoiceId | None = None
    trash_days: Annotated[int, Field(ge=1, le=365)] | None = None
    pdf_capture: Literal["auto", "text", "vision"] | None = None
    theme: Literal["system", "light", "dark"] | None = None


Role = Literal["user", "viewer", "admin"]


class User(CoreUser):
    """Core's User plus the role and the preferences, so the web has them at login.
    ``is_admin`` stays and equals ``role == "admin"``; a viewer reads the admin panel."""

    role: Role
    preferences: Preferences


class RoleUpdate(BaseModel):
    role: Role


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
    role: Role


class Smtp(BaseModel):
    """The mail configuration in effect, read-only; the password is never returned.
    An empty ``host`` means SMTP is not configured."""

    host: str
    port: int
    username: str
    from_address: str
    starttls: bool


AllowKind = Literal["domain", "address", "viewer"]


class Allowlist(BaseModel):
    """Who may sign in besides ADMIN_EMAILS: listed domains and listed single addresses.
    ``viewer_domains``: a first sign-in from one of these domains gets the viewer role."""

    allowed_domains: list[str]
    allowed_addresses: list[str]
    viewer_domains: list[str]


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


class SystemService(BaseModel):
    name: str
    version: str | None
    commit: str | None
    healthy: bool


class SystemPod(BaseModel):
    name: str
    service: str  # the app.kubernetes.io/name label
    image_tag: str | None
    ready: bool
    restarts: int
    node: str | None
    started_at: datetime | None


class SystemDeployment(BaseModel):
    name: str
    replicas: int
    ready: int
    updated: int


class SystemInfo(BaseModel):
    """The admin System page. Outside a cluster `cluster` is false and the Kubernetes lists
    are empty; the services are probed either way, an unreachable one is `healthy: false`."""

    version: str
    commit: str
    cluster: bool
    services: list[SystemService]
    pods: list[SystemPod]
    deployments: list[SystemDeployment]
