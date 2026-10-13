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
    assert set(me.json()) == {
        "id",
        "email",
        "is_admin",
        "role",
        "balance_cents",
        "created_at",
        "preferences",
    }
    assert me.json()["preferences"] == {
        "ui_language": None,
        "output_language": None,
        "audio_voice": None,
        "trash_days": None,
        "pdf_capture": None,
        "theme": None,
    }


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


def test_every_link_request_is_logged_with_outcome_and_client_ip(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    client.post(
        "/api/account/auth/request-link",
        json={"email": "Mallory@evil.test"},
        headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"},  # the last hop is the ingress's
    )
    clock.advance(minutes=1)
    token, _ = login(client, mailer, "admin@example.org")
    assert [(a.email, a.ip, a.outcome) for a in repo.login_attempts] == [
        ("mallory@evil.test", "10.0.0.1", "refused"),
        ("admin@example.org", "0.0.0.0", "allowed"),  # the test client is no address
    ]
    r = client.get("/api/account/admin/login-attempts", headers=bearer(token))
    assert r.status_code == 200
    assert [(a["email"], a["outcome"]) for a in r.json()] == [
        ("admin@example.org", "allowed"),
        ("mallory@evil.test", "refused"),
    ]  # newest first
    assert set(r.json()[0]) == {"at", "email", "ip", "outcome"}
    assert (
        client.get("/api/account/admin/login-attempts?limit=1", headers=bearer(token)).json()[0][
            "email"
        ]
        == "admin@example.org"
    )


def test_pasted_code_from_the_mail_signs_in(client: TestClient, mailer: FakeMailer) -> None:
    r = client.post("/api/account/auth/request-link", json={"email": "alice@example.org"})
    assert r.status_code == 202
    body = mailer.sent[-1].body
    code = body.split("Or paste this code on the sign-in page:")[1].split()[0]
    assert code == mailer.sent[-1].token  # the code is the link's token
    r = client.get("/api/account/auth/callback", params={"token": code})
    assert r.status_code == 200 and r.json()["user"]["email"] == "alice@example.org"


def test_malformed_forwarded_header_cannot_break_a_request(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    r = client.post(
        "/api/account/auth/request-link",
        json={"email": "alice@example.org"},
        headers={"X-Forwarded-For": "10.0.0.1, not-an-address"},
    )
    assert r.status_code == 202
    assert repo.login_attempts[-1].ip == "0.0.0.0"  # what the inet column can hold
    r = client.post(
        "/api/account/visits", json={"path": "/"}, headers={"X-Forwarded-For": "<script>"}
    )
    assert r.status_code == 204


def test_five_links_per_address_per_hour(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    body = {"email": "alice@example.org"}
    for _ in range(5):
        assert client.post("/api/account/auth/request-link", json=body).status_code == 202
    r = client.post("/api/account/auth/request-link", json=body)
    assert r.status_code == 429
    assert r.json()["code"] == "too_many_links"
    assert r.json()["error"].startswith("5 sign-in links were sent to this address")
    assert len(mailer.sent) == 5
    assert len(repo.login_attempts) == 5  # the throttled request writes no row
    # another address is not affected; the quota is per address
    assert (
        client.post("/api/account/auth/request-link", json={"email": "bob@example.org"}).status_code
        == 202
    )
    # an hour later the address may ask again
    clock.advance(hours=1, minutes=1)
    assert client.post("/api/account/auth/request-link", json=body).status_code == 202


def test_session_token_lives_one_day_by_default(client: TestClient, mailer: FakeMailer) -> None:
    import jwt as pyjwt

    token, _ = login(client, mailer, "alice@example.org")
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 24 * 3600
