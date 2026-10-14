"""API schemas, prefix ``/api/account``, as fixed in the family's ``docs/architecture.md`` v1."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

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


AllowKind = Literal["domain", "address", "viewer", "viewer_address"]


class Allowlist(BaseModel):
    """Who may sign in besides ADMIN_EMAILS: listed domains and listed single addresses.
    ``viewer_domains``: a first sign-in from one of these domains gets the viewer role."""

    allowed_domains: list[str]
    allowed_addresses: list[str]
    viewer_domains: list[str]
    viewer_addresses: list[str]  # a first sign-in of one of these addresses gets the viewer role


class DomainAdd(BaseModel):
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]


class AddressAdd(BaseModel):
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]


class AdminLogin(BaseModel):
    user_id: uuid.UUID
    email: str
    at: datetime


class RateLimitRulesView(BaseModel):
    """The rate-limit rule in force. The first five are editable at run time (stored under
    the ``ratelimit`` settings key, read by core's middleware in every service within 30 s);
    ``retention_days`` comes from the environment only."""

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
    ban_max_days: int | None = None  # 1..365; omitted keeps the environment default


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


VoucherMessage = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class CreateVouchersBody(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)  # null uses the configured default
    count: int = Field(default=1, ge=1, le=100)
    send_to: Email | None = None  # mail every created voucher to this address right away
    message: VoucherMessage | None = None
    allow: bool = True  # with send_to: add the address to the allowlist first
    paid: bool = False  # sold for money (revenue) rather than given away


class VoucherPaid(BaseModel):
    paid: bool


class InfraCost(BaseModel):
    id: uuid.UUID
    date: date
    source: Literal["vultr", "manual"]
    item: str
    amount_cents: int  # in `currency`, as billed
    currency: Literal["USD", "EUR"]
    amount_eur_cents: int | None  # converted at the pricing rules' usd_per_eur; null without it


class InfraCostAdd(BaseModel):
    date: date
    item: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    amount_cents: int = Field(ge=0, le=10_000_000)
    currency: Literal["USD", "EUR"] = "EUR"


class InfraCosts(BaseModel):
    """Infrastructure costs of a period, and the Vultr sync as two separate facts:
    ``configured`` (a key is set) and ``last_success_at`` (syncing has worked, when).
    ``last_error`` is Vultr's own message from the last failed attempt, null after a success."""

    configured: bool
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    usd_per_eur: float | None  # the pricing rules' rate, the one core books with
    entries: list[InfraCost]
    totals_by_currency: dict[str, int]
    total_eur_cents: int | None  # null when USD entries exist and no rate is set


class TypicalPrice(BaseModel):
    p25: float
    median: float
    p75: float


class PublicPriceRow(BaseModel):
    action: str  # core's action, "judge:<level>", or "source:pdf:vision" (the vision way)
    level: str | None  # the judge level (low|medium|high) for judge rows, else null
    unit: str  # a stable key ("question", "output", "page", "audio_minute", …); web translates
    price_per_unit_cents: float | None  # estimated: the midpoint of min and max below
    price_min_cents: float | None
    price_max_cents: float | None
    estimated: bool  # the price comes from rag's or ingest's estimate (null price: false)
    per_source_cents: float | None  # sources: added once per source on top of the units
    typical_cents: TypicalPrice | None  # per whole action, from history; null below 5
    count: int  # actions in the window
    model: str | None


class PublicPrices(BaseModel):
    """End prices only: what an action costs a user today, from the last window's measured
    costs through the current pricing rules. No margins, fees, costs or user data."""

    usd_per_eur: float | None
    rate_date: date | None
    rate_source: Literal["ECB", "manual", "seed"]
    window_days: int
    actions: list[PublicPriceRow]


class PricingPreviewRow(BaseModel):
    action: str
    actions: int  # how many of this action ran in the last 30 days
    avg_cost_cents: float | None  # mean real cost of one action; null without data
    margin_pct: float
    fixed_cents: float
    charge_cents: float | None  # what one average action charges under these rules


class ExchangeRateStatus(BaseModel):
    """Where ``usd_per_eur`` comes from. ``automatic``: the ECB reference rate, checked every
    hour; ``manual``: set by an admin, the hourly update paused. ``stale`` is true when the
    last successful ECB check is older than three days (automatic mode only)."""

    usd_per_eur: float | None
    mode: Literal["automatic", "manual"]
    source: Literal["ECB", "manual", "seed"]
    rate_date: date | None  # the ECB day the rate is for
    last_checked: datetime | None  # last attempt
    last_success: datetime | None
    last_error: str | None
    stale: bool


class RateMode(BaseModel):
    mode: Literal["automatic", "manual"]


class PricingView(BaseModel):
    """Core's pricing rules (settings key ``pricing``), the actions they can name, an
    example charge per action from the last 30 days' average cost, and the rate's origin."""

    rules: dict[
        str, Any
    ]  # {"default_margin_pct", "actions": {action: {margin_pct?, fixed_cents?}}}
    actions: list[str]
    preview: list[PricingPreviewRow]
    rate: ExchangeRateStatus


class FinanceGroupRow(BaseModel):
    key: str
    calls: int
    actions: int
    cost_cents: float  # real cost, euro cents
    charge_cents: float  # charged to users, euro cents
    cost_usd_cents: float  # real cost as measured, US cents


class FinanceCosts(BaseModel):
    from_: date = Field(serialization_alias="from")
    to: date
    group: str
    rows: list[FinanceGroupRow]
    total_cost_cents: float
    total_charge_cents: float
    total_cost_usd_cents: float


class VoucherMoney(BaseModel):
    issued_paid_cents: int
    issued_free_cents: int
    redeemed_paid_cents: int
    redeemed_free_cents: int


class FinanceRevenue(BaseModel):
    """Money in: paid vouchers. Credit used: what users were charged. The demo user's
    charges are seed credit, not money, and stand apart."""

    from_: date = Field(serialization_alias="from")
    to: date
    charged_cents: float
    demo_charged_cents: float
    vouchers: VoucherMoney
    outstanding_credit_cents: int  # what users can still spend, now; the demo user excluded


class ProfitRow(BaseModel):
    period: date
    charged_cents: float
    model_cost_cents: float
    infra_cost_cents: float | None  # EUR; null when USD lines exist and no rate is set
    profit_cents: float | None
    demo_charged_cents: float
    demo_cost_cents: float


class FinanceProfit(BaseModel):
    """Charged − model cost − infrastructure, per day or month, in euro cents: usage as core
    books it, infrastructure converted at the pricing rules' usd_per_eur. Daily rows get
    an even share of their month's infrastructure. Demo usage is shown, not counted."""

    from_: date = Field(serialization_alias="from")
    to: date
    group: Literal["day", "month"]
    usd_per_eur: float | None
    rows: list[ProfitRow]
    total: ProfitRow | None


class SendVoucherBody(BaseModel):
    email: Email
    message: VoucherMessage | None = None
    allow: bool = True


class VoucherCode(BaseModel):
    code: str


class CreateVouchersResponse(BaseModel):
    codes: list[str]  # shown exactly once; only their hashes are stored


class AdminVoucher(BaseModel):
    """A voucher in the admin list. The code appears masked; the full code is one request
    away (``GET /admin/vouchers/{id}/code``) for vouchers created since codes are stored
    encrypted — ``recoverable`` says so; older ones have only the hash."""

    id: uuid.UUID
    amount_cents: int
    created_by: str
    created_at: datetime
    redeemed_by: str | None
    redeemed_at: datetime | None
    status: Literal["open", "redeemed"]
    code_masked: str | None  # "ABCD-****-****-****", null when not recoverable
    recoverable: bool
    sent_to: str | None
    sent_at: datetime | None
    paid: bool


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
    dependencies: dict[str, str] | None  # from the service's healthz, passed through unchanged


class SystemPod(BaseModel):
    name: str
    service: str  # the app.kubernetes.io/name label
    image_tag: str | None
    ready: bool
    restarts: int
    node: str | None
    started_at: datetime | None
    phase: str | None  # Pending | Running | Succeeded | Failed | Unknown
    # CrashLoopBackOff, ImagePullBackOff, OOMKilled, Error, …; a termination within the last
    # ten minutes still counts; null when the containers run quietly
    reason: str | None
    template_hash: str | None  # which ReplicaSet the pod belongs to


class SystemDeployment(BaseModel):
    name: str
    replicas: int
    ready: int
    updated: int
    progressing: (
        bool | None
    )  # a rollout is under way; false once NewReplicaSetAvailable, null without the condition
    available: bool | None  # the Available condition
    replica_sets: int  # ReplicaSets that have pods; 2 during a rollout


class SystemInfo(BaseModel):
    """The admin System page. Outside a cluster `cluster` is false and the Kubernetes lists
    are empty; the services are probed either way, an unreachable one is `healthy: false`."""

    version: str
    commit: str
    cluster: bool
    services: list[SystemService]
    pods: list[SystemPod]
    deployments: list[SystemDeployment]
