"""Configuration from the environment. Fails at startup when a required value is missing.

Secrets never live in the repository. ``SMTP_*`` is the mail configuration, read
once at start and shown read-only in the admin panel. ``AUTH_ALLOWED_DOMAINS`` is a
*seed value only*: it populates the ``settings`` table on first start and is ignored
once a row exists, because an admin edits the allowlist through the API afterwards.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from lasteverlm_core import UNKNOWN_BUILD

from .mail import SmtpConfig


class ConfigError(RuntimeError):
    """A required environment variable is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    auth_jwt_secret: str
    public_base_url: str
    demo_token: str | None
    admin_emails: frozenset[str] = field(default_factory=frozenset)
    allowed_domains_seed: tuple[str, ...] = ()
    smtp: SmtpConfig | None = None  # None: no SMTP_HOST, sign-in mails cannot be sent
    magic_link_ttl_minutes: int = 15
    link_quota_per_hour: int = 5  # sign-in links per address per hour, then 429
    jwt_ttl_days: int = 1  # sign-out is client-side; a token lives at most this long
    voucher_default_cents: int = 1000
    visit_retention_days: int = 30
    access_retention_days: int = 30  # core's RETENTION_DAYS, for the tables its middleware writes
    ban_max_days: int = 90  # core's BAN_MAX_DAYS: a ban holds until lifted, at most this long
    trust_proxy_headers: bool = True
    visit_hash_secret: str | None = None
    log_level: str = "INFO"
    app_version: str = (
        UNKNOWN_BUILD  # APP_VERSION, from the ConfigMap; shown on /healthz and /admin/system
    )
    app_commit: str = UNKNOWN_BUILD  # APP_COMMIT
    ingest_url: str = "http://ingest"  # the chart's Service names (INGEST_URL, RAG_URL): the
    rag_url: str = "http://rag"  # health probes of /admin/system and the user purge both use them

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ) if env is None else env

        def required(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise ConfigError(f"missing required environment variable {name}")
            return value

        smtp_host = env.get("SMTP_HOST", "").strip()
        smtp = (
            SmtpConfig(
                host=smtp_host,
                port=_positive_int(env.get("SMTP_PORT", "587"), "SMTP_PORT"),
                username=env.get("SMTP_USERNAME", "").strip(),
                password=env.get("SMTP_PASSWORD", ""),
                from_address=required("SMTP_FROM_ADDRESS"),
                starttls=_bool(env.get("SMTP_STARTTLS", "true"), "SMTP_STARTTLS"),
            )
            if smtp_host
            else None
        )

        return cls(
            database_url=required("DATABASE_URL"),
            auth_jwt_secret=required("AUTH_JWT_SECRET"),
            public_base_url=required("PUBLIC_BASE_URL").rstrip("/"),
            demo_token=env.get("DEMO_TOKEN", "").strip() or None,
            admin_emails=frozenset(_csv_lower(env.get("ADMIN_EMAILS", ""))),
            allowed_domains_seed=tuple(_csv_lower(env.get("AUTH_ALLOWED_DOMAINS", ""))),
            smtp=smtp,
            magic_link_ttl_minutes=_positive_int(
                env.get("MAGIC_LINK_TTL_MINUTES", "15"), "MAGIC_LINK_TTL_MINUTES"
            ),
            link_quota_per_hour=_positive_int(
                env.get("LINK_QUOTA_PER_HOUR", "5"), "LINK_QUOTA_PER_HOUR"
            ),
            jwt_ttl_days=_positive_int(env.get("JWT_TTL_DAYS", "1"), "JWT_TTL_DAYS"),
            voucher_default_cents=_positive_int(
                env.get("VOUCHER_DEFAULT_CENTS", "1000"), "VOUCHER_DEFAULT_CENTS"
            ),
            visit_retention_days=_positive_int(
                env.get("VISIT_RETENTION_DAYS", "30"), "VISIT_RETENTION_DAYS"
            ),
            access_retention_days=_positive_int(env.get("RETENTION_DAYS", "30"), "RETENTION_DAYS"),
            ban_max_days=_positive_int(env.get("BAN_MAX_DAYS", "90"), "BAN_MAX_DAYS"),
            trust_proxy_headers=_bool(
                env.get("TRUST_PROXY_HEADERS", "true"), "TRUST_PROXY_HEADERS"
            ),
            visit_hash_secret=env.get("VISIT_HASH_SECRET", "").strip() or None,
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            app_version=env.get("APP_VERSION", "").strip() or UNKNOWN_BUILD,
            app_commit=env.get("APP_COMMIT", "").strip() or UNKNOWN_BUILD,
            ingest_url=env.get("INGEST_URL", "").strip().rstrip("/") or "http://ingest",
            rag_url=env.get("RAG_URL", "").strip().rstrip("/") or "http://rag",
        )

    @property
    def system_services(self) -> tuple[tuple[str, str], ...]:
        """What /admin/system probes: the same two base URLs the purge calls use, plus
        /healthz — one way to reach each service, not two."""
        return (("ingest", f"{self.ingest_url}/healthz"), ("rag", f"{self.rag_url}/healthz"))


def _csv_lower(raw: str) -> list[str]:
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


def _bool(raw: str, name: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")
