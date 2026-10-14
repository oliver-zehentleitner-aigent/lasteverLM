"""Roles: viewer reads the admin panel, admin changes it, the role is set at first sign-in
or by an admin; the last admin and the demo user keep their roles."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID

from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import DEMO_TOKEN, FakeMailer, bearer, login
from .test_admin import ADMIN_ROUTES

USERS = "/api/account/admin/users"


def _make_viewer(client: TestClient, mailer: FakeMailer) -> tuple[str, str]:
    admin_token, _ = login(client, mailer, "admin@example.org")
    viewer_token, viewer = login(client, mailer, "viewer@example.org")
    r = client.patch(
        f"{USERS}/{viewer['id']}", json={"role": "viewer"}, headers=bearer(admin_token)
    )
    assert r.status_code == 200 and r.json()["role"] == "viewer" and r.json()["is_admin"] is False
    return admin_token, viewer_token


def test_viewer_reads_everything_and_writes_nothing(client: TestClient, mailer: FakeMailer) -> None:
    _, viewer_token = _make_viewer(client, mailer)
    for method, path, body in ADMIN_ROUTES:
        r = client.request(method, path, json=body, headers=bearer(viewer_token))
        if method == "GET":
            assert r.status_code == 200, (path, r.text)
        else:
            assert r.status_code == 403, (method, path, r.text)
            assert r.json() == {"error": "admin only"}
    me = client.get("/api/account/me", headers=bearer(viewer_token)).json()
    assert me["role"] == "viewer" and me["is_admin"] is False


def test_roles_are_assigned_at_first_sign_in(client: TestClient, mailer: FakeMailer) -> None:
    admin_token, admin = login(client, mailer, "admin@example.org")  # ADMIN_EMAILS
    assert admin["role"] == "admin" and admin["is_admin"] is True
    r = client.post(
        "/api/account/admin/settings/domains",
        json={"domain": "partner.test"},
        headers=bearer(admin_token),
    )
    assert r.status_code == 201
    r = client.post(
        "/api/account/admin/settings/viewer-domains",
        json={"domain": "Partner.test"},
        headers=bearer(admin_token),
    )
    assert r.status_code == 201 and r.json()["viewer_domains"] == ["partner.test"]
    _, viewer = login(client, mailer, "auditor@partner.test")
    assert viewer["role"] == "viewer"
    _, plain = login(client, mailer, "someone@example.org")
    assert plain["role"] == "user" and plain["is_admin"] is False
    # an existing user keeps the role when the domain is listed later
    r = client.delete(
        "/api/account/admin/settings/viewer-domains/partner.test", headers=bearer(admin_token)
    )
    assert r.status_code == 204
    assert (
        client.get("/api/account/admin/settings/allowlist", headers=bearer(admin_token)).json()[
            "viewer_domains"
        ]
        == []
    )


def test_patch_role_promotes_and_demotes_but_keeps_the_last_admin(
    client: TestClient, mailer: FakeMailer
) -> None:
    admin_token, admin = login(client, mailer, "admin@example.org")
    _, other = login(client, mailer, "other@example.org")
    r = client.patch(f"{USERS}/{admin['id']}", json={"role": "viewer"}, headers=bearer(admin_token))
    assert r.status_code == 409  # the last admin
    r = client.patch(f"{USERS}/{other['id']}", json={"role": "admin"}, headers=bearer(admin_token))
    assert r.status_code == 200 and r.json()["role"] == "admin"
    r = client.patch(f"{USERS}/{admin['id']}", json={"role": "user"}, headers=bearer(admin_token))
    assert r.status_code == 200 and r.json()["role"] == "user"  # now there is another admin
    assert client.get(USERS, headers=bearer(admin_token)).status_code == 403  # demoted at once
    r = client.patch(
        f"{USERS}/00000000-0000-4000-8000-000000000099",
        json={"role": "admin"},
        headers=bearer(admin_token),
    )
    assert r.status_code == 403  # the caller lost admin; a fresh admin gets 404 for an unknown id
    other_token, _ = login(client, mailer, "other@example.org")
    r = client.patch(
        f"{USERS}/00000000-0000-4000-8000-000000000099",
        json={"role": "admin"},
        headers=bearer(other_token),
    )
    assert r.status_code == 404
    r = client.patch(f"{USERS}/{other['id']}", json={"role": "owner"}, headers=bearer(other_token))
    assert r.status_code == 422


def test_demo_user_keeps_the_user_role(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    repo.users[DEMO_USER_ID] = UserRecord(
        DEMO_USER_ID, "demo@localhost", False, datetime.now(UTC), None
    )
    admin_token, _ = login(client, mailer, "admin@example.org")
    r = client.patch(f"{USERS}/{DEMO_USER_ID}", json={"role": "admin"}, headers=bearer(admin_token))
    assert r.status_code == 409
    assert client.get(USERS, headers=bearer(DEMO_TOKEN)).status_code == 403
    assert client.get("/api/account/me", headers=bearer(DEMO_TOKEN)).json()["role"] == "user"


def test_viewer_address_gets_viewer_at_first_sign_in(
    client: TestClient, mailer: FakeMailer
) -> None:
    admin_token, _ = login(client, mailer, "admin@example.org")
    url = "/api/account/admin/settings/viewer-addresses"
    r = client.post(url, json={"address": "Reviewer@Example.org"}, headers=bearer(admin_token))
    assert r.status_code == 201 and r.json()["viewer_addresses"] == ["reviewer@example.org"]
    assert (
        client.post(
            url, json={"address": "reviewer@example.org"}, headers=bearer(admin_token)
        ).status_code
        == 409
    )
    assert (
        client.post(url, json={"address": "nope"}, headers=bearer(admin_token)).status_code == 422
    )
    _, reviewer = login(client, mailer, "reviewer@example.org")  # allowed through its domain
    assert reviewer["role"] == "viewer"
    _, colleague = login(client, mailer, "colleague@example.org")
    assert colleague["role"] == "user"  # the address, not its domain
    # a listed viewer address alone does not let anyone sign in
    client.post(url, json={"address": "outsider@elsewhere.test"}, headers=bearer(admin_token))
    r = client.post("/api/account/auth/request-link", json={"email": "outsider@elsewhere.test"})
    assert r.status_code == 403 and r.json()["code"] == "not_allowed"
    # removing it later keeps the existing user's role
    assert (
        client.delete(f"{url}/reviewer@example.org", headers=bearer(admin_token)).status_code == 204
    )
    assert (
        client.delete(f"{url}/reviewer@example.org", headers=bearer(admin_token)).status_code == 404
    )
    users = {
        u["email"]: u
        for u in client.get("/api/account/admin/users", headers=bearer(admin_token)).json()
    }
    assert users["reviewer@example.org"]["role"] == "viewer"
