"""Admin view on core's rate-limit tables: blocks, bans, lifting, access log."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from lasteverlm_account.repository import AccessRecord, BanRecord, BlockRecord
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import Clock, FakeMailer, bearer, login


def test_blocks_lists_only_active_ones(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    now = clock.now
    repo.blocks += [
        BlockRecord("203.0.113.1", now + timedelta(minutes=10), 1, now),
        BlockRecord("203.0.113.2", now - timedelta(minutes=1), 2, now - timedelta(minutes=16)),
    ]
    r = client.get("/api/account/admin/blocks", headers=bearer(token))
    assert r.status_code == 200
    assert [b["ip"] for b in r.json()] == ["203.0.113.1"]
    assert set(r.json()[0]) == {"ip", "blocked_until", "strikes", "updated_at"}


def test_bans_default_active_and_lift(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    now = clock.now
    repo.ip_bans += [
        BanRecord("203.0.113.9", "third block in 24h", now - timedelta(hours=1), None),
        BanRecord(
            "203.0.113.8", "third block in 24h", now - timedelta(days=2), now - timedelta(days=1)
        ),
    ]
    r = client.get("/api/account/admin/bans", headers=bearer(token))
    assert [b["ip"] for b in r.json()] == ["203.0.113.9"]
    r = client.get(
        "/api/account/admin/bans", params={"include_lifted": "true"}, headers=bearer(token)
    )
    assert [b["ip"] for b in r.json()] == ["203.0.113.9", "203.0.113.8"]

    r = client.delete("/api/account/admin/bans/203.0.113.9", headers=bearer(token))
    assert r.status_code == 204
    assert client.get("/api/account/admin/bans", headers=bearer(token)).json() == []
    lifted = next(b for b in repo.ip_bans if b.ip == "203.0.113.9")
    assert lifted.lifted_at == now

    r = client.delete("/api/account/admin/bans/203.0.113.9", headers=bearer(token))
    assert r.status_code == 404
    assert r.json() == {"error": "no active ban for this address"}


def test_access_log_newest_first_with_limit(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    user = uuid.uuid4()
    for i in range(5):
        repo.access.append(
            AccessRecord(
                clock.now - timedelta(seconds=i),
                "203.0.113.1",
                "GET",
                f"/p{i}",
                200,
                user if i else None,
                "account",
            )
        )
    r = client.get("/api/account/admin/access", params={"limit": 3}, headers=bearer(token))
    assert r.status_code == 200
    assert [a["path"] for a in r.json()] == ["/p0", "/p1", "/p2"]
    assert r.json()[0]["user_id"] is None and r.json()[1]["user_id"] == str(user)
    assert set(r.json()[0]) == {"at", "ip", "method", "path", "status", "user_id", "service"}
    assert (
        client.get(
            "/api/account/admin/access", params={"limit": 0}, headers=bearer(token)
        ).status_code
        == 422
    )
