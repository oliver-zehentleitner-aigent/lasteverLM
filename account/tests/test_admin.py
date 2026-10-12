"""Admin gate, settings round-trips, write-only SMTP password, test mail."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID

from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import SETTING_SMTP

from .conftest import DEMO_TOKEN, FakeMailer, bearer, login

ADMIN_ROUTES = [
    ("GET", "/api/account/admin/users", None),
    ("GET", "/api/account/admin/logins", None),
    ("GET", "/api/account/admin/visits", None),
    ("GET", "/api/account/admin/settings/smtp", None),
    ("GET", "/api/account/admin/settings/domains", None),
    ("POST", "/api/account/admin/vouchers", {}),
    ("GET", "/api/account/admin/blocks", None),
    ("GET", "/api/account/admin/bans", None),
    ("DELETE", "/api/account/admin/bans/203.0.113.1", None),
    ("GET", "/api/account/admin/access", None),
]


def test_non_admin_gets_403_everywhere(client: TestClient, mailer: FakeMailer) -> None:
    login(client, mailer, "first@example.org")  # first user: admin
    token, user = login(client, mailer, "second@example.org")
    assert user["is_admin"] is False
    for method, path, body in ADMIN_ROUTES:
        r = client.request(method, path, json=body, headers=bearer(token))
        assert r.status_code == 403, (method, path, r.text)
        assert r.json() == {"error": "admin only"}


def test_demo_user_is_never_admin(client: TestClient, repo: MemoryRepository) -> None:
    # Even with the flag set in the database the demo identity is refused.
    repo.users[DEMO_USER_ID] = UserRecord(
        DEMO_USER_ID, "demo@localhost", True, datetime.now(UTC), None
    )
    r = client.get("/api/account/admin/users", headers=bearer(DEMO_TOKEN))
    assert r.status_code == 403


def test_domains_roundtrip_normalizes(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    r = client.get("/api/account/admin/settings/domains", headers=bearer(token))
    assert r.json() == {"allowed_domains": ["example.org"]}

    r = client.put(
        "/api/account/admin/settings/domains",
        json={"allowed_domains": [" Example.ORG", "@acme.test", "acme.test", ""]},
        headers=bearer(token),
    )
    assert r.status_code == 200
    assert r.json() == {"allowed_domains": ["acme.test", "example.org"]}

    # takes effect immediately
    client.post("/api/account/auth/request-link", json={"email": "x@acme.test"})
    assert mailer.sent[-1].to == "x@acme.test"


def test_smtp_password_is_write_only_and_kept_when_omitted(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    body = {
        "host": "mail.test",
        "port": 465,
        "username": "u",
        "password": "s3cret",
        "from_address": "noreply@mail.test",
        "starttls": False,
    }
    r = client.put("/api/account/admin/settings/smtp", json=body, headers=bearer(token))
    assert r.status_code == 200
    assert "password" not in r.json()
    assert r.json() == {k: v for k, v in body.items() if k != "password"}
    assert "s3cret" not in r.text

    r = client.get("/api/account/admin/settings/smtp", headers=bearer(token))
    assert "password" not in r.json() and "s3cret" not in r.text

    # update without password keeps the stored one
    body.pop("password")
    body["port"] = 587
    client.put("/api/account/admin/settings/smtp", json=body, headers=bearer(token))
    assert repo.settings[SETTING_SMTP]["password"] == "s3cret"
    assert repo.settings[SETTING_SMTP]["port"] == 587


def test_smtp_test_mail_goes_to_the_admin(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    r = client.post("/api/account/admin/settings/smtp/test", headers=bearer(token))
    assert r.status_code == 202
    assert r.json() == {"sent_to": "admin@example.org"}
    assert mailer.sent[-1].to == "admin@example.org"

    mailer.fail = True
    r = client.post("/api/account/admin/settings/smtp/test", headers=bearer(token))
    assert r.status_code == 502
    assert r.json()["error"].startswith("SMTP delivery failed")


def test_smtp_test_without_configuration_is_409(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    del repo.settings[SETTING_SMTP]
    r = client.post("/api/account/admin/settings/smtp/test", headers=bearer(token))
    assert r.status_code == 409


def test_admin_users_shape(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    r = client.get("/api/account/admin/users", headers=bearer(token))
    assert r.status_code == 200
    assert set(r.json()[0]) == {
        "id",
        "email",
        "is_admin",
        "created_at",
        "last_login_at",
        "balance_cents",
        "usage_cents",
    }
    assert r.json()[0]["last_login_at"] is not None
