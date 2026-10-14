"""A viewer sees IP addresses shortened (IPv4 without its last octet, IPv6 to its /48); an
admin sees them in full; nothing keyed by a full IP is open to a viewer."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.masking import mask_ip
from lasteverlm_account.repository import (
    AccessRecord,
    BanRecord,
    BlockRecord,
    LoginAttemptRecord,
)
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import Clock, FakeMailer, bearer, login

A = "/api/account/admin"
V4 = "203.0.113.7"
V6 = "2a05:f480:1800:abcd:1234::9"
PREFIX = "2001:db8:1:2::/64"  # an IPv6 ban key


@pytest.mark.parametrize(
    ("value", "masked"),
    [
        (V4, "203.0.113.*"),
        (V6, "2a05:f480:1800::*"),
        ("2001:db8::1", "2001:db8:0::*"),  # compressed
        ("::ffff:203.0.113.5", "203.0.113.*"),  # v4-mapped
        (PREFIX, "2001:db8:1::*"),
        ("unknown", "*"),
        ("", "*"),
        ("203.0.113", "*"),
        ("testclient", "*"),
    ],
)
def test_mask_ip(value: str, masked: str) -> None:
    assert mask_ip(value) == masked


@pytest.fixture
def tokens(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> dict[str, str]:
    admin_token, _ = login(client, mailer, "admin@example.org")
    _, viewer = login(client, mailer, "viewer@example.org")
    r = client.patch(
        f"{A}/users/{viewer['id']}", json={"role": "viewer"}, headers=bearer(admin_token)
    )
    assert r.status_code == 200
    viewer_token, _ = login(client, mailer, "viewer@example.org")
    now = clock.now
    repo.login_attempts.append(LoginAttemptRecord(now, "x@example.org", V4, "refused"))
    repo.blocks.append(BlockRecord(V6, now + timedelta(minutes=10), 1, now))
    repo.ip_bans += [BanRecord(V4, "third block", now, None), BanRecord(PREFIX, "v6", now, None)]
    repo.access.append(AccessRecord(now, V6, "GET", "/x", 200, None, "account"))
    return {"admin": admin_token, "viewer": viewer_token}


# endpoint -> (full values an admin sees, the masked values a viewer sees)
ENDPOINTS = {
    "/login-attempts": ((V4,), ("203.0.113.*",)),
    "/blocks": ((V6,), ("2a05:f480:1800::*",)),
    "/bans": ((V4, PREFIX), ("203.0.113.*", "2001:db8:1::*")),
    "/access": ((V6,), ("2a05:f480:1800::*",)),
}


@pytest.mark.parametrize("path", list(ENDPOINTS))
def test_viewer_gets_shortened_ips_admin_full(
    client: TestClient, tokens: dict[str, str], path: str
) -> None:
    full, masked = ENDPOINTS[path]
    as_admin = client.get(f"{A}{path}", headers=bearer(tokens["admin"])).json()
    as_viewer = client.get(f"{A}{path}", headers=bearer(tokens["viewer"])).json()
    admin_ips = {row["ip"] for row in as_admin}
    viewer_ips = {row["ip"] for row in as_viewer}
    assert set(full) <= admin_ips, path
    assert set(masked) <= viewer_ips and not admin_ips & viewer_ips, path


def test_viewer_cannot_lift_a_ban(
    client: TestClient, tokens: dict[str, str], repo: MemoryRepository
) -> None:
    h = bearer(tokens["viewer"])
    assert client.delete(f"{A}/bans", params={"ip": V4}, headers=h).status_code == 403
    assert client.delete(f"{A}/bans", params={"ip": PREFIX}, headers=h).status_code == 403
    assert client.delete(f"{A}/bans/{V4}", headers=h).status_code == 403
    assert all(b.lifted_at is None for b in repo.ip_bans)
