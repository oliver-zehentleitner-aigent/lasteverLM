"""Visitor log: no raw IP, daily salt rotation, user agent family only, retention, admin view."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.privacy import DailySalt, ua_family, visitor_hash
from lasteverlm_account.repository import LoginAttemptRecord, VisitRecord
from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import AccountService

from .conftest import Clock, FakeMailer, bearer, login

VISITS = "/api/account/visits"
ADMIN_VISITS = "/api/account/admin/visits"

CHROME = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def test_daily_salt_rotates_per_day_and_is_random() -> None:
    salt = DailySalt()
    a = salt.for_day(date(2026, 10, 12))
    assert a == salt.for_day(date(2026, 10, 12))
    b = salt.for_day(date(2026, 10, 13))
    assert a != b and len(b) == 32
    assert DailySalt().for_day(date(2026, 10, 12)) != a  # another process, another salt


def test_shared_secret_makes_replicas_agree_and_still_rotates_daily() -> None:
    a, b = DailySalt("shared-secret"), DailySalt("shared-secret")
    today, tomorrow = date(2026, 10, 12), date(2026, 10, 13)
    assert a.shared and a.for_day(today) == b.for_day(today)
    assert a.for_day(today) != a.for_day(tomorrow)
    assert a.for_day(today) != DailySalt("other-secret").for_day(today)
    assert not DailySalt().shared


def test_visitor_hash_is_stable_within_a_day_only() -> None:
    salt = DailySalt()
    today, tomorrow = date(2026, 10, 12), date(2026, 10, 13)
    h1 = visitor_hash("203.0.113.7", salt.for_day(today))
    assert h1 == visitor_hash(" 203.0.113.7 ", salt.for_day(today))
    assert h1 != visitor_hash("203.0.113.8", salt.for_day(today))
    assert h1 != visitor_hash("203.0.113.7", salt.for_day(tomorrow))
    assert "203.0.113.7" not in h1 and len(h1) == 32


@pytest.mark.parametrize(
    ("ua", "family"),
    [
        (CHROME, "chrome"),
        (CHROME + " Edg/130.0", "edge"),
        ("Mozilla/5.0 (Macintosh) Gecko/20100101 Firefox/131.0", "firefox"),
        (
            "Mozilla/5.0 (iPhone) AppleWebKit/605 (KHTML, like Gecko) Version/17 Safari/604.1",
            "safari",
        ),
        ("curl/8.5.0", "bot"),
        ("Googlebot/2.1", "bot"),
        ("", "unknown"),
        (None, "unknown"),
        ("SomethingElse/1.0", "other"),
    ],
)
def test_ua_family(ua: str | None, family: str) -> None:
    assert ua_family(ua) == family


def test_visit_stores_hash_and_family_never_the_ip(
    client: TestClient, repo: MemoryRepository, mailer: FakeMailer
) -> None:
    headers = {"X-Forwarded-For": "203.0.113.7, 10.0.0.2", "User-Agent": CHROME}
    r = client.post(VISITS, json={"path": "/"}, headers=headers)
    assert r.status_code == 204

    token, user = login(client, mailer, "alice@example.org")
    r = client.post(VISITS, json={"path": "/notebooks"}, headers={**headers, **bearer(token)})
    assert r.status_code == 204

    assert len(repo.visits) == 2
    anonymous, signed_in = repo.visits
    assert anonymous.user_id is None and str(signed_in.user_id) == user["id"]
    assert anonymous.ip_hash == signed_in.ip_hash  # same address, same day
    for v in repo.visits:
        assert "203.0.113.7" not in v.ip_hash
        assert v.ua_family == "chrome"
        assert "Mozilla" not in v.ua_family


def test_admin_visits_aggregates_per_day_and_path(
    client: TestClient, mailer: FakeMailer, clock: Clock
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    for ip in ("203.0.113.1", "203.0.113.1", "203.0.113.2"):
        client.post(VISITS, json={"path": "/"}, headers={"X-Forwarded-For": ip})
    client.post(VISITS, json={"path": "/about"}, headers={"X-Forwarded-For": "203.0.113.1"})

    r = client.get(ADMIN_VISITS, params={"days": 7}, headers=bearer(token))
    assert r.status_code == 200
    rows = {row["path"]: row for row in r.json()}
    assert rows["/"] == {"day": "2026-10-12", "path": "/", "visits": 3, "unique": 2}
    assert rows["/about"]["visits"] == 1 and rows["/about"]["unique"] == 1
    assert set(rows["/"]) == {"day", "path", "visits", "unique"}

    clock.advance(days=8)
    assert client.get(ADMIN_VISITS, params={"days": 7}, headers=bearer(token)).json() == []


@pytest.mark.anyio
async def test_startup_applies_retention(
    service: AccountService, repo: MemoryRepository, clock: Clock
) -> None:
    old = clock.now - timedelta(days=31)
    fresh = clock.now - timedelta(days=29)
    for at in (old, fresh):
        await repo.add_visit(VisitRecord(at, "/", None, "h", "other"))
        await repo.add_login_attempt(LoginAttemptRecord(at, "a@b.test", "203.0.113.1", "refused"))
    await service.startup()
    assert [v.at for v in repo.visits] == [fresh]
    assert [a.at for a in repo.login_attempts] == [fresh]


@pytest.mark.anyio
async def test_startup_seeds_settings_only_once(
    service: AccountService, repo: MemoryRepository
) -> None:
    await service.startup()
    assert await service.allowed_domains() == ["example.org"]
    await service.add_allow_entry("domain", "changed.test")
    await service.remove_allow_entry("domain", "example.org")
    await service.startup()  # a restart must not overwrite what an admin changed
    assert await service.allowed_domains() == ["changed.test"]
    assert datetime.now(UTC) is not None
