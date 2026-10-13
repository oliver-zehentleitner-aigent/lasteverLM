"""Magic-link flow, allowlist, token lifecycle, admin assignment."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, verify_jwt

from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import ADMIN_EMAIL, DEMO_TOKEN, Clock, FakeMailer, bearer, login


def test_full_login_flow_issues_jwt_and_creates_user(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, user = login(client, mailer, "Alice@Example.org")

    assert user["email"] == "alice@example.org"  # lowercased
    assert user["balance_cents"] == 0
    claims = verify_jwt(token, "test-secret-not-for-production-0123456789")
    assert str(claims.sub) == user["id"]

    me = client.get("/api/account/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]
    assert set(me.json()) == {"id", "email", "is_admin", "balance_cents", "created_at"}


def test_request_link_refuses_an_address_without_access_and_says_so(
    client: TestClient, mailer: FakeMailer
) -> None:
    r = client.post("/api/account/auth/request-link", json={"email": "mallory@evil.test"})
    assert r.status_code == 403
    assert r.json() == {"error": "This address has no access to lasteverLM.", "code": "not_allowed"}
    assert mailer.sent == []

    r = client.post("/api/account/auth/request-link", json={"email": "alice@example.org"})
    assert r.status_code == 202
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "alice@example.org"
    assert "https://lasteverlm.test/auth/callback?token=" in mailer.sent[0].body


def test_admin_email_bypasses_domain_allowlist(client: TestClient, mailer: FakeMailer) -> None:
    service = client.app.state.service  # type: ignore[attr-defined]
    service.settings = replace(service.settings, admin_emails=frozenset({"boss@other.test"}))
    r = client.post("/api/account/auth/request-link", json={"email": "boss@other.test"})
    assert r.status_code == 202
    assert [m.to for m in mailer.sent] == ["boss@other.test"]


def test_link_is_single_use(client: TestClient, mailer: FakeMailer) -> None:
    login(client, mailer, "alice@example.org")
    r = client.get("/api/account/auth/callback", params={"token": mailer.sent[-1].token})
    assert r.status_code == 401
    assert r.json() == {"error": "invalid or expired link"}


def test_link_expires_after_ttl(client: TestClient, mailer: FakeMailer, clock: Clock) -> None:
    client.post("/api/account/auth/request-link", json={"email": "alice@example.org"})
    clock.advance(minutes=16)
    r = client.get("/api/account/auth/callback", params={"token": mailer.sent[-1].token})
    assert r.status_code == 401


def test_garbage_token_rejected(client: TestClient) -> None:
    assert client.get("/api/account/auth/callback", params={"token": "nope"}).status_code == 401
    assert client.get("/api/account/auth/callback").status_code == 422


def test_first_user_becomes_admin_and_admin_emails_too(
    client: TestClient, mailer: FakeMailer
) -> None:
    _, first = login(client, mailer, "first@example.org")
    _, second = login(client, mailer, "second@example.org")
    _, boss = login(client, mailer, ADMIN_EMAIL)
    assert first["is_admin"] is True
    assert second["is_admin"] is False
    assert boss["is_admin"] is True


def test_login_is_logged_and_second_login_reuses_user(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, user1 = login(client, mailer, "alice@example.org")
    _, user2 = login(client, mailer, "alice@example.org")
    assert user1["id"] == user2["id"]
    r = client.get("/api/account/admin/logins", headers=bearer(token))
    assert r.status_code == 200  # first user is admin
    assert [row["email"] for row in r.json()] == ["alice@example.org", "alice@example.org"]


def test_bearer_required(client: TestClient) -> None:
    assert client.get("/api/account/me").status_code == 401
    assert client.get("/api/account/me", headers=bearer("garbage")).status_code == 401
    assert client.get("/api/account/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_demo_token_resolves_to_seeded_demo_user(
    client: TestClient, repo: MemoryRepository
) -> None:
    # Without the row the migration seeds, the demo token must not pass.
    assert client.get("/api/account/me", headers=bearer(DEMO_TOKEN)).status_code == 401
    repo.users[DEMO_USER_ID] = UserRecord(
        DEMO_USER_ID, "demo@localhost", False, datetime.now(UTC), None
    )
    r = client.get("/api/account/me", headers=bearer(DEMO_TOKEN))
    assert r.status_code == 200
    assert r.json()["id"] == str(DEMO_USER_ID)
