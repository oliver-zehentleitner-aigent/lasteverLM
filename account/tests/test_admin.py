"""Admin gate, domain settings round-trip, read-only SMTP view, test mail."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID

from lasteverlm_account.config import Settings
from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import SETTING_SMTP, AccountError, AccountService

from .conftest import DEMO_TOKEN, Clock, FakeMailer, bearer, login

ADMIN_ROUTES = [
    ("GET", "/api/account/admin/users", None),
    ("PATCH", "/api/account/admin/users/00000000-0000-4000-8000-000000000099", {"role": "viewer"}),
    ("DELETE", "/api/account/admin/users/00000000-0000-4000-8000-000000000099", None),
    ("POST", "/api/account/admin/settings/viewer-domains", {"domain": "x.test"}),
    ("POST", "/api/account/admin/settings/viewer-addresses", {"address": "a@x.test"}),
    ("DELETE", "/api/account/admin/settings/viewer-addresses/a@x.test", None),
    ("DELETE", "/api/account/admin/settings/viewer-domains/x.test", None),
    ("GET", "/api/account/admin/logins", None),
    ("GET", "/api/account/admin/login-attempts", None),
    ("GET", "/api/account/admin/visits", None),
    ("GET", "/api/account/admin/settings/smtp", None),
    ("GET", "/api/account/admin/settings/ratelimit", None),
    ("PUT", "/api/account/admin/settings/ratelimit", {}),
    ("DELETE", "/api/account/admin/settings/ratelimit", None),
    ("GET", "/api/account/admin/settings/allowlist", None),
    ("POST", "/api/account/admin/settings/domains", {"domain": "x.test"}),
    ("DELETE", "/api/account/admin/settings/domains/example.org", None),
    ("POST", "/api/account/admin/settings/addresses", {"address": "a@x.test"}),
    ("DELETE", "/api/account/admin/settings/addresses/a@x.test", None),
    ("POST", "/api/account/admin/vouchers", {}),
    ("GET", "/api/account/admin/vouchers", None),
    ("PATCH", "/api/account/admin/vouchers/00000000-0000-4000-8000-000000000099", {"paid": True}),
    ("GET", "/api/account/admin/finance/infra", None),
    (
        "POST",
        "/api/account/admin/finance/infra",
        {"date": "2026-10-01", "item": "x", "amount_cents": 1},
    ),
    ("DELETE", "/api/account/admin/finance/infra/00000000-0000-4000-8000-000000000099", None),
    ("POST", "/api/account/admin/finance/infra/sync", None),
    ("GET", "/api/account/admin/settings/pricing", None),
    (
        "PUT",
        "/api/account/admin/settings/pricing",
        {"usd_per_eur": 1.1, "default_margin_pct": 0, "actions": {}},
    ),
    (
        "POST",
        "/api/account/admin/settings/pricing/preview",
        {"default_margin_pct": 0, "actions": {}},
    ),
    ("DELETE", "/api/account/admin/settings/pricing", None),
    ("PUT", "/api/account/admin/settings/pricing/rate-mode", {"mode": "manual"}),
    ("POST", "/api/account/admin/settings/pricing/rate/sync", None),
    ("GET", "/api/account/admin/finance/costs", None),
    ("GET", "/api/account/admin/finance/revenue", None),
    ("GET", "/api/account/admin/finance/profit", None),
    ("DELETE", "/api/account/admin/vouchers/00000000-0000-4000-8000-000000000099", None),
    ("GET", "/api/account/admin/stats", None),
    ("GET", "/api/account/admin/system", None),
    ("GET", "/api/account/admin/stats/daily", None),
    ("GET", "/api/account/admin/stats/usage", None),
    ("GET", "/api/account/admin/blocks", None),
    ("GET", "/api/account/admin/bans", None),
    ("DELETE", "/api/account/admin/bans/203.0.113.1", None),
    ("DELETE", "/api/account/admin/bans?ip=2001:db8:1:2::/64", None),
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


def test_allowlist_entries_are_added_and_removed_one_at_a_time(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    h = bearer(token)
    r = client.get("/api/account/admin/settings/allowlist", headers=h)
    assert r.json() == {
        "allowed_domains": ["example.org"],
        "allowed_addresses": [],
        "viewer_domains": [],
        "viewer_addresses": [],
    }

    r = client.post(
        "/api/account/admin/settings/domains", json={"domain": " @Acme.TEST "}, headers=h
    )
    assert r.status_code == 201
    assert r.json()["allowed_domains"] == ["acme.test", "example.org"]
    r = client.post("/api/account/admin/settings/domains", json={"domain": "acme.test"}, headers=h)
    assert r.status_code == 409
    r = client.post(
        "/api/account/admin/settings/domains", json={"domain": "not a domain"}, headers=h
    )
    assert r.status_code == 422

    r = client.post(
        "/api/account/admin/settings/addresses", json={"address": "Guest@Partner.test"}, headers=h
    )
    assert r.status_code == 201
    assert r.json()["allowed_addresses"] == ["guest@partner.test"]
    r = client.post("/api/account/admin/settings/addresses", json={"address": "nope"}, headers=h)
    assert r.status_code == 422

    # both kinds take effect immediately; the address does not open its whole domain
    assert (
        client.post("/api/account/auth/request-link", json={"email": "x@acme.test"}).status_code
        == 202
    )
    assert (
        client.post(
            "/api/account/auth/request-link", json={"email": "guest@partner.test"}
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/api/account/auth/request-link", json={"email": "other@partner.test"}
        ).status_code
        == 403
    )
    assert [m.to for m in mailer.sent[-2:]] == ["x@acme.test", "guest@partner.test"]

    r = client.delete("/api/account/admin/settings/addresses/Guest@partner.test", headers=h)
    assert r.status_code == 204
    r = client.delete("/api/account/admin/settings/addresses/guest@partner.test", headers=h)
    assert r.status_code == 404
    r = client.delete("/api/account/admin/settings/domains/acme.test", headers=h)
    assert r.status_code == 204
    assert client.get("/api/account/admin/settings/domains", headers=h).json() == {
        "allowed_domains": ["example.org"],
        "allowed_addresses": [],
        "viewer_domains": [],
        "viewer_addresses": [],
    }
    assert (
        client.post("/api/account/auth/request-link", json={"email": "x@acme.test"}).status_code
        == 403
    )


def test_smtp_is_read_only_and_shows_the_environment_without_password(
    client: TestClient, mailer: FakeMailer
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    r = client.get("/api/account/admin/settings/smtp", headers=bearer(token))
    assert r.status_code == 200
    assert r.json() == {
        "host": "smtp.test",
        "port": 587,
        "username": "",
        "from_address": "noreply@lasteverlm.test",
        "starttls": True,
    }
    assert "password" not in r.text
    # the configuration is not editable through the API any more
    r = client.put("/api/account/admin/settings/smtp", json={"host": "x"}, headers=bearer(token))
    assert r.status_code == 405


@pytest.mark.anyio
async def test_startup_removes_a_stored_smtp_row(
    service: AccountService, repo: MemoryRepository
) -> None:
    repo.settings[SETTING_SMTP] = {"host": "old.test", "password": "old-secret"}
    await service.startup()
    assert SETTING_SMTP not in repo.settings


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


@pytest.mark.anyio
async def test_smtp_test_without_configuration_is_409(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer
) -> None:
    service = AccountService(replace(settings, smtp=None), repo, mailer)
    with pytest.raises(AccountError) as exc:
        await service.send_test_mail("admin@example.org")
    assert exc.value.status == 409
    assert mailer.sent == []


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
        "granted_cents",
        "role",
    }
    assert r.json()[0]["last_login_at"] is not None


def test_voucher_list_has_no_codes_and_shows_who_redeemed(
    client: TestClient, mailer: FakeMailer, clock: Clock
) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    codes = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 500, "count": 2}, headers=bearer(token)
    ).json()["codes"]
    clock.advance(minutes=1)
    user_token, user = login(client, mailer, "user@example.org")
    client.post("/api/account/vouchers/redeem", json={"code": codes[0]}, headers=bearer(user_token))

    r = client.get("/api/account/admin/vouchers", headers=bearer(token))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert set(rows[0]) == {
        "id",
        "amount_cents",
        "created_by",
        "created_at",
        "redeemed_by",
        "redeemed_at",
        "status",
        "code_masked",
        "recoverable",
        "sent_to",
        "sent_at",
        "paid",
    }
    for code in codes:
        assert code not in r.text
    by_status = {row["status"]: row for row in rows}
    assert by_status["redeemed"]["redeemed_by"] == "user@example.org"
    assert by_status["redeemed"]["redeemed_at"] is not None
    assert by_status["open"]["redeemed_by"] is None and by_status["open"]["redeemed_at"] is None
    assert all(
        row["created_by"] == "admin@example.org" and row["amount_cents"] == 500 for row in rows
    )
    assert client.get("/api/account/admin/vouchers?limit=1", headers=bearer(token)).json()[0]["id"]


def test_stats_overview(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    from lasteverlm_account.repository import BanRecord, BlockRecord
    from lasteverlm_account.repository_memory import _Usage

    # The admin's login is backdated two days, so only one login falls into the 24 h window.
    # (Not via the clock: a one-day token issued two days ago would already be expired.)
    token, admin = login(client, mailer, "admin@example.org")
    repo.logins[0] = replace(repo.logins[0], at=clock.now - timedelta(days=2))
    codes = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 300, "count": 3}, headers=bearer(token)
    ).json()["codes"]
    user_token, user = login(client, mailer, "user@example.org")
    r = client.post(
        "/api/account/vouchers/redeem", json={"code": codes[0]}, headers=bearer(user_token)
    )
    assert r.status_code == 200, r.text
    user_id = uuid.UUID(user["id"])
    repo.usage.append(_Usage(user_id, 120, clock.now - timedelta(hours=30)))
    repo.usage.append(_Usage(user_id, 80, clock.now - timedelta(hours=1)))
    repo.blocks.append(BlockRecord("203.0.113.1", clock.now + timedelta(minutes=5), 1, clock.now))
    repo.blocks.append(BlockRecord("203.0.113.2", clock.now - timedelta(minutes=5), 1, clock.now))
    repo.ip_bans.append(BanRecord("203.0.113.3", "x", clock.now, None))
    repo.ip_bans.append(BanRecord("203.0.113.4", "x", clock.now, clock.now))

    r = client.get("/api/account/admin/stats", headers=bearer(token))
    assert r.status_code == 200
    assert r.json() == {
        "users": 2,  # admin and user (the memory repository has no demo row; a real one counts)
        "logins_24h": 1,
        "vouchers": {"issued": 3, "redeemed": 1, "open": 2},
        "credits_granted_cents": 300,  # the redeemed voucher; no demo seed in the memory repo
        "usage_cost_cents": {"total": 200, "last_24h": 80},
        "blocks_active": 1,
        "bans_active": 1,
    }


def test_ratelimit_rules_are_env_defaults_until_overridden(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    from lasteverlm_core import RATE_LIMIT_SETTINGS_KEY

    token, _ = login(client, mailer, "admin@example.org")
    h = bearer(token)
    url = "/api/account/admin/settings/ratelimit"
    defaults = {
        "per_minute": 120,
        "block_minutes": 15,
        "ban_after_strikes": 3,
        "strike_window_hours": 24,
        "ban_max_days": 90,
        "retention_days": 30,
    }
    assert client.get(url, headers=h).json() == defaults

    body = {"per_minute": 60, "block_minutes": 5, "ban_after_strikes": 2, "strike_window_hours": 12}
    r = client.put(url, json=body, headers=h)
    assert r.status_code == 200
    assert r.json() == {**body, "ban_max_days": 90, "retention_days": 30}
    # stored under core's key, in core's shape (the env cap filled in), read by every service
    assert repo.settings[RATE_LIMIT_SETTINGS_KEY] == {**body, "ban_max_days": 90}
    body = {**body, "ban_max_days": 30}
    r = client.put(url, json=body, headers=h)
    assert r.status_code == 200 and r.json() == {**body, "retention_days": 30}
    assert repo.settings[RATE_LIMIT_SETTINGS_KEY] == body
    for bad in (0, 366):
        r = client.put(url, json={**body, "ban_max_days": bad}, headers=h)
        assert r.status_code == 422 and "ban_max_days" in r.json()["error"]
    # an old four-field row still reads, with the env cap
    repo.settings[RATE_LIMIT_SETTINGS_KEY] = {k: v for k, v in body.items() if k != "ban_max_days"}
    assert client.get(url, headers=h).json()["ban_max_days"] == 90
    repo.settings[RATE_LIMIT_SETTINGS_KEY] = body

    r = client.put(url, json={**body, "per_minute": 0}, headers=h)
    assert r.status_code == 422
    assert "per_minute" in r.json()["error"]
    r = client.put(url, json={**body, "block_minutes": 1441}, headers=h)
    assert r.status_code == 422 and "block_minutes" in r.json()["error"]
    assert repo.settings[RATE_LIMIT_SETTINGS_KEY] == body  # a refused update changes nothing

    repo.settings[RATE_LIMIT_SETTINGS_KEY] = {"per_minute": "lots"}  # malformed by hand
    assert client.get(url, headers=h).json() == defaults

    assert client.delete(url, headers=h).status_code == 204
    assert RATE_LIMIT_SETTINGS_KEY not in repo.settings
    assert client.get(url, headers=h).json() == defaults


def test_daily_stats_have_every_day_oldest_first(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    from lasteverlm_account.repository import VisitRecord
    from lasteverlm_account.repository_memory import _Usage

    token, _ = login(client, mailer, "admin@example.org")
    repo.logins[0] = replace(repo.logins[0], at=clock.now - timedelta(days=2))  # two days ago
    codes = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 400}, headers=bearer(token)
    ).json()["codes"]
    user_token, user = login(client, mailer, "user@example.org")  # one login today
    client.post("/api/account/vouchers/redeem", json={"code": codes[0]}, headers=bearer(user_token))
    today = clock.now
    repo.visits.append(VisitRecord(today - timedelta(days=1), "/", None, "h", "other"))
    repo.visits.append(VisitRecord(today - timedelta(days=1, hours=2), "/x", None, "h2", "other"))
    repo.usage.append(_Usage(uuid.UUID(user["id"]), 70, today))
    repo.usage.append(_Usage(uuid.UUID(user["id"]), 5, today - timedelta(days=40)))  # outside

    r = client.get("/api/account/admin/stats/daily?days=3", headers=bearer(token))
    assert r.status_code == 200
    days = r.json()["days"]
    assert [d["day"] for d in days] == [
        (today - timedelta(days=2)).date().isoformat(),
        (today - timedelta(days=1)).date().isoformat(),
        today.date().isoformat(),
    ]
    assert days[0] == {
        "day": days[0]["day"],
        "logins": 1,
        "visits": 0,
        "usage_cost_cents": 0,
        "credits_granted_cents": 0,
    }
    assert (days[1]["logins"], days[1]["visits"]) == (0, 2)
    assert (days[2]["logins"], days[2]["usage_cost_cents"], days[2]["credits_granted_cents"]) == (
        1,
        70,
        400,
    )
    assert (
        len(client.get("/api/account/admin/stats/daily", headers=bearer(token)).json()["days"])
        == 30
    )


def test_usage_stats_by_model_and_top_users(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    from lasteverlm_account.repository_memory import _Usage

    token, admin = login(client, mailer, "admin@example.org")
    _, user = login(client, mailer, "user@example.org")
    code = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 1000}, headers=bearer(token)
    ).json()["codes"][0]
    u, a = uuid.UUID(user["id"]), uuid.UUID(admin["id"])
    client.post("/api/account/vouchers/redeem", json={"code": code}, headers=bearer(token))
    repo.usage.append(_Usage(u, 300, clock.now, "big-llm", "llm"))
    repo.usage.append(_Usage(u, 100, clock.now, "big-llm", "llm"))
    repo.usage.append(_Usage(a, 50, clock.now, "embed", "embedding"))
    repo.usage.append(_Usage(a, 5, clock.now, "tts-1", "tts"))

    r = client.get("/api/account/admin/stats/usage", headers=bearer(token))
    assert r.status_code == 200
    assert r.json() == {
        "by_model": [
            {"model": "big-llm", "kind": "llm", "calls": 2, "cost_cents": 400},
            {"model": "embed", "kind": "embedding", "calls": 1, "cost_cents": 50},
            {"model": "tts-1", "kind": "tts", "calls": 1, "cost_cents": 5},
        ],
        "top_users": [
            {"email": "user@example.org", "usage_cents": 400, "balance_cents": -400},
            {"email": "admin@example.org", "usage_cents": 55, "balance_cents": 945},
        ],
    }
