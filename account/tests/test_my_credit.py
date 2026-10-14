"""The user's credit page: balance, credits, charged actions with what they were for."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from lasteverlm_account.repository_memory import MemoryRepository, _Usage

from .conftest import Clock, FakeMailer, bearer, login

URL = "/api/account/me/credit"


def use(repo: MemoryRepository, user: str, at, cost: str, charge: str, **kw: object) -> None:  # type: ignore[no-untyped-def]
    repo.usage.append(
        _Usage(uuid.UUID(user), Decimal(cost), at, charge_cents=Decimal(charge), **kw)  # type: ignore[arg-type]
    )


def test_credit_page(
    client: TestClient, mailer: FakeMailer, repo: MemoryRepository, clock: Clock
) -> None:
    admin_token, _ = login(client, mailer, "admin@example.org")
    token, user = login(client, mailer, "alice@example.org")
    code = client.post(
        "/api/account/admin/vouchers", json={"amount_cents": 500}, headers=bearer(admin_token)
    ).json()["codes"][0]
    client.post("/api/account/vouchers/redeem", json={"code": code}, headers=bearer(token))
    nb, out, src, gone = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    repo.notebook_titles[nb] = "Thesis"
    repo.output_titles[out] = "Report on chapter 2"
    repo.source_names[src] = "paper.pdf"
    t = clock.now - timedelta(minutes=10)
    # one output: two model calls and its fee, one action
    use(repo, user["id"], t, "3", "4.5", action="output:report", action_id=out, notebook_id=nb)
    use(repo, user["id"], t, "1", "1.5", action="output:report", action_id=out, notebook_id=nb)
    use(
        repo,
        user["id"],
        t,
        "0",
        "2",
        action="output:report",
        action_id=out,
        notebook_id=nb,
        kind="fee",
    )
    use(repo, user["id"], t + timedelta(minutes=1), "2", "3", action="source:pdf", action_id=src)
    use(
        repo,
        user["id"],
        t + timedelta(minutes=2),
        "1",
        "1",
        action="output:quiz",
        action_id=gone,
        notebook_id=nb,
    )
    models = client.app.state.service.settings.judge_models  # type: ignore[attr-defined]
    use(
        repo,
        user["id"],
        t + timedelta(minutes=3),
        "5",
        "5",
        action="judge",
        action_id=uuid.uuid4(),
        model=models["high"],
    )
    # someone else's charge never shows
    use(repo, str(uuid.uuid4()), t, "9", "9", action="chat_answer", action_id=uuid.uuid4())

    r = client.get(URL, headers=bearer(token))
    assert r.status_code == 200
    body = r.json()
    assert body["balance_cents"] == 500 - 17  # 8 + 3 + 1 + 5 charged
    assert body["granted_cents"] == 500 and body["spent_cents"] == 17
    assert body["total_entries"] == 5
    entries = body["entries"]
    assert [e["type"] for e in entries] == [
        "voucher",
        "charge",
        "charge",
        "charge",
        "charge",
    ]  # newest first
    judge, quiz, pdf, report = entries[1:]
    assert judge["label_key"] == "judge:high" and judge["amount_cents"] == -5
    assert quiz["output"] == {"id": str(gone), "title": None}  # deleted output: title null
    assert pdf["source"] == {"id": str(src), "title": "paper.pdf"} and pdf["output"] is None
    assert report["amount_cents"] == -8 and report["action"] == "output:report"  # fee included
    assert report["notebook"] == {"id": str(nb), "title": "Thesis"}
    assert report["output"]["title"] == "Report on chapter 2"
    by_action = {a["label_key"]: a for a in body["by_action"]}
    assert by_action["output:report"] == {
        "action": "output:report",
        "label_key": "output:report",
        "count": 1,
        "charged_cents": 8.0,
    }
    assert by_action["judge:high"]["count"] == 1
    assert body["by_day"][-1]["charged_cents"] == 17
    for secret in ("cost", "margin", "@"):
        assert secret not in r.text.replace("alice", ""), secret

    page = client.get(URL, params={"limit": 2, "offset": 2}, headers=bearer(token)).json()
    assert [e["action"] for e in page["entries"]] == ["output:quiz", "source:pdf"]
    assert page["total_entries"] == 5
    old = client.get(
        URL, params={"from": "2020-01-01", "to": "2020-01-31"}, headers=bearer(token)
    ).json()
    assert old["entries"] == [] and old["balance_cents"] == 483  # balance is always now
    assert (
        client.get(
            URL, params={"from": "2026-10-10", "to": "2026-10-01"}, headers=bearer(token)
        ).status_code
        == 422
    )
    assert client.get(URL).status_code == 401
