"""The exchange rate: the ECB reference rate hourly, a visible failure, a manual override."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import PRICING_SETTINGS_KEY

from lasteverlm_account.ecb import EcbError, EcbRates, parse_usd
from lasteverlm_account.repository_memory import MemoryRepository

from .conftest import Clock, FakeMailer, bearer, login

PRICING = "/api/account/admin/settings/pricing"


def ecb_xml(day: str, usd: str) -> bytes:
    """The structure of the ECB's eurofxref-daily.xml, trimmed."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
 <gesmes:subject>Reference rates</gesmes:subject>
 <Cube><Cube time='{day}'>
  <Cube currency='USD' rate='{usd}'/><Cube currency='JPY' rate='176.91'/>
 </Cube></Cube>
</gesmes:Envelope>""".encode()


class FakeEcb:
    def __init__(self) -> None:
        self.day, self.usd, self.fail = "2026-10-14", "1.1201", False
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.fail:
            return httpx.Response(503)
        return httpx.Response(200, content=ecb_xml(self.day, self.usd))


def connect(client: TestClient, fake: FakeEcb) -> None:
    client.app.state.service.ecb = EcbRates(transport=httpx.MockTransport(fake))  # type: ignore[attr-defined]


def seed(repo: MemoryRepository) -> None:
    repo.settings[PRICING_SETTINGS_KEY] = {
        "usd_per_eur": 1.1188,
        "default_margin_pct": 5,
        "actions": {},
    }


def test_parse_the_ecb_document() -> None:
    assert parse_usd(ecb_xml("2026-10-13", "1.1188")) == (date(2026, 10, 13), Decimal("1.1188"))
    for bad in (b"<html/>", b"not xml", ecb_xml("2026-10-13", "n/a")):
        with pytest.raises(EcbError):
            parse_usd(bad)


def test_sync_writes_a_changed_rate_and_records_its_origin(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    seed(repo)
    token, _ = login(client, mailer, "admin@example.org")
    before = client.get(PRICING, headers=bearer(token)).json()["rate"]
    assert before["source"] == "seed" and before["mode"] == "automatic" and before["stale"] is True
    fake = FakeEcb()
    connect(client, fake)
    r = client.post(f"{PRICING}/rate/sync", headers=bearer(token))
    assert r.status_code == 200
    rate = r.json()["rate"]
    assert rate["usd_per_eur"] == 1.1201 and rate["source"] == "ECB"
    assert (
        rate["rate_date"] == "2026-10-14" and rate["stale"] is False and rate["last_error"] is None
    )
    # margins are untouched, only the rate moved
    assert repo.settings[PRICING_SETTINGS_KEY] == {
        "usd_per_eur": 1.1201,
        "default_margin_pct": 5,
        "actions": {},
    }


def test_failed_fetch_keeps_the_rate_and_shows_it(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    seed(repo)
    token, _ = login(client, mailer, "admin@example.org")
    fake = FakeEcb()
    connect(client, fake)
    client.post(f"{PRICING}/rate/sync", headers=bearer(token))
    fake.fail = True
    clock.advance(days=4)
    rate = client.post(f"{PRICING}/rate/sync", headers=bearer(token)).json()["rate"]
    assert rate["usd_per_eur"] == 1.1201  # kept
    assert rate["last_error"] == "HTTP 503" and rate["stale"] is True  # older than 3 days
    assert rate["last_checked"] > rate["last_success"]


def test_manual_override_pauses_and_automatic_resumes(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    seed(repo)
    token, _ = login(client, mailer, "admin@example.org")
    fake = FakeEcb()
    connect(client, fake)
    r = client.put(
        PRICING,
        json={"usd_per_eur": 1.2, "default_margin_pct": 5, "actions": {}},
        headers=bearer(token),
    )
    rate = r.json()["rate"]
    assert rate["mode"] == "manual" and rate["source"] == "manual" and rate["stale"] is False
    calls = fake.calls
    client.post(f"{PRICING}/rate/sync", headers=bearer(token))
    assert fake.calls == calls and repo.settings[PRICING_SETTINGS_KEY]["usd_per_eur"] == 1.2
    # a PUT that keeps the rate (only margins change) does not switch modes
    r = client.put(f"{PRICING}/rate-mode", json={"mode": "automatic"}, headers=bearer(token))
    assert r.json()["rate"]["mode"] == "automatic" and r.json()["rate"]["usd_per_eur"] == 1.1201
    r = client.put(
        PRICING,
        json={"usd_per_eur": 1.1201, "default_margin_pct": 9, "actions": {}},
        headers=bearer(token),
    )
    assert r.json()["rate"]["mode"] == "automatic"
    assert (
        client.put(
            f"{PRICING}/rate-mode", json={"mode": "sometimes"}, headers=bearer(token)
        ).status_code
        == 422
    )


def test_viewer_sees_the_rate_but_cannot_switch(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    _, viewer = login(client, mailer, "v@example.org")
    client.patch(
        f"/api/account/admin/users/{viewer['id']}", json={"role": "viewer"}, headers=bearer(token)
    )
    vtoken, _ = login(client, mailer, "v@example.org")
    assert "rate" in client.get(PRICING, headers=bearer(vtoken)).json()
    assert (
        client.put(
            f"{PRICING}/rate-mode", json={"mode": "manual"}, headers=bearer(vtoken)
        ).status_code
        == 403
    )
    assert client.post(f"{PRICING}/rate/sync", headers=bearer(vtoken)).status_code == 403


def test_loop_flag_from_env() -> None:
    from lasteverlm_account.config import Settings

    env = {
        "DATABASE_URL": "x",
        "AUTH_JWT_SECRET": "y",
        "PUBLIC_BASE_URL": "https://z",
        "VOUCHER_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    }
    assert Settings.from_env(env).exchange_rate_sync is True
    assert Settings.from_env({**env, "EXCHANGE_RATE_SYNC": "false"}).exchange_rate_sync is False
