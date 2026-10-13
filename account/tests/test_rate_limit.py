"""Core's rate-limit middleware as mounted by this service: outermost, per client IP."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import MemoryRateLimitStore, RateLimitSettings

from lasteverlm_account.repository import AccessRecord, BanRecord, BlockRecord
from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import AccountService

from .conftest import Clock, FakeMailer, bearer, login

FORWARDED = {"X-Forwarded-For": "203.0.113.50"}


def test_every_request_is_logged_with_service_and_user(
    client: TestClient, mailer: FakeMailer, limiter_store: MemoryRateLimitStore
) -> None:
    token, user = login(client, mailer, "alice@example.org")
    client.get("/api/account/me", headers={**bearer(token), **FORWARDED})
    entry = limiter_store.entries[-1]
    assert entry.service == "account"
    assert entry.path == "/api/account/me" and entry.method == "GET" and entry.status == 200
    assert str(entry.user_id) == user["id"]
    assert entry.ip == "203.0.113.50"


def test_banned_address_gets_403_before_any_route(
    client: TestClient, limiter_store: MemoryRateLimitStore
) -> None:
    limiter_store.bans["203.0.113.50"] = "third block in 24h"
    r = client.get("/api/account/healthz", headers=FORWARDED)
    assert r.status_code == 403
    r = client.get("/api/account/healthz")  # another address is unaffected
    assert r.status_code == 200


@pytest.mark.parametrize("rate_limit_settings", [RateLimitSettings(per_minute=3)])
def test_over_the_limit_means_429_and_a_block(
    client: TestClient, limiter_store: MemoryRateLimitStore, rate_limit_settings: RateLimitSettings
) -> None:
    # /healthz rows are sampled, so the window is measured on a normal route (401 counts).
    statuses = [client.get("/api/account/me", headers=FORWARDED).status_code for _ in range(5)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]
    assert "203.0.113.50" in limiter_store.blocks
    assert client.get("/api/account/me").status_code == 401  # another address is unaffected


@pytest.mark.anyio
async def test_startup_purges_core_tables_but_keeps_active_bans(
    service: AccountService, repo: MemoryRepository, clock: Clock
) -> None:
    old = clock.now - timedelta(days=31)
    fresh = clock.now - timedelta(days=29)
    for at in (old, fresh):
        repo.access.append(AccessRecord(at, "203.0.113.1", "GET", "/", 200, None, "account"))
        repo.blocks.append(BlockRecord("203.0.113.1", at, 1, at))
        repo.ip_bans.append(BanRecord("203.0.113.1", "lifted", at, at))
    repo.ip_bans.append(BanRecord("203.0.113.9", "active", old, None))
    repo.ip_bans.append(BanRecord("203.0.113.8", "expired", clock.now - timedelta(days=91), None))
    await service.startup()
    assert [a.at for a in repo.access] == [fresh]
    assert [b.updated_at for b in repo.blocks] == [fresh]
    # a ban holds until an admin lifts it, at most BAN_MAX_DAYS (90)
    assert [(b.reason, b.lifted_at) for b in repo.ip_bans] == [("lifted", fresh), ("active", None)]
