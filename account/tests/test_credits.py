"""Vouchers and balance: single use, atomic under concurrency, ledger minus usage."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from lasteverlm_account.repository_memory import MemoryRepository
from lasteverlm_account.service import (
    AccountError,
    AccountService,
    generate_voucher_code,
    hash_secret,
    normalize_voucher_code,
)

from .conftest import FakeMailer, bearer, login

REDEEM = "/api/account/vouchers/redeem"
VOUCHERS = "/api/account/admin/vouchers"


def test_voucher_code_format_and_normalization() -> None:
    code = generate_voucher_code()
    assert len(code) == 19 and code.count("-") == 3
    assert normalize_voucher_code(code.lower().replace("-", " ")) == code.replace("-", "")
    assert normalize_voucher_code("") == ""


def test_redeem_credits_balance_once(client: TestClient, mailer: FakeMailer) -> None:
    admin_token, _ = login(client, mailer, "admin@example.org")
    user_token, _ = login(client, mailer, "user@example.org")

    r = client.post(
        VOUCHERS,
        json={"amount_cents": 500, "count": 2},
        headers=bearer(admin_token),
    )
    assert r.status_code == 201
    codes = r.json()["codes"]
    assert len(codes) == 2 and codes[0] != codes[1]

    r = client.post(REDEEM, json={"code": codes[0]}, headers=bearer(user_token))
    assert r.status_code == 200
    assert r.json()["balance_cents"] == 500

    # second attempt on the same code, by anyone, fails and changes nothing
    r = client.post(REDEEM, json={"code": codes[0]}, headers=bearer(admin_token))
    assert r.status_code == 404
    assert r.json() == {"error": "unknown or already redeemed voucher"}
    assert client.get("/api/account/me", headers=bearer(user_token)).json()["balance_cents"] == 500

    # case and separators do not matter
    r = client.post(
        REDEEM,
        json={"code": codes[1].lower().replace("-", "")},
        headers=bearer(user_token),
    )
    assert r.status_code == 200
    assert r.json()["balance_cents"] == 1000


def test_default_amount_from_settings(client: TestClient, mailer: FakeMailer) -> None:
    admin_token, _ = login(client, mailer, "admin@example.org")
    code = client.post(VOUCHERS, json={}, headers=bearer(admin_token)).json()["codes"][0]
    r = client.post(REDEEM, json={"code": code}, headers=bearer(admin_token))
    assert r.json()["balance_cents"] == 1000  # voucher_default_cents


def test_unknown_or_empty_code(client: TestClient, mailer: FakeMailer) -> None:
    token, _ = login(client, mailer, "user@example.org")
    assert client.post(REDEEM, json={"code": "NOPE"}, headers=bearer(token)).status_code == 404
    assert client.post(REDEEM, json={"code": "---"}, headers=bearer(token)).status_code == 404
    assert client.post(REDEEM, json={"code": ""}, headers=bearer(token)).status_code == 422


def test_balance_is_ledger_minus_usage(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository
) -> None:
    token, user = login(client, mailer, "user@example.org")
    user_id = uuid.UUID(user["id"])
    code = client.post(VOUCHERS, json={"amount_cents": 1000}, headers=bearer(token)).json()[
        "codes"
    ][0]
    client.post(REDEEM, json={"code": code}, headers=bearer(token))
    repo.usage_cost_cents[user_id] = 350  # written by ingest/rag in the real system

    assert client.get("/api/account/me", headers=bearer(token)).json()["balance_cents"] == 650
    users = client.get("/api/account/admin/users", headers=bearer(token)).json()
    assert users[0]["balance_cents"] == 650 and users[0]["usage_cents"] == 350


@pytest.mark.anyio
async def test_concurrent_redeem_of_one_code_credits_exactly_once(
    service: AccountService, repo: MemoryRepository
) -> None:
    now = datetime.now(UTC)
    admin = await repo.create_user("admin@example.org", admin=True, now=now)
    users = [await repo.create_user(f"u{i}@example.org", admin=False, now=now) for i in range(10)]
    code = generate_voucher_code()
    await repo.create_voucher(hash_secret(normalize_voucher_code(code)), 700, admin.id, now)

    results = await asyncio.gather(
        *(service.redeem(u.id, code) for u in users), return_exceptions=True
    )
    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, AccountError)]
    assert len(winners) == 1 and len(losers) == 9
    assert winners[0].balance_cents == 700
    assert sum(e.amount_cents for e in repo.ledger) == 700
    totals = await repo.all_credit_totals()
    assert sum(t.balance_cents for t in totals.values()) == 700
