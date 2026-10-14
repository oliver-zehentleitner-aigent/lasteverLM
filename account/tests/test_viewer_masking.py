"""A viewer never receives a full e-mail address from the admin API; an admin still does."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.repository_memory import MemoryRepository, _Usage

from .conftest import Clock, FakeMailer, bearer, login

A = "/api/account/admin"
ADMIN = "admin@example.org"
USER = "alice.user@example.org"
LISTED = "listed.one@outside.test"
WATCHER = "watcher@outside.test"
FRIEND = "friend@outside.test"
STRANGER = "stranger@nowhere.test"

# endpoint -> the addresses an admin sees there (the viewer must see none of them)
ENDPOINTS: dict[str, tuple[str, ...]] = {
    "/users": (ADMIN, USER),
    "/logins": (ADMIN, USER),
    "/login-attempts": (USER, STRANGER),
    "/settings/allowlist": (LISTED, WATCHER),
    "/vouchers": (ADMIN, USER, FRIEND),
    "/finance/costs?group=user": (USER,),
    "/stats/usage": (USER,),
    "/settings/starter-notebook": (ADMIN,),
}
EVERY = (ADMIN, USER, LISTED, WATCHER, FRIEND, STRANGER)


@pytest.fixture
def tokens(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> dict[str, str]:
    admin_token, admin = login(client, mailer, ADMIN)
    h = bearer(admin_token)
    _, viewer = login(client, mailer, "viewer@example.org")
    r = client.patch(f"{A}/users/{viewer['id']}", json={"role": "viewer"}, headers=h)
    assert r.status_code == 200
    viewer_token, _ = login(client, mailer, "viewer@example.org")
    user_token, user = login(client, mailer, USER)
    client.post("/api/account/auth/request-link", json={"email": STRANGER})  # refused
    for path, address in (("addresses", LISTED), ("viewer-addresses", WATCHER)):
        r = client.post(f"{A}/settings/{path}", json={"address": address}, headers=h)
        assert r.status_code == 201, r.text
    codes = client.post(f"{A}/vouchers", json={"count": 2}, headers=h).json()["codes"]
    r = client.post(
        "/api/account/vouchers/redeem", json={"code": codes[0]}, headers=bearer(user_token)
    )
    assert r.status_code == 200, r.text
    open_id = next(
        v["id"] for v in client.get(f"{A}/vouchers", headers=h).json() if v["status"] == "open"
    )
    r = client.post(f"{A}/vouchers/{open_id}/send", json={"email": FRIEND}, headers=h)
    assert r.status_code == 200, r.text
    repo.usage.append(
        _Usage(uuid.UUID(str(user["id"])), Decimal(5), clock.now, charge_cents=Decimal(6))
    )
    nb = uuid.uuid4()
    repo.notebooks[nb] = uuid.UUID(str(admin["id"]))
    repo.sources.append((nb, "ready"))
    r = client.put(f"{A}/settings/starter-notebook", json={"notebook_id": str(nb)}, headers=h)
    assert r.status_code == 200, r.text
    return {"admin": admin_token, "viewer": viewer_token}


@pytest.mark.parametrize("path", list(ENDPOINTS))
def test_viewer_sees_no_full_address(client: TestClient, tokens: dict[str, str], path: str) -> None:
    as_admin = client.get(f"{A}{path}", headers=bearer(tokens["admin"]))
    as_viewer = client.get(f"{A}{path}", headers=bearer(tokens["viewer"]))
    assert as_admin.status_code == as_viewer.status_code == 200
    for address in ENDPOINTS[path]:
        assert address in as_admin.text, (path, address)  # the admin's view is unchanged
    leaked = [a for a in EVERY if a in as_viewer.text]
    assert leaked == [], path
    assert "@" in as_viewer.text  # masked, not dropped: the domain stays


def test_masked_shape(client: TestClient, tokens: dict[str, str]) -> None:
    row = next(
        u
        for u in client.get(f"{A}/users", headers=bearer(tokens["viewer"])).json()
        if u["email"].endswith("@example.org") and u["email"].startswith("a***r")
    )
    assert row["email"] == "a***r@example.org"
    starter = client.get(f"{A}/settings/starter-notebook", headers=bearer(tokens["viewer"])).json()
    assert starter["set_by"] == "a***n@example.org"


def test_finance_keeps_a_gone_users_id(
    client: TestClient, tokens: dict[str, str], repo: MemoryRepository, clock: Clock
) -> None:
    gone = uuid.uuid4()
    repo.usage.append(_Usage(gone, Decimal(1), clock.now, charge_cents=Decimal(1)))
    body = client.get(
        f"{A}/finance/costs", params={"group": "user"}, headers=bearer(tokens["viewer"])
    ).json()
    assert str(gone) in [r["key"] for r in body["rows"]]
