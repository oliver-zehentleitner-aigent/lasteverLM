"""Deleting a user: rag and ingest purge first on the admin's bearer, account last; a
failing step leaves the user untouched and names itself."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, MemoryRateLimitStore, RateLimitSettings

from lasteverlm_account.config import Settings
from lasteverlm_account.main import create_app
from lasteverlm_account.repository import UserRecord
from lasteverlm_account.repository_memory import MemoryRepository, _Usage
from lasteverlm_account.services import ServiceClient
from lasteverlm_account.system import SystemProbe

from .conftest import DEMO_TOKEN, FakeMailer, bearer, login

USERS = "/api/account/admin/users"


class Recorder:
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail = fail

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            (request.method, str(request.url), request.headers.get("authorization", ""))
        )
        if request.url.host == self.fail:
            return httpx.Response(500, json={"error": "storage unavailable"})
        return httpx.Response(204)


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def client(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer, recorder: Recorder
) -> TestClient:
    app = create_app(
        settings=settings,
        repository=repo,
        mailer=mailer,
        rate_limit_store=MemoryRateLimitStore(),
        rate_limit_settings=RateLimitSettings(),
        system=SystemProbe([], transport=httpx.MockTransport(recorder)),
        services=ServiceClient(
            ingest_url="http://ingest",
            rag_url="http://rag",
            transport=httpx.MockTransport(recorder),
        ),
    )
    with TestClient(app) as c:
        yield c


def test_delete_purges_rag_then_ingest_then_account(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, recorder: Recorder
) -> None:
    admin_token, admin = login(client, mailer, "admin@example.org")
    user_token, user = login(client, mailer, "gone@example.org")
    uid = uuid.UUID(user["id"])
    code = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 100}, headers=bearer(admin_token)
    ).json()["codes"][0]
    client.post("/api/account/vouchers/redeem", json={"code": code}, headers=bearer(user_token))
    repo.usage.append(_Usage(uid, 7, datetime.now(UTC)))
    client.post("/api/account/visits", json={"path": "/"}, headers=bearer(user_token))

    r = client.delete(f"{USERS}/{uid}", headers=bearer(admin_token))
    assert r.status_code == 204
    assert [(m, u) for m, u, _ in recorder.calls] == [
        ("DELETE", f"http://rag/api/rag/admin/users/{uid}"),
        ("DELETE", f"http://ingest/api/ingest/admin/users/{uid}"),
    ]
    assert all(auth == f"Bearer {admin_token}" for _, _, auth in recorder.calls)
    assert uid not in repo.users
    assert all(e.user_id != uid for e in repo.ledger) and all(u.user_id != uid for u in repo.usage)
    assert all(r.user_id != uid for r in repo.logins)
    assert all(v.user_id != uid for v in repo.visits)
    voucher = next(iter(repo.vouchers.values()))
    assert voucher.redeemed_by is None and voucher.redeemed_at is not None  # history stays
    assert any(a.email == "gone@example.org" for a in repo.login_attempts)
    assert client.get("/api/account/me", headers=bearer(user_token)).status_code == 401
    rows = client.get("/api/account/admin/vouchers", headers=bearer(admin_token)).json()
    assert rows[0]["redeemed_by"] is None and rows[0]["status"] == "redeemed"
    # a repeat is a 404: nothing left to delete
    assert client.delete(f"{USERS}/{uid}", headers=bearer(admin_token)).status_code == 404


@pytest.mark.parametrize("failing", ["rag", "ingest"])
def test_failing_step_stops_and_leaves_the_user(
    settings: Settings, repo: MemoryRepository, mailer: FakeMailer, failing: str
) -> None:
    recorder = Recorder(fail=failing)
    app = create_app(
        settings=settings,
        repository=repo,
        mailer=mailer,
        rate_limit_store=MemoryRateLimitStore(),
        rate_limit_settings=RateLimitSettings(),
        system=SystemProbe([], transport=httpx.MockTransport(recorder)),
        services=ServiceClient(
            ingest_url="http://ingest",
            rag_url="http://rag",
            transport=httpx.MockTransport(recorder),
        ),
    )
    with TestClient(app) as client:
        admin_token, _ = login(client, mailer, "admin@example.org")
        _, user = login(client, mailer, "stays@example.org")
        r = client.delete(f"{USERS}/{user['id']}", headers=bearer(admin_token))
        assert r.status_code == 502
        assert r.json()["code"] == "purge_failed"
        assert r.json()["step"] == failing
        assert r.json()["message"] == "HTTP 500 storage unavailable"
        assert r.json()["error"].startswith(f"{failing} could not purge the user's data: HTTP 500")
        assert "storage unavailable" in r.json()["error"]
        assert uuid.UUID(user["id"]) in repo.users  # nothing of account's was touched
        hosts = [httpx.URL(u).host for _, u, _ in recorder.calls]
        assert hosts == ["rag"] if failing == "rag" else ["rag", "ingest"]
        assert len(client.get(USERS, headers=bearer(admin_token)).json()) == 2


def test_delete_refuses_self_demo_unknown_and_viewers(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, recorder: Recorder
) -> None:
    repo.users[DEMO_USER_ID] = UserRecord(
        DEMO_USER_ID, "demo@localhost", False, datetime.now(UTC), None
    )
    admin_token, admin = login(client, mailer, "admin@example.org")
    assert client.delete(f"{USERS}/{admin['id']}", headers=bearer(admin_token)).status_code == 409
    assert client.delete(f"{USERS}/{DEMO_USER_ID}", headers=bearer(admin_token)).status_code == 409
    assert client.delete(f"{USERS}/{uuid.uuid4()}", headers=bearer(admin_token)).status_code == 404
    assert client.delete(f"{USERS}/{admin['id']}", headers=bearer(DEMO_TOKEN)).status_code == 403
    assert recorder.calls == []  # no service was asked for any of these
