"""Business rules of the account service, independent of HTTP and of the storage backend."""

from __future__ import annotations

import asyncio
import calendar
import contextlib
import hashlib
import logging
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from lasteverlm_core import (
    DEFAULT_PRICING_RULES,
    DEMO_USER_ID,
    PRICING_SETTINGS_KEY,
    RATE_LIMIT_SETTINGS_KEY,
    USAGE_ACTIONS,
    AuthSettings,
    DependencyProbe,
    PricingRules,
    RateLimitRules,
    RateLimitSettings,
    issue_jwt,
    purge_params,
)

from .config import Settings
from .crypto import VoucherCipher
from .mail import Mailer, MailError, magic_link_mail, voucher_mail
from .models import (
    AdminAccess,
    AdminBan,
    AdminBlock,
    AdminLogin,
    AdminLoginAttempt,
    AdminStats,
    AdminUserView,
    AdminVisit,
    AdminVoucher,
    AllowKind,
    Allowlist,
    DailyStat,
    DailyStats,
    FinanceCosts,
    FinanceGroupRow,
    FinanceProfit,
    FinanceRevenue,
    InfraCost,
    InfraCostAdd,
    InfraCosts,
    ModelUsage,
    Preferences,
    PreferencesUpdate,
    PricingPreviewRow,
    PricingView,
    ProfitRow,
    RateLimitRulesUpdate,
    RateLimitRulesView,
    Role,
    Smtp,
    SystemDeployment,
    SystemInfo,
    SystemPod,
    SystemService,
    UsageCost,
    UsageStats,
    User,
    UserUsage,
    VoucherCode,
    VoucherCounts,
    VoucherMoney,
)
from .privacy import DailySalt, ua_family, utc_today, visitor_hash
from .repository import (
    InfraCostRecord,
    LoginAttemptRecord,
    Repository,
    UserRecord,
    VisitRecord,
    VoucherRecord,
)
from .services import PurgeError, ServiceClient
from .system import ServiceStatus, SystemProbe
from .vultr import VultrBilling, VultrError

log = logging.getLogger("lasteverlm_account")

SETTING_SMTP = "smtp"  # no longer written; a leftover row is deleted at start
SETTING_DOMAINS = "allowed_domains"
SETTING_ADDRESSES = "allowed_addresses"
SETTING_VIEWER_DOMAINS = "viewer_domains"
SETTING_VIEWER_ADDRESSES = "viewer_addresses"
SETTING_VULTR_SYNC = "vultr_sync"  # {"last_sync", "last_error", "rows"}
_SETTING_KEYS: dict[str, tuple[str, str]] = {  # kind -> (setting key, list key inside the value)
    "domain": (SETTING_DOMAINS, "allowed_domains"),
    "address": (SETTING_ADDRESSES, "allowed_addresses"),
    "viewer": (SETTING_VIEWER_DOMAINS, "viewer_domains"),
    "viewer_address": (SETTING_VIEWER_ADDRESSES, "viewer_addresses"),
}
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")

_VOUCHER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


class AccountError(Exception):
    """A request the service refuses; carries the HTTP status the API should answer."""

    def __init__(
        self,
        status: int,
        message: str,
        code: str | None = None,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code  # stable marker for clients that must tell refusals apart
        self.details = details or {}  # extra fields the client renders (e.g. step, message)


@dataclass(frozen=True)
class PendingMail:
    to: str
    subject: str
    body: str


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _valid(key: str, value: Any) -> bool:
    try:
        Preferences(**{key: value})
    except ValueError:
        return False
    return True


def _role(user: UserRecord) -> Role:
    return "admin" if user.role == "admin" else "viewer" if user.role == "viewer" else "user"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_allow_value(kind: AllowKind, value: str) -> str:
    """Lower-cased, trimmed; a domain may be written with a leading ``@``. 422 on bad shape."""
    value = value.strip().lower()
    if kind in ("domain", "viewer"):
        value = value.lstrip("@")
        if not _DOMAIN_RE.match(value):
            raise AccountError(422, f"not a domain: {value!r}")
        return value
    local, sep, domain = value.rpartition("@")
    if not sep or not local or " " in value or not _DOMAIN_RE.match(domain):
        raise AccountError(422, f"not an e-mail address: {value!r}")
    return value


def normalize_voucher_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def generate_voucher_code() -> str:
    raw = "".join(secrets.choice(_VOUCHER_ALPHABET) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


class AccountService:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        mailer: Mailer,
        *,
        clock: Callable[[], datetime] | None = None,
        salt: DailySalt | None = None,
        rate_limit: RateLimitSettings | None = None,
        system: SystemProbe | None = None,
        services: ServiceClient | None = None,
        dependencies: DependencyProbe | None = None,
        vultr: VultrBilling | None = None,
    ) -> None:
        self.settings = settings
        self.repo = repository
        self.mailer = mailer
        self.system = system or SystemProbe(settings.system_services)
        self.services = services or ServiceClient(
            ingest_url=settings.ingest_url, rag_url=settings.rag_url
        )
        self.dependencies = dependencies or DependencyProbe({})
        self._cipher = VoucherCipher(settings.voucher_key)
        key = settings.vultr_billing_api_key
        self.vultr = vultr or (VultrBilling(key) if key else None)
        # The env defaults of the rate-limit rule, shared with the middleware; the panel
        # overrides the four runtime fields through the settings table (context/core.md).
        self.rate_limit = rate_limit or RateLimitSettings()
        self.auth = AuthSettings(
            jwt_secret=settings.auth_jwt_secret, demo_token=settings.demo_token
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._salt = salt or DailySalt(settings.visit_hash_secret)

    def now(self) -> datetime:
        return self._clock()

    # lifecycle --------------------------------------------------------------
    async def startup(self) -> None:
        """Seed admin-editable settings from the environment, apply retention, say what happened."""
        seed = list(self.settings.allowed_domains_seed)
        if await self.repo.set_setting_if_missing(SETTING_DOMAINS, {"allowed_domains": seed}):
            log.info("settings: allowed_domains seeded from AUTH_ALLOWED_DOMAINS (%d)", len(seed))
        elif seed and not await self.allowed_domains():
            # An empty persisted list is "never configured", not an admin's choice: a
            # deployment whose seed was empty on first start would otherwise stay locked.
            await self._store("domain", seed)
            log.info(
                "settings: empty allowed_domains re-seeded from AUTH_ALLOWED_DOMAINS (%d)",
                len(seed),
            )
        else:
            log.info("settings: allowed_domains present (%d)", len(await self.allowed_domains()))
        # SMTP comes from the environment (context/admin-settings.md); a row from the time
        # the admin panel stored it, password included, must not linger in the database.
        if await self.repo.delete_setting(SETTING_SMTP):
            log.info("settings: removed the stored smtp row, SMTP comes from the environment")
        smtp = self.settings.smtp
        if smtp is None:
            log.warning("smtp: not configured (SMTP_HOST unset), sign-in links cannot be mailed")
        else:
            log.info(
                "smtp: %s:%d, from %s, starttls %s, %s",
                smtp.host,
                smtp.port,
                smtp.from_address,
                "on" if smtp.starttls else "off",
                "with login" if smtp.username else "no login",
            )
        if (
            not self.settings.admin_emails
            and not await self.allowed_domains()
            and not await self.allowed_addresses()
        ):
            log.warning("nobody can log in: ADMIN_EMAILS is empty and the allowlist is empty")
        now = self.now()
        removed = await self.repo.purge_visits(
            now - timedelta(days=self.settings.visit_retention_days)
        )
        links = await self.repo.purge_magic_links(now)
        attempts = await self.repo.purge_login_attempts(
            now - timedelta(days=self.settings.access_retention_days)
        )
        log.info(
            "retention: removed %d visit_log rows older than %d days, %d expired magic links, "
            "%d login_attempts rows older than %d days",
            removed,
            self.settings.visit_retention_days,
            links,
            attempts,
            self.settings.access_retention_days,
        )
        # Core's middleware writes these tables and never deletes; this service owns their
        # retention (context/core.md). A ban holds until an admin lifts it, at most BAN_MAX_DAYS.
        access, blocks, bans = await self.repo.purge_access_tables(
            purge_params(
                self.settings.access_retention_days,
                (await self.ratelimit_rules()).ban_max_days,
                now,
            )
        )
        log.info(
            "retention: core tables: removed %d access_log rows, %d stale blocks older than "
            "%d days, %d bans (lifted before that or older than %d days)",
            access,
            blocks,
            self.settings.access_retention_days,
            bans,
            self.settings.ban_max_days,
        )
        log.info(
            "visitor hash salt: %s",
            "shared across replicas (VISIT_HASH_SECRET)" if self._salt.shared else "per process",
        )

    # auth -------------------------------------------------------------------
    async def _list(self, kind: AllowKind) -> list[str]:
        key, list_key = _SETTING_KEYS[kind]
        value = await self.repo.get_setting(key) or {}
        return sorted({str(v).lower() for v in value.get(list_key, [])})

    async def _store(self, kind: AllowKind, values: list[str]) -> None:
        key, list_key = _SETTING_KEYS[kind]
        await self.repo.set_setting(key, {list_key: sorted(set(values))})

    async def allowed_domains(self) -> list[str]:
        return await self._list("domain")

    async def allowed_addresses(self) -> list[str]:
        return await self._list("address")

    async def viewer_domains(self) -> list[str]:
        return await self._list("viewer")

    async def viewer_addresses(self) -> list[str]:
        return await self._list("viewer_address")

    async def allowlist(self) -> Allowlist:
        return Allowlist(
            allowed_domains=await self.allowed_domains(),
            allowed_addresses=await self.allowed_addresses(),
            viewer_domains=await self.viewer_domains(),
            viewer_addresses=await self.viewer_addresses(),
        )

    async def initial_role(self, email: str) -> Role:
        """The role a first sign-in gets: admin from ADMIN_EMAILS, viewer from a listed
        address or domain, user otherwise. The repository still turns the very first real
        user into an admin."""
        if email in self.settings.admin_emails:
            return "admin"
        if email in await self.viewer_addresses():
            return "viewer"
        if email.rsplit("@", 1)[-1] in await self.viewer_domains():
            return "viewer"
        return "user"

    async def add_allow_entry(self, kind: AllowKind, value: str) -> Allowlist:
        value = normalize_allow_value(kind, value)
        current = await self._list(kind)
        if value in current:
            raise AccountError(409, f"already listed: {value}")
        await self._store(kind, [*current, value])
        return await self.allowlist()

    async def remove_allow_entry(self, kind: AllowKind, value: str) -> None:
        value = value.strip().lower().lstrip("@")
        current = await self._list(kind)
        if value not in current:
            raise AccountError(404, f"not listed: {value}")
        await self._store(kind, [v for v in current if v != value])

    async def is_allowed(self, email: str) -> bool:
        """Listed address, listed domain, or an address in ADMIN_EMAILS so the first admin
        can get in."""
        if email in self.settings.admin_emails:
            return True
        if email in await self.allowed_addresses():
            return True
        domain = email.rsplit("@", 1)[-1]
        return domain in await self.allowed_domains()

    async def request_link(self, email: str, ip: str = "unknown") -> PendingMail:
        """Prepare a magic link for an allowed address; 403 ``not_allowed`` for any other.

        A refused address is told so (context/auth.md): no mail goes out for it. Either
        way the attempt is logged with the plain client address (context/privacy.md).
        """
        email = normalize_email(email)
        now = self.now()
        allowed = "@" in email and await self.is_allowed(email)
        if allowed:
            # Per-address quota, counted on the attempts already logged; a throttled request
            # writes no row, so the quota also caps what one address can add to the table.
            sent = await self.repo.count_allowed_attempts(email, now - timedelta(hours=1))
            if sent >= self.settings.link_quota_per_hour:
                raise AccountError(
                    429,
                    f"{self.settings.link_quota_per_hour} sign-in links were sent to this "
                    "address in the last hour. Use one of them, or try again later.",
                    "too_many_links",
                )
        await self.repo.add_login_attempt(
            LoginAttemptRecord(now, email[:254], ip, "allowed" if allowed else "refused")
        )
        if not allowed:
            raise AccountError(403, "This address has no access to lasteverLM.", "not_allowed")
        token = secrets.token_urlsafe(32)
        expires_at = self.now() + timedelta(minutes=self.settings.magic_link_ttl_minutes)
        await self.repo.create_magic_link(email, hash_secret(token), expires_at)
        link = f"{self.settings.public_base_url}/auth/callback?token={token}"
        subject, body = magic_link_mail(link, token, self.settings.magic_link_ttl_minutes)
        return PendingMail(to=email, subject=subject, body=body)

    async def deliver(self, mail: PendingMail) -> None:
        config = self.settings.smtp
        if config is None:
            log.error("cannot send mail: SMTP is not configured")
            return
        try:
            await self.mailer.send(config, mail.to, mail.subject, mail.body)
        except MailError as exc:
            log.error("mail delivery failed: %s", exc)

    async def complete_login(self, token: str) -> tuple[str, User]:
        now = self.now()
        email = await self.repo.consume_magic_link(hash_secret(token), now)
        if email is None:
            raise AccountError(401, "invalid or expired link")
        user = await self.repo.get_user_by_email(email)
        if user is None:
            user = await self.repo.create_user(email, role=await self.initial_role(email), now=now)
        await self.repo.record_login(user.id, now)
        jwt_token = issue_jwt(
            user.id, self.settings.auth_jwt_secret, timedelta(days=self.settings.jwt_ttl_days), now
        )
        return jwt_token, await self._user_view(user)

    # account ----------------------------------------------------------------
    async def user(self, user_id: uuid.UUID) -> UserRecord:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise AccountError(401, "unknown user")
        return user

    async def user_view(self, user_id: uuid.UUID) -> User:
        return await self._user_view(await self.user(user_id))

    async def _user_view(self, user: UserRecord) -> User:
        totals = await self.repo.credit_totals(user.id)
        return User(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            balance_cents=totals.balance_cents,
            created_at=user.created_at,
            role=_role(user),
            preferences=self.preferences_of(user),
        )

    @staticmethod
    def preferences_of(user: UserRecord) -> Preferences:
        """The stored object, tolerant of keys a later version may have added or removed:
        unknown keys are ignored, a stored value that no longer validates reads as unset."""
        known = {k: user.preferences.get(k) for k in Preferences.model_fields}
        try:
            return Preferences(**known)
        except ValueError:
            return Preferences(**{k: v for k, v in known.items() if _valid(k, v)})

    async def preferences(self, user_id: uuid.UUID) -> Preferences:
        return self.preferences_of(await self.user(user_id))

    async def update_preferences(self, user_id: uuid.UUID, update: PreferencesUpdate) -> User:
        """Merge the keys the client sent (null clears) into the stored object."""
        if user_id == DEMO_USER_ID:
            raise AccountError(403, "the shared demo user has no preferences to change")
        user = await self.user(user_id)
        merged = self.preferences_of(user).model_dump()
        merged.update(update.model_dump(include=update.model_fields_set))
        await self.repo.set_preferences(user.id, {k: v for k, v in merged.items() if v is not None})
        return await self.user_view(user.id)

    async def redeem(self, user_id: uuid.UUID, code: str) -> User:
        user = await self.user(user_id)
        normalized = normalize_voucher_code(code)
        if not normalized:
            raise AccountError(404, "unknown or already redeemed voucher")
        amount = await self.repo.redeem_voucher(hash_secret(normalized), user.id, self.now())
        if amount is None:
            raise AccountError(404, "unknown or already redeemed voucher")
        return await self._user_view(user)

    async def record_visit(
        self, path: str, user_id: uuid.UUID | None, ip: str, user_agent: str | None
    ) -> None:
        now = self.now()
        salt = self._salt.for_day(utc_today(now))
        await self.repo.add_visit(
            VisitRecord(
                at=now,
                path=path[:512],
                user_id=user_id,
                ip_hash=visitor_hash(ip, salt),
                ua_family=ua_family(user_agent),
            )
        )

    # admin ------------------------------------------------------------------
    async def require_admin(self, user_id: uuid.UUID) -> UserRecord:
        user = await self.user(user_id)
        if user.role != "admin" or user.id == DEMO_USER_ID:
            raise AccountError(403, "admin only")
        return user

    async def require_reader(self, user_id: uuid.UUID) -> UserRecord:
        """Viewers and admins read the admin panel; the demo user is neither."""
        user = await self.user(user_id)
        if user.role not in ("viewer", "admin") or user.id == DEMO_USER_ID:
            raise AccountError(403, "admin only")
        return user

    async def delete_user(self, caller: UserRecord, user_id: uuid.UUID, bearer: str) -> None:
        """Orchestrated hard delete (context/deletion.md): rag, then ingest purge the user's
        data on the admin's bearer; only when both answered does account delete its rows.
        A failing step stops everything, nothing of account's is touched, 502 names the step."""
        user = await self.repo.get_user(user_id)
        if user is None:
            raise AccountError(404, "unknown user")
        if user.id == caller.id:
            raise AccountError(409, "you cannot delete your own account; ask another admin")
        if user.id == DEMO_USER_ID:
            raise AccountError(409, "the shared demo user cannot be deleted")
        for step in ("rag", "ingest"):
            try:
                await self.services.purge_user(step, user.id, bearer)
            except PurgeError as exc:
                log.error("user %s not deleted, %s failed: %s", user.id, exc.step, exc.message)
                raise AccountError(
                    502,
                    f"{exc.step} could not purge the user's data: {exc.message}",
                    "purge_failed",
                    {"step": exc.step, "message": exc.message},
                ) from exc
        try:
            await self.repo.delete_user(user.id)
        except Exception as exc:  # the other services are done; say so, the repeat finishes it
            log.error("user %s: rag and ingest purged, account's delete failed: %s", user.id, exc)
            raise AccountError(
                502,
                "account could not delete the user's rows; repeat the call",
                "purge_failed",
                {"step": "account", "message": type(exc).__name__},
            ) from exc
        log.info("user %s deleted by %s", user.email, caller.email)

    async def set_user_role(self, user_id: uuid.UUID, role: Role) -> AdminUserView:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise AccountError(404, "unknown user")
        if user.id == DEMO_USER_ID:
            raise AccountError(409, "the shared demo user keeps the user role")
        if user.role == "admin" and role != "admin" and await self.repo.count_admins() <= 1:
            raise AccountError(409, "the last admin keeps the admin role")
        await self.repo.set_role(user.id, role)
        rows = [u for u in await self.admin_users() if u.id == user.id]
        return rows[0]

    def smtp_view(self) -> Smtp:
        """What is in effect, without the password; empty host when not configured."""
        config = self.settings.smtp
        if config is None:
            return Smtp(host="", port=587, username="", from_address="", starttls=True)
        return Smtp(
            host=config.host,
            port=config.port,
            username=config.username,
            from_address=config.from_address,
            starttls=config.starttls,
        )

    async def send_test_mail(self, to: str) -> None:
        config = self.settings.smtp
        if config is None:
            raise AccountError(409, "SMTP is not configured")
        try:
            await self.mailer.send(
                config, to, "lasteverLM SMTP test", "SMTP settings work. Nothing else to do.\n"
            )
        except MailError as exc:
            raise AccountError(502, f"SMTP delivery failed: {exc}") from exc

    async def admin_users(self) -> list[AdminUserView]:
        """Every user row, the seeded demo user included: it consumes credit like anyone
        else, and the stats count it the same way so the numbers add up."""
        totals = await self.repo.all_credit_totals()
        result = []
        for user in await self.repo.list_users():
            t = totals.get(user.id)
            result.append(
                AdminUserView(
                    id=user.id,
                    email=user.email,
                    is_admin=user.is_admin,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                    balance_cents=t.balance_cents if t else 0,
                    usage_cents=t.usage_cents_whole if t else 0,
                    granted_cents=t.credited_cents if t else 0,
                    role=_role(user),
                )
            )
        return result

    async def admin_vouchers(self, limit: int) -> list[AdminVoucher]:
        return [self._admin_voucher(v) for v in await self.repo.list_vouchers(limit)]

    async def delete_voucher(self, voucher_id: uuid.UUID) -> None:
        outcome = await self.repo.delete_voucher(voucher_id)
        if outcome == "missing":
            raise AccountError(404, "unknown voucher")
        if outcome == "redeemed":
            raise AccountError(409, "a redeemed voucher is history and cannot be deleted")

    async def admin_daily_stats(self, days: int) -> DailyStats:
        """The last `days` UTC days up to today, every day present."""
        today = utc_today(self.now())
        first = today - timedelta(days=days - 1)
        since = datetime.combine(first, time.min, tzinfo=UTC)
        found = {r.day: r for r in await self.repo.daily_stats(since)}
        out = []
        for offset in range(days):
            day = first + timedelta(days=offset)
            r = found.get(day)
            out.append(
                DailyStat(
                    day=day,
                    logins=r.logins if r else 0,
                    visits=r.visits if r else 0,
                    usage_cost_cents=r.usage_cost_cents if r else 0,
                    credits_granted_cents=r.credits_granted_cents if r else 0,
                )
            )
        return DailyStats(days=out)

    async def admin_usage_stats(self) -> UsageStats:
        return UsageStats(
            by_model=[
                ModelUsage(model=r.model, kind=r.kind, calls=r.calls, cost_cents=r.cost_cents)
                for r in await self.repo.usage_by_model()
            ],
            top_users=[
                UserUsage(email=r.email, usage_cents=r.usage_cents, balance_cents=r.balance_cents)
                for r in await self.repo.top_users_by_usage(10)
            ],
        )

    async def admin_system(self) -> SystemInfo:
        """Versions, the other services' health, and the pods and deployments of this namespace."""
        own = ServiceStatus(
            "account",
            self.settings.app_version,
            self.settings.app_commit,
            True,  # this process answers; what it depends on is in `dependencies`
            {str(k): str(v) for k, v in (await self.dependencies.states()).items()},
        )
        snap = await self.system.snapshot(own)
        return SystemInfo(
            version=self.settings.app_version,
            commit=self.settings.app_commit,
            cluster=snap.cluster,
            services=[SystemService(**s.__dict__) for s in snap.services],
            pods=[SystemPod(**p.__dict__) for p in snap.pods],
            deployments=[SystemDeployment(**d.__dict__) for d in snap.deployments],
        )

    async def admin_stats(self) -> AdminStats:
        now = self.now()
        s = await self.repo.stats(now - timedelta(hours=24), now)
        return AdminStats(
            users=s.users,
            logins_24h=s.logins_since,
            vouchers=VoucherCounts(
                issued=s.vouchers_issued,
                redeemed=s.vouchers_redeemed,
                open=s.vouchers_issued - s.vouchers_redeemed,
            ),
            credits_granted_cents=s.credits_granted_cents,
            usage_cost_cents=UsageCost(
                total=s.usage_cost_cents_total, last_24h=s.usage_cost_cents_since
            ),
            blocks_active=s.blocks_active,
            bans_active=s.bans_active,
        )

    async def admin_logins(self, limit: int) -> list[AdminLogin]:
        return [
            AdminLogin(user_id=r.user_id, email=r.email, at=r.at)
            for r in await self.repo.list_logins(limit)
        ]

    async def ratelimit_rules(self) -> RateLimitRules:
        """What core's middleware applies: the stored override, else the env defaults.
        A malformed row counts as no override (the middleware does the same, and warns)."""
        defaults = RateLimitRules.from_settings(self.rate_limit)
        raw = await self.repo.get_setting(RATE_LIMIT_SETTINGS_KEY)
        if raw is None:
            return defaults
        try:
            return RateLimitRules.parse(raw, defaults)
        except ValueError as exc:
            log.warning("stored rate-limit rules unusable, showing env defaults: %s", exc)
            return defaults

    async def ratelimit_view(self) -> RateLimitRulesView:
        rules = await self.ratelimit_rules()
        return RateLimitRulesView(**rules.as_json(), retention_days=self.rate_limit.retention_days)

    async def update_ratelimit(self, update: RateLimitRulesUpdate) -> RateLimitRulesView:
        try:
            # core's bounds, one validator; an omitted ban_max_days keeps the env default
            rules = RateLimitRules.parse(
                update.model_dump(exclude_none=True), RateLimitRules.from_settings(self.rate_limit)
            )
        except ValueError as exc:
            raise AccountError(422, str(exc)) from exc
        await self.repo.set_setting(RATE_LIMIT_SETTINGS_KEY, rules.as_json())
        return await self.ratelimit_view()

    async def reset_ratelimit(self) -> None:
        """Back to the env defaults: the override row goes, the middleware notices within 30 s."""
        await self.repo.delete_setting(RATE_LIMIT_SETTINGS_KEY)

    async def admin_login_attempts(self, limit: int) -> list[AdminLoginAttempt]:
        return [
            AdminLoginAttempt(at=a.at, email=a.email, ip=a.ip, outcome=a.outcome)
            for a in await self.repo.list_login_attempts(limit)
        ]

    async def admin_visits(self, days: int) -> list[AdminVisit]:
        since = self.now() - timedelta(days=days)
        return [
            AdminVisit(day=r.day, path=r.path, visits=r.visits, unique=r.unique)
            for r in await self.repo.visit_summary(since)
        ]

    # access control: core's middleware writes these tables, admins read and lift.
    async def admin_blocks(self) -> list[AdminBlock]:
        return [
            AdminBlock(
                ip=b.ip, blocked_until=b.blocked_until, strikes=b.strikes, updated_at=b.updated_at
            )
            for b in await self.repo.active_blocks(self.now())
        ]

    async def admin_bans(self, include_lifted: bool) -> list[AdminBan]:
        return [
            AdminBan(ip=b.ip, reason=b.reason, created_at=b.created_at, lifted_at=b.lifted_at)
            for b in await self.repo.bans(include_lifted=include_lifted)
        ]

    async def lift_ban(self, ip: str) -> None:
        if not await self.repo.lift_ban(ip.strip(), self.now()):
            raise AccountError(404, "no active ban for this address")

    async def admin_access(self, limit: int) -> list[AdminAccess]:
        return [
            AdminAccess(
                at=a.at,
                ip=a.ip,
                method=a.method,
                path=a.path,
                status=a.status,
                user_id=a.user_id,
                service=a.service,
            )
            for a in await self.repo.access_log(limit)
        ]

    async def create_vouchers(
        self,
        admin: UserRecord,
        amount_cents: int | None,
        count: int,
        send_to: str | None = None,
        message: str | None = None,
        allow: bool = True,
        paid: bool = False,
    ) -> list[str]:
        """Create `count` vouchers; the plain codes come back once. The code is stored hashed
        (for the redeem) and encrypted (so an admin can show or mail it again). With
        `send_to`, every created voucher goes out by mail right away."""
        amount = amount_cents or self.settings.voucher_default_cents
        now = self.now()
        codes = []
        for _ in range(count):
            code = generate_voucher_code()
            voucher_id = await self.repo.create_voucher(
                hash_secret(normalize_voucher_code(code)),
                amount,
                admin.id,
                now,
                code_enc=self._cipher.encrypt(code),
                paid=paid,
            )
            codes.append(code)
            if send_to:
                await self.send_voucher(admin, voucher_id, send_to, message, allow)
        return codes

    def _plain_code(self, voucher: VoucherRecord) -> str | None:
        return self._cipher.decrypt(voucher.code_enc) if voucher.code_enc else None

    def _not_recoverable(self, what: str) -> AccountError:
        return AccountError(
            404,
            f"this voucher was created before codes were stored recoverably; {what}",
            "not_recoverable",
        )

    async def voucher_code(self, voucher_id: uuid.UUID) -> VoucherCode:
        voucher = await self.repo.get_voucher(voucher_id)
        if voucher is None:
            raise AccountError(404, "unknown voucher")
        code = self._plain_code(voucher)
        if code is None:
            raise self._not_recoverable("only its hash exists")
        return VoucherCode(code=code)

    async def send_voucher(
        self,
        admin: UserRecord,
        voucher_id: uuid.UUID,
        email: str,
        message: str | None,
        allow: bool,
    ) -> AdminVoucher:
        """Mail the voucher to `email` on the admin's behalf: allowlist the address first when
        asked (idempotent), at most `voucher_mail_quota_per_hour` mails per address."""
        voucher = await self.repo.get_voucher(voucher_id)
        if voucher is None:
            raise AccountError(404, "unknown voucher")
        if voucher.redeemed_at is not None:
            raise AccountError(409, "this voucher was redeemed already", "already_redeemed")
        code = self._plain_code(voucher)
        if code is None:
            raise self._not_recoverable("nothing to send")
        email = normalize_email(email)
        if self.settings.smtp is None:
            raise AccountError(409, "SMTP is not configured", "smtp_not_configured")
        now = self.now()
        sent = await self.repo.count_voucher_mails(email, now - timedelta(hours=1))
        if sent >= self.settings.voucher_mail_quota_per_hour:
            raise AccountError(
                429,
                f"{self.settings.voucher_mail_quota_per_hour} voucher mails went to this address "
                "in the last hour; try again later.",
                "too_many_mails",
            )
        if allow and not await self.is_allowed(email):
            await self.add_allow_entry("address", email)
        subject, body = voucher_mail(
            code,
            voucher.amount_cents,
            self.settings.public_base_url,
            message,
            self.preferences_of(admin).ui_language,
        )
        try:
            await self.mailer.send(self.settings.smtp, email, subject, body)
        except MailError as exc:
            raise AccountError(502, f"mail could not be sent: {exc}", "mail_failed") from exc
        await self.repo.mark_voucher_sent(voucher.id, email, now)
        log.info("voucher %s sent to %s by %s", voucher.id, email, admin.email)
        updated = await self.repo.get_voucher(voucher.id)
        assert updated is not None
        return self._admin_voucher(updated)

    def _admin_voucher(self, v: VoucherRecord) -> AdminVoucher:
        code = self._plain_code(v)
        return AdminVoucher(
            id=v.id,
            amount_cents=v.amount_cents,
            created_by=v.created_by,
            created_at=v.created_at,
            redeemed_by=v.redeemed_by,
            redeemed_at=v.redeemed_at,
            status="redeemed" if v.redeemed_at is not None else "open",
            code_masked=f"{code[:4]}-****-****-****" if code else None,
            recoverable=code is not None,
            sent_to=v.sent_to,
            sent_at=v.sent_at,
            paid=v.paid,
        )

    async def set_voucher_paid(self, voucher_id: uuid.UUID, paid: bool) -> AdminVoucher:
        if not await self.repo.set_voucher_paid(voucher_id, paid):
            raise AccountError(404, "unknown voucher")
        voucher = await self.repo.get_voucher(voucher_id)
        assert voucher is not None
        return self._admin_voucher(voucher)

    # finance: infrastructure costs -------------------------------------------
    async def usd_per_eur(self) -> Decimal | None:
        """The one exchange rate: the pricing rules' usd_per_eur, which core books with."""
        return (await self.pricing_rules()).usd_per_eur

    async def sync_vultr(self) -> int:
        """Read Vultr's billing and upsert the monthly lines; the outcome is kept for the
        page. Raises 409 ``vultr_not_connected`` without a key."""
        if self.vultr is None:
            raise AccountError(
                409, "Vultr billing is not connected (VULTR_BILLING_API_KEY)", "vultr_not_connected"
            )
        now = self.now()
        try:
            lines = await self.vultr.cost_lines()
        except VultrError as exc:
            await self.repo.set_setting(
                SETTING_VULTR_SYNC, {"last_sync": None, "last_error": str(exc), "rows": 0}
            )
            log.warning("vultr billing sync failed: %s", exc)
            raise AccountError(502, f"Vultr billing sync failed: {exc}", "vultr_failed") from exc
        rows = await self.repo.upsert_infra_costs(
            "vultr",
            [
                InfraCostRecord(
                    uuid.uuid4(), ln.month, "vultr", ln.item, ln.amount_cents, ln.currency
                )
                for ln in lines
            ],
        )
        await self.repo.set_setting(
            SETTING_VULTR_SYNC, {"last_sync": now.isoformat(), "last_error": None, "rows": rows}
        )
        log.info("vultr billing sync: %d monthly lines", rows)
        return rows

    async def vultr_loop(self, interval_seconds: float = 24 * 3600) -> None:
        """The daily sync, started by the app when a key is set. Upserts are idempotent, so
        every replica may run it; a failure is logged and kept for the page, never raised."""
        while True:
            with contextlib.suppress(AccountError):  # logged and kept by sync_vultr
                await self.sync_vultr()
            await asyncio.sleep(interval_seconds)

    def _eur(self, cents: int, currency: str, usd_per_eur: Decimal | None) -> int | None:
        if currency == "EUR":
            return cents
        return round(Decimal(cents) / usd_per_eur) if usd_per_eur else None

    def _infra_cost(self, r: InfraCostRecord, rate: Decimal | None) -> InfraCost:
        return InfraCost(
            id=r.id,
            date=r.date,
            source="vultr" if r.source == "vultr" else "manual",
            item=r.item,
            amount_cents=r.amount_cents,
            currency="USD" if r.currency == "USD" else "EUR",
            amount_eur_cents=self._eur(r.amount_cents, r.currency, rate),
        )

    async def admin_infra(self, since: date, until: date) -> InfraCosts:
        rate = await self.usd_per_eur()
        sync = await self.repo.get_setting(SETTING_VULTR_SYNC) or {}
        rows = await self.repo.list_infra_costs(since, until)
        totals: dict[str, int] = {}
        for r in rows:
            totals[r.currency] = totals.get(r.currency, 0) + r.amount_cents
        converted = [self._eur(r.amount_cents, r.currency, rate) for r in rows]
        last = sync.get("last_sync")
        return InfraCosts(
            vultr="connected" if self.vultr is not None else "not connected",
            last_sync=datetime.fromisoformat(last) if last else None,
            last_error=sync.get("last_error"),
            usd_per_eur=float(rate) if rate is not None else None,
            entries=[self._infra_cost(r, rate) for r in rows],
            totals_by_currency=totals,
            total_eur_cents=None if None in converted else sum(c or 0 for c in converted),
        )

    async def add_infra_cost(self, body: InfraCostAdd) -> InfraCost:
        record = InfraCostRecord(
            uuid.uuid4(), body.date, "manual", body.item, body.amount_cents, body.currency
        )
        if not await self.repo.add_infra_cost(record):
            raise AccountError(409, "an entry with this date and item exists already")
        return self._infra_cost(record, await self.usd_per_eur())

    async def delete_infra_cost(self, cost_id: uuid.UUID) -> None:
        outcome = await self.repo.delete_infra_cost(cost_id)
        if outcome == "missing":
            raise AccountError(404, "unknown entry")
        if outcome == "not_manual":
            raise AccountError(
                409, "Vultr entries come from the billing sync and cannot be deleted", "not_manual"
            )

    # finance: pricing ---------------------------------------------------------
    async def pricing_rules(self) -> PricingRules:
        raw = await self.repo.get_setting(PRICING_SETTINGS_KEY)
        if raw is None:
            return DEFAULT_PRICING_RULES
        try:
            return PricingRules.parse(raw)
        except ValueError as exc:
            log.warning("stored pricing rules unusable, showing the defaults: %s", exc)
            return DEFAULT_PRICING_RULES

    async def pricing_view(self, rules: PricingRules | None = None) -> PricingView:
        rules = rules or await self.pricing_rules()
        averages = {
            a.action: a for a in await self.repo.action_averages(self.now() - timedelta(days=30))
        }
        preview = []
        for action in sorted(USAGE_ACTIONS):
            avg = averages.get(action)
            fixed = rules.fixed_cents(action)
            charge = rules.charge_cents(action, avg.avg_cost_cents) + fixed if avg else None
            preview.append(
                PricingPreviewRow(
                    action=action,
                    actions=avg.actions if avg else 0,
                    avg_cost_cents=_money(avg.avg_cost_cents) if avg else None,
                    margin_pct=_money(rules.margin_pct(action)),
                    fixed_cents=_money(fixed),
                    charge_cents=_money(charge) if charge is not None else None,
                )
            )
        return PricingView(rules=rules.as_json(), actions=sorted(USAGE_ACTIONS), preview=preview)

    def _parse_pricing(self, body: dict[str, Any]) -> PricingRules:
        try:
            return PricingRules.parse(body)  # core's validator, the one the services trust
        except ValueError as exc:
            raise AccountError(422, str(exc)) from exc

    async def update_pricing(self, body: dict[str, Any]) -> PricingView:
        rules = self._parse_pricing(body)
        await self.repo.set_setting(PRICING_SETTINGS_KEY, rules.as_json())
        return await self.pricing_view(rules)

    async def preview_pricing(self, body: dict[str, Any]) -> PricingView:
        """What the proposed rules would charge, without storing them."""
        return await self.pricing_view(self._parse_pricing(body))

    async def reset_pricing(self) -> None:
        """Margins and fees back to zero. The exchange rate stays: without it core refuses
        to book, so a reset must not take it away."""
        rate = await self.usd_per_eur()
        if rate is None:
            await self.repo.delete_setting(PRICING_SETTINGS_KEY)
            return
        await self.repo.set_setting(
            PRICING_SETTINGS_KEY,
            PricingRules.parse(
                {"usd_per_eur": float(rate), "default_margin_pct": 0, "actions": {}}
            ).as_json(),
        )

    # finance: costs, revenue, profit -----------------------------------------
    async def finance_costs(self, since: date, until: date, group: str) -> FinanceCosts:
        rows = await self.repo.usage_groups(since, until, group)
        return FinanceCosts(
            from_=since,
            to=until,
            group=group,
            rows=[
                FinanceGroupRow(
                    key=r.key,
                    calls=r.calls,
                    actions=r.actions,
                    cost_cents=_money(r.cost_cents),
                    charge_cents=_money(r.charge_cents),
                    cost_usd_cents=_money(r.cost_usd_cents),
                )
                for r in rows
            ],
            total_cost_cents=_money(sum((r.cost_cents for r in rows), Decimal(0))),
            total_charge_cents=_money(sum((r.charge_cents for r in rows), Decimal(0))),
            total_cost_usd_cents=_money(sum((r.cost_usd_cents for r in rows), Decimal(0))),
        )

    async def finance_revenue(self, since: date, until: date) -> FinanceRevenue:
        periods = await self.repo.usage_periods(since, until, "month")
        money = await self.repo.voucher_money(since, until)
        totals = await self.repo.all_credit_totals()
        return FinanceRevenue(
            from_=since,
            to=until,
            charged_cents=_money(sum((p.charge_cents for p in periods if not p.demo), Decimal(0))),
            demo_charged_cents=_money(sum((p.charge_cents for p in periods if p.demo), Decimal(0))),
            vouchers=VoucherMoney(**money.__dict__),
            outstanding_credit_cents=sum(
                max(t.balance_cents, 0) for uid, t in totals.items() if uid != DEMO_USER_ID
            ),
        )

    async def finance_profit(self, since: date, until: date, group: str) -> FinanceProfit:
        rate = await self.usd_per_eur()
        first_month = since.replace(day=1)
        infra_rows = await self.repo.list_infra_costs(first_month, until)
        infra: dict[date, Decimal | None] = {}
        for r in infra_rows:
            month = r.date.replace(day=1)
            eur = self._eur(r.amount_cents, r.currency, rate)
            prev = infra.get(month, Decimal(0))
            infra[month] = None if eur is None or prev is None else prev + Decimal(eur)

        def infra_for(period: date) -> Decimal | None:
            month_total = infra.get(period.replace(day=1), Decimal(0))
            if month_total is None or group == "month":
                return month_total
            return month_total / calendar.monthrange(period.year, period.month)[1]

        sums: dict[date, list[Decimal]] = {}
        for p in await self.repo.usage_periods(since, until, group):
            row = sums.setdefault(p.period, [Decimal(0)] * 4)
            if p.demo:
                row[2] += p.charge_cents
                row[3] += p.cost_cents
            else:
                row[0] += p.charge_cents
                row[1] += p.cost_cents
        periods = _periods(since, until, group)
        rows = []
        for period in periods:
            charged, cost, demo_charged, demo_cost = sums.get(period, [Decimal(0)] * 4)
            infra_cost = infra_for(period)
            rows.append(
                ProfitRow(
                    period=period,
                    charged_cents=_money(charged),
                    model_cost_cents=_money(cost),
                    infra_cost_cents=_money(infra_cost) if infra_cost is not None else None,
                    profit_cents=(
                        _money(charged - cost - infra_cost) if infra_cost is not None else None
                    ),
                    demo_charged_cents=_money(demo_charged),
                    demo_cost_cents=_money(demo_cost),
                )
            )
        total = None
        if rows:
            infra_vals = [r.infra_cost_cents for r in rows]
            infra_total = None if None in infra_vals else sum(v or 0 for v in infra_vals)
            charged_total = sum(r.charged_cents for r in rows)
            cost_total = sum(r.model_cost_cents for r in rows)
            total = ProfitRow(
                period=since,
                charged_cents=round(charged_total, 4),
                model_cost_cents=round(cost_total, 4),
                infra_cost_cents=round(infra_total, 4) if infra_total is not None else None,
                profit_cents=(
                    round(charged_total - cost_total - infra_total, 4)
                    if infra_total is not None
                    else None
                ),
                demo_charged_cents=round(sum(r.demo_charged_cents for r in rows), 4),
                demo_cost_cents=round(sum(r.demo_cost_cents for r in rows), 4),
            )
        return FinanceProfit(
            from_=since,
            to=until,
            group="month" if group == "month" else "day",
            usd_per_eur=float(rate) if rate is not None else None,
            rows=rows,
            total=total,
        )


def _money(value: Decimal | float | int) -> float:
    """Cents as a JSON number, sub-cent exact to four places."""
    return float(round(Decimal(value), 4))


def _periods(since: date, until: date, group: str) -> list[date]:
    if group == "day":
        return [since + timedelta(days=i) for i in range((until - since).days + 1)]
    months, cur = [], since.replace(day=1)
    while cur <= until:
        months.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months
