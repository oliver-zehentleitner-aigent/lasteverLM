"""Infrastructure costs: Vultr billing sync, manual entries, EUR conversion, paid vouchers."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.vultr import VultrBilling, summarize

from .conftest import FakeMailer, bearer, login

INFRA = "/api/account/admin/finance/infra"

PENDING = {
    "pending_charges": [
        {
            "description": "vke-node-1",
            "product": "Kubernetes",
            "start_date": "2026-10-01T00:00:00+00:00",
            "total": 12.34,
        },
        {
            "description": "vke-node-1",
            "product": "Kubernetes",
            "start_date": "2026-10-05T00:00:00+00:00",
            "total": 1.00,
        },
        {
            "description": "postgres",
            "product": "Managed DB",
            "start_date": "2026-10-01T00:00:00+00:00",
            "total": 15.0,
        },
    ]
}
INVOICES = {"billing_invoices": [{"id": 41, "date": "2026-10-01", "amount": 25.5}]}
ITEMS = {
    "invoice_items": [
        {
            "description": "postgres",
            "product": "Managed DB",
            "start_date": "2026-09-01T00:00:00+00:00",
            "total": 15.0,
        },
        {
            "description": "object storage",
            "product": "Storage",
            "start_date": "2026-09-01T00:00:00+00:00",
            "total": 10.5,
        },
    ]
}


class FakeVultr:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.auth: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.auth.append(request.headers.get("authorization", ""))
        if self.fail:
            return httpx.Response(
                401, json={"error": "Unauthorized IP address: 199.247.6.182", "status": 401}
            )
        path = request.url.path
        if path == "/v2/billing/pending-charges":
            return httpx.Response(200, json=PENDING)
        if path == "/v2/billing/invoices":
            return httpx.Response(200, json=INVOICES)
        if path == "/v2/billing/invoices/41/items":
            return httpx.Response(200, json=ITEMS)
        return httpx.Response(404)


def connect(client: TestClient, fake: FakeVultr) -> None:
    client.app.state.service.vultr = VultrBilling(  # type: ignore[attr-defined]
        "secret-key", transport=httpx.MockTransport(fake)
    )


def test_summarize_groups_by_month_and_item() -> None:
    lines = summarize(PENDING["pending_charges"] + ITEMS["invoice_items"])
    got = {(ln.month, ln.item): ln.amount_cents for ln in lines}
    assert got == {
        (date(2026, 10, 1), "vke-node-1"): 1334,
        (date(2026, 10, 1), "postgres"): 1500,
        (date(2026, 9, 1), "postgres"): 1500,
        (date(2026, 9, 1), "object storage"): 1050,
    }
    assert all(ln.currency == "USD" for ln in lines)


def test_not_connected_is_said_and_sync_refuses(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    body = client.get(INFRA, headers=bearer(token)).json()
    assert body["configured"] is False and body["last_success_at"] is None and body["entries"] == []
    r = client.post(f"{INFRA}/sync", headers=bearer(token))
    assert r.status_code == 409 and r.json()["code"] == "vultr_not_connected"


def test_sync_upserts_lines_and_converts_with_the_rate(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    fake = FakeVultr()
    connect(client, fake)
    period = {"from": "2026-09-01", "to": "2026-10-31"}
    r = client.post(f"{INFRA}/sync", headers=bearer(token))
    assert r.status_code == 200
    assert all(a == "Bearer secret-key" for a in fake.auth)
    body = client.get(INFRA, params=period, headers=bearer(token)).json()
    assert body["configured"] is True and body["last_success_at"] and body["last_error"] is None
    assert len(body["entries"]) == 4
    assert body["totals_by_currency"] == {"USD": 1334 + 1500 + 1500 + 1050}
    assert body["usd_per_eur"] is None and body["total_eur_cents"] is None  # no rate: no guess
    assert all(e["amount_eur_cents"] is None for e in body["entries"])
    # a second sync is idempotent
    client.post(f"{INFRA}/sync", headers=bearer(token))
    assert len(repo.infra) == 4
    r = client.put(
        "/api/account/admin/settings/pricing",
        json={"usd_per_eur": 2, "default_margin_pct": 0, "actions": {}},
        headers=bearer(token),
    )
    assert r.status_code == 200
    body = client.get(INFRA, params=period, headers=bearer(token)).json()
    assert body["total_eur_cents"] == round((1334 + 1500 + 1500 + 1050) / 2)
    assert body["usd_per_eur"] == 2
    assert (
        client.put(
            "/api/account/admin/settings/pricing",
            json={"usd_per_eur": 0, "default_margin_pct": 0, "actions": {}},
            headers=bearer(token),
        ).status_code
        == 422
    )


def test_failed_sync_is_kept_and_named(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    connect(client, FakeVultr(fail=True))
    r = client.post(f"{INFRA}/sync", headers=bearer(token))
    assert r.status_code == 502 and r.json()["code"] == "vultr_failed"
    assert "secret-key" not in r.text
    body = client.get(INFRA, headers=bearer(token)).json()
    assert body["configured"] is True and body["last_success_at"] is None
    assert body["last_error"] == (
        "/v2/billing/pending-charges: HTTP 401: Unauthorized IP address: 199.247.6.182"
        " — add this address to Vultr → Account → API → Access Control"
    )
    assert "secret-key" not in body["last_error"]


def test_a_failure_keeps_the_last_success(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    fake = FakeVultr()
    connect(client, fake)
    client.post(f"{INFRA}/sync", headers=bearer(token))
    first = client.get(INFRA, headers=bearer(token)).json()["last_success_at"]
    fake.fail = True
    client.post(f"{INFRA}/sync", headers=bearer(token))
    body = client.get(INFRA, headers=bearer(token)).json()
    assert body["last_success_at"] == first and body["last_error"].startswith(
        "/v2/billing/pending-charges: HTTP 401"
    )
    assert body["last_attempt_at"] >= first


def test_manual_entries(client: TestClient, mailer: FakeMailer, repo: MemoryRepository) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    entry = {"date": "2026-10-01", "item": "domain", "amount_cents": 1200, "currency": "EUR"}
    r = client.post(INFRA, json=entry, headers=bearer(token))
    assert r.status_code == 201 and r.json()["source"] == "manual"
    assert r.json()["amount_eur_cents"] == 1200
    assert client.post(INFRA, json=entry, headers=bearer(token)).status_code == 409
    assert (
        client.post(INFRA, json={**entry, "amount_cents": -1}, headers=bearer(token)).status_code
        == 422
    )
    body = client.get(
        INFRA, params={"from": "2026-10-01", "to": "2026-10-31"}, headers=bearer(token)
    ).json()
    assert body["total_eur_cents"] == 1200
    cid = r.json()["id"]
    assert client.delete(f"{INFRA}/{cid}", headers=bearer(token)).status_code == 204
    assert client.delete(f"{INFRA}/{cid}", headers=bearer(token)).status_code == 404
    connect(client, FakeVultr())
    client.post(f"{INFRA}/sync", headers=bearer(token))
    vultr_id = repo.infra[0].id
    r = client.delete(f"{INFRA}/{vultr_id}", headers=bearer(token))
    assert r.status_code == 409 and r.json()["code"] == "not_manual"


def test_paid_vouchers(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    client.post("/api/account/admin/vouchers", json={"paid": True}, headers=bearer(token))
    rows = client.get("/api/account/admin/vouchers", headers=bearer(token)).json()
    assert rows[0]["paid"] is True
    r = client.patch(
        f"/api/account/admin/vouchers/{rows[0]['id']}", json={"paid": False}, headers=bearer(token)
    )
    assert r.status_code == 200 and r.json()["paid"] is False
    assert (
        client.patch(
            "/api/account/admin/vouchers/00000000-0000-4000-8000-000000000099",
            json={"paid": True},
            headers=bearer(token),
        ).status_code
        == 404
    )


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_key_means_not_connected(raw: str) -> None:
    from lasteverlm_account.config import Settings

    env = {
        "DATABASE_URL": "x",
        "AUTH_JWT_SECRET": "y",
        "PUBLIC_BASE_URL": "https://z",
        "VOUCHER_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "VULTR_BILLING_API_KEY": raw,
    }
    assert Settings.from_env(env).vultr_billing_api_key is None
