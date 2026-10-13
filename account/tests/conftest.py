"""Shared fixtures: in-memory repository, capturing mailer, app with a test client."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import MemoryRateLimitStore, RateLimitSettings

from lasteverlm_account.config import Settings
from lasteverlm_account.mail import SmtpConfig
from lasteverlm_account.main import create_app
from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import AccountService

ADMIN_EMAIL = "root@example.org"
ALLOWED_DOMAIN = "example.org"
DEMO_TOKEN = "demo-secret"


@dataclass
class SentMail:
    to: str
    subject: str
    body: str

    @property
    def token(self) -> str:
        match = re.search(r"token=([A-Za-z0-9_\-]+)", self.body)
        assert match, self.body
        return match.group(1)


@dataclass
class FakeMailer:
    sent: list[SentMail] = field(default_factory=list)
    fail: bool = False

    async def send(self, config: SmtpConfig, to: str, subject: str, body: str) -> None:
        if self.fail:
            from lasteverlm_account.mail import MailError

            raise MailError("connection refused")
        self.sent.append(SentMail(to, subject, body))


class Clock:
    """Controllable time, so expiry and daily salt rotation are testable."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql://unused",
        auth_jwt_secret="test-secret-not-for-production-0123456789",
        public_base_url="https://lasteverlm.test",
        demo_token=DEMO_TOKEN,
        admin_emails=frozenset({ADMIN_EMAIL}),
        allowed_domains_seed=(ALLOWED_DOMAIN,),
        smtp=SmtpConfig("smtp.test", 587, "", "", "noreply@lasteverlm.test", True),
    )


@pytest.fixture
def repo() -> MemoryRepository:
    return MemoryRepository()


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer, clock: Clock
) -> AccountService:
    return AccountService(settings, repo, mailer, clock=clock)


@pytest.fixture
def limiter_store() -> MemoryRateLimitStore:
    return MemoryRateLimitStore()


@pytest.fixture
def rate_limit_settings() -> RateLimitSettings:
    return RateLimitSettings()


@pytest.fixture
def client(
    settings: Settings,
    repo: MemoryRepository,
    mailer: FakeMailer,
    clock: Clock,
    limiter_store: MemoryRateLimitStore,
    rate_limit_settings: RateLimitSettings,
) -> Iterator[TestClient]:
    app = create_app(
        settings=settings,
        repository=repo,
        mailer=mailer,
        rate_limit_store=limiter_store,
        rate_limit_settings=rate_limit_settings,
    )
    with TestClient(app) as c:
        c.app.state.service._clock = clock  # type: ignore[attr-defined]
        yield c


def login(client: TestClient, mailer: FakeMailer, email: str) -> tuple[str, dict[str, object]]:
    """Run the full magic-link flow and return (jwt, user)."""
    before = len(mailer.sent)
    r = client.post("/api/account/auth/request-link", json={"email": email})
    assert r.status_code == 202, r.text
    assert len(mailer.sent) == before + 1, "no mail was sent"
    r = client.get("/api/account/auth/callback", params={"token": mailer.sent[-1].token})
    assert r.status_code == 200, r.text
    data = r.json()
    return data["jwt"], data["user"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def new_user_id() -> uuid.UUID:
    return uuid.uuid4()
