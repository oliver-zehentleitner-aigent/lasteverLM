"""Business rules of the account service, independent of HTTP and of the storage backend."""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from lasteverlm_core import DEMO_USER_ID, AuthSettings, User, issue_jwt, purge_params

from .config import Settings
from .mail import Mailer, MailError, magic_link_mail
from .models import (
    AdminAccess,
    AdminBan,
    AdminBlock,
    AdminLogin,
    AdminUser,
    AdminVisit,
    AllowKind,
    Allowlist,
    Smtp,
)
from .privacy import DailySalt, ua_family, utc_today, visitor_hash
from .repository import Repository, UserRecord, VisitRecord

log = logging.getLogger("lasteverlm_account")

SETTING_SMTP = "smtp"  # no longer written; a leftover row is deleted at start
SETTING_DOMAINS = "allowed_domains"
SETTING_ADDRESSES = "allowed_addresses"
_SETTING_KEYS: dict[str, tuple[str, str]] = {  # kind -> (setting key, list key inside the value)
    "domain": (SETTING_DOMAINS, "allowed_domains"),
    "address": (SETTING_ADDRESSES, "allowed_addresses"),
}
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")

_VOUCHER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


class AccountError(Exception):
    """A request the service refuses; carries the HTTP status the API should answer."""

    def __init__(self, status: int, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code  # stable marker for clients that must tell refusals apart


@dataclass(frozen=True)
class PendingMail:
    to: str
    subject: str
    body: str


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_allow_value(kind: AllowKind, value: str) -> str:
    """Lower-cased, trimmed; a domain may be written with a leading ``@``. 422 on bad shape."""
    value = value.strip().lower()
    if kind == "domain":
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
    ) -> None:
        self.settings = settings
        self.repo = repository
        self.mailer = mailer
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
            await self.repo.set_setting(SETTING_DOMAINS, {"allowed_domains": seed})
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
        log.info(
            "retention: removed %d visit_log rows older than %d days, %d expired magic links",
            removed,
            self.settings.visit_retention_days,
            links,
        )
        # Core's middleware writes these tables and never deletes; this service owns their
        # retention (context/core.md). A ban holds until an admin lifts it, at most BAN_MAX_DAYS.
        access, blocks, bans = await self.repo.purge_access_tables(
            purge_params(self.settings.access_retention_days, self.settings.ban_max_days, now)
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

    async def allowlist(self) -> Allowlist:
        return Allowlist(
            allowed_domains=await self.allowed_domains(),
            allowed_addresses=await self.allowed_addresses(),
        )

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

    async def set_allowed_domains(self, domains: list[str]) -> list[str]:
        """Whole-list replacement, used by the startup re-seed and tests."""
        cleaned = sorted({d.strip().lower().lstrip("@") for d in domains if d.strip()})
        await self._store("domain", cleaned)
        return cleaned

    async def is_allowed(self, email: str) -> bool:
        """Listed address, listed domain, or an address in ADMIN_EMAILS so the first admin
        can get in."""
        if email in self.settings.admin_emails:
            return True
        if email in await self.allowed_addresses():
            return True
        domain = email.rsplit("@", 1)[-1]
        return domain in await self.allowed_domains()

    async def request_link(self, email: str) -> PendingMail:
        """Prepare a magic link for an allowed address; 403 ``not_allowed`` for any other.

        A refused address is told so (context/auth.md): no mail goes out for it.
        """
        email = normalize_email(email)
        if "@" not in email or not await self.is_allowed(email):
            raise AccountError(403, "This address has no access to lasteverLM.", "not_allowed")
        token = secrets.token_urlsafe(32)
        expires_at = self.now() + timedelta(minutes=self.settings.magic_link_ttl_minutes)
        await self.repo.create_magic_link(email, hash_secret(token), expires_at)
        link = f"{self.settings.public_base_url}/auth/callback?token={token}"
        subject, body = magic_link_mail(link, self.settings.magic_link_ttl_minutes)
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
            user = await self.repo.create_user(
                email, admin=email in self.settings.admin_emails, now=now
            )
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
        )

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
        if not user.is_admin or user.id == DEMO_USER_ID:
            raise AccountError(403, "admin only")
        return user

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

    async def admin_users(self) -> list[AdminUser]:
        totals = await self.repo.all_credit_totals()
        result = []
        for user in await self.repo.list_users():
            t = totals.get(user.id)
            result.append(
                AdminUser(
                    id=user.id,
                    email=user.email,
                    is_admin=user.is_admin,
                    created_at=user.created_at,
                    last_login_at=user.last_login_at,
                    balance_cents=t.balance_cents if t else 0,
                    usage_cents=t.usage_cents if t else 0,
                )
            )
        return result

    async def admin_logins(self, limit: int) -> list[AdminLogin]:
        return [
            AdminLogin(user_id=r.user_id, email=r.email, at=r.at)
            for r in await self.repo.list_logins(limit)
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
        self, admin_id: uuid.UUID, amount_cents: int | None, count: int
    ) -> list[str]:
        amount = amount_cents or self.settings.voucher_default_cents
        now = self.now()
        codes = []
        for _ in range(count):
            code = generate_voucher_code()
            await self.repo.create_voucher(
                hash_secret(normalize_voucher_code(code)), amount, admin_id, now
            )
            codes.append(code)
        return codes
