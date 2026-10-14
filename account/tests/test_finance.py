"""Finance part 2: balance on charge, pricing rules with preview, costs, revenue, profit."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, PRICING_SETTINGS_KEY

from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository, _Usage

from .conftest import Clock, FakeMailer, bearer, login

PRICING = "/api/account/admin/settings/pricing"


def _use(
    repo: MemoryRepository, user: str, at: datetime, cost: str, charge: str, **kw: object
) -> None:
    repo.usage.append(
        _Usage(uuid.UUID(user), Decimal(cost), at, charge_cents=Decimal(charge), **kw)  # type: ignore[arg-type]
    )


def test_balance_is_credit_minus_charge_rounded_down(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    code = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 1000}, headers=bearer(token)
    ).json()["codes"][0]
    client.post("/api/account/vouchers/redeem", json={"code": code}, headers=bearer(token))
    _use(repo, admin["id"], clock.now, "10", "12.4")  # cost 10, charged 12.4
    me = client.get("/api/account/me", headers=bearer(token)).json()
    assert me["balance_cents"] == 987  # 1000 - 12.4, floored
    row = client.get("/api/account/admin/users", headers=bearer(token)).json()[0]
    assert row["usage_cents"] == 13 and row["balance_cents"] == 987


def test_pricing_rules_validate_store_preview_and_reset(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    _use(repo, admin["id"], clock.now, "3", "3", action="chat_answer", action_id=a1)
    _use(repo, admin["id"], clock.now, "1", "1", action="chat_answer", action_id=a1)
    _use(repo, admin["id"], clock.now, "6", "6", action="chat_answer", action_id=a2)
    view = client.get(PRICING, headers=bearer(token)).json()
    assert view["rules"] == {"usd_per_eur": None, "default_margin_pct": 0, "actions": {}}
    assert "chat_answer" in view["actions"]
    row = next(r for r in view["preview"] if r["action"] == "chat_answer")
    assert (row["actions"], row["avg_cost_cents"], row["charge_cents"]) == (2, 5.0, 5.0)

    rules = {
        "usd_per_eur": 1.1188,
        "default_margin_pct": 20,
        "actions": {"chat_answer": {"margin_pct": 50, "fixed_cents": 2}},
    }
    r = client.post(f"{PRICING}/preview", json=rules, headers=bearer(token))
    row = next(x for x in r.json()["preview"] if x["action"] == "chat_answer")
    assert row["charge_cents"] == 5 * 1.5 + 2
    assert PRICING_SETTINGS_KEY not in repo.settings  # preview stores nothing

    r = client.put(PRICING, json=rules, headers=bearer(token))
    assert r.status_code == 200 and repo.settings[PRICING_SETTINGS_KEY] == rules
    summary = next(x for x in r.json()["preview"] if x["action"] == "summary")
    assert summary["margin_pct"] == 20 and summary["charge_cents"] is None  # no data yet

    for bad in (
        {"usd_per_eur": 1.1, "default_margin_pct": 1001, "actions": {}},
        {
            "usd_per_eur": 1.1,
            "default_margin_pct": 0,
            "actions": {"no_such_action": {"margin_pct": 1}},
        },
        {"usd_per_eur": 1.1, "default_margin_pct": 0, "actions": {}, "extra": 1},
        {"default_margin_pct": 0, "actions": {}},  # no rate: core cannot book without one
        {"usd_per_eur": 0, "default_margin_pct": 0, "actions": {}},
    ):
        r = client.put(PRICING, json=bad, headers=bearer(token))
        assert r.status_code == 422, bad
    assert repo.settings[PRICING_SETTINGS_KEY] == rules

    assert client.delete(PRICING, headers=bearer(token)).status_code == 204
    after = client.get(PRICING, headers=bearer(token)).json()["rules"]
    assert after == {"usd_per_eur": 1.1188, "default_margin_pct": 0, "actions": {}}  # rate kept


def test_costs_grouped(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    day = clock.now.date().isoformat()
    _use(
        repo,
        admin["id"],
        clock.now,
        "4",
        "5",
        action="chat_answer",
        model="big",
        service="rag",
        cost_usd_cents=Decimal("4.4752"),
    )
    _use(
        repo, admin["id"], clock.now, "1", "1.5", action="summary", model="small", service="ingest"
    )
    _use(
        repo,
        admin["id"],
        clock.now,
        "0",
        "2",
        action="summary",
        kind="fee",
        model="fee",
        service="ingest",
    )
    url = "/api/account/admin/finance/costs"
    body = client.get(url, params={"group": "action"}, headers=bearer(token)).json()
    assert body["from"] and body["group"] == "action"
    rows = {r["key"]: r for r in body["rows"]}
    assert rows["chat_answer"]["cost_cents"] == 4 and rows["chat_answer"]["charge_cents"] == 5
    assert rows["chat_answer"]["cost_usd_cents"] == 4.4752
    assert rows["summary"]["cost_usd_cents"] == 1  # an old row: its USD cost is its cost
    assert rows["summary"]["calls"] == 1 and rows["summary"]["charge_cents"] == 3.5  # fee row
    assert body["total_cost_cents"] == 5 and body["total_charge_cents"] == 8.5
    for group, key in (
        ("model", "big"),
        ("service", "ingest"),
        ("user", "admin@example.org"),
        ("day", day),
    ):
        keys = [
            r["key"]
            for r in client.get(url, params={"group": group}, headers=bearer(token)).json()["rows"]
        ]
        assert key in keys, group
    assert client.get(url, params={"group": "planet"}, headers=bearer(token)).status_code == 422
    r = client.get(url, params={"from": "2026-10-10", "to": "2026-10-01"}, headers=bearer(token))
    assert r.status_code == 422


def test_revenue(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    repo.users[DEMO_USER_ID] = UserRecord(DEMO_USER_ID, "demo@localhost", False, clock.now, None)
    token, admin = login(client, mailer, "admin@example.org")
    paid = client.post(
        "/api/account/admin/vouchers",
        json={"amount_cents": 2000, "paid": True},
        headers=bearer(token),
    ).json()["codes"][0]
    client.post("/api/account/admin/vouchers", json={"amount_cents": 500}, headers=bearer(token))
    client.post("/api/account/vouchers/redeem", json={"code": paid}, headers=bearer(token))
    _use(repo, admin["id"], clock.now, "100", "150")
    _use(repo, str(DEMO_USER_ID), clock.now, "30", "30")
    body = client.get("/api/account/admin/finance/revenue", headers=bearer(token)).json()
    assert body["vouchers"] == {
        "issued_paid_cents": 2000,
        "issued_free_cents": 500,
        "redeemed_paid_cents": 2000,
        "redeemed_free_cents": 0,
    }
    assert body["charged_cents"] == 150 and body["demo_charged_cents"] == 30
    assert body["outstanding_credit_cents"] == 1850  # admin: 2000 - 150; demo excluded


def test_profit_needs_a_rate_for_usd_infra(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    token, admin = login(client, mailer, "admin@example.org")
    month = clock.now.date().replace(day=1)
    _use(repo, admin["id"], clock.now, "100", "160")
    _use(repo, str(DEMO_USER_ID), clock.now, "40", "40")
    client.post(
        "/api/account/admin/finance/infra",
        json={"date": month.isoformat(), "item": "domain", "amount_cents": 20, "currency": "EUR"},
        headers=bearer(token),
    )
    url = "/api/account/admin/finance/profit"
    params = {"from": month.isoformat(), "to": clock.now.date().isoformat()}
    body = client.get(url, params=params, headers=bearer(token)).json()
    row = body["rows"][-1]
    assert body["group"] == "month" and row["period"] == month.isoformat()
    assert (row["charged_cents"], row["model_cost_cents"], row["infra_cost_cents"]) == (
        160,
        100,
        20,
    )
    assert row["profit_cents"] == 40 and row["demo_charged_cents"] == 40  # demo not counted
    from lasteverlm_account.repository import InfraCostRecord

    repo.infra.append(InfraCostRecord(uuid.uuid4(), month, "vultr", "vke", 1000, "USD"))
    row = client.get(url, params=params, headers=bearer(token)).json()["rows"][-1]
    assert row["infra_cost_cents"] is None and row["profit_cents"] is None  # no rate, no guess
    client.put(
        PRICING,
        json={"usd_per_eur": 1.25, "default_margin_pct": 0, "actions": {}},
        headers=bearer(token),
    )
    body = client.get(url, params=params, headers=bearer(token)).json()
    row = body["rows"][-1]
    assert body["usd_per_eur"] == 1.25
    assert row["infra_cost_cents"] == 20 + 800 and row["profit_cents"] == 160 - 100 - 820
    days = client.get(url, params={**params, "group": "day"}, headers=bearer(token)).json()
    assert len(days["rows"]) == (clock.now.date() - month).days + 1
    assert days["total"]["charged_cents"] == 160


def test_viewer_reads_finance_but_cannot_price(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "admin@example.org")
    _, viewer = login(client, mailer, "v@example.org")
    client.patch(
        f"/api/account/admin/users/{viewer['id']}", json={"role": "viewer"}, headers=bearer(token)
    )
    vtoken, _ = login(client, mailer, "v@example.org")
    for path in (
        PRICING,
        "/api/account/admin/finance/costs",
        "/api/account/admin/finance/revenue",
        "/api/account/admin/finance/profit",
    ):
        assert client.get(path, headers=bearer(vtoken)).status_code == 200, path
    assert (
        client.put(
            PRICING,
            json={"usd_per_eur": 1.1, "default_margin_pct": 1, "actions": {}},
            headers=bearer(vtoken),
        ).status_code
        == 403
    )
    assert client.post(f"{PRICING}/preview", json={}, headers=bearer(vtoken)).status_code == 403
