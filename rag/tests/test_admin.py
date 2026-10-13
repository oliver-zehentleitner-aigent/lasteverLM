from datetime import UTC, datetime, timedelta

from lasteverlm_rag.admin import admin_stats

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    OWNER,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    make_client,
)

STATS = "/api/rag/admin/stats"


def test_stats_have_every_key_and_count_jobs_by_claim():
    store = FakeStore()
    empty = admin_stats(store).model_dump()
    assert empty["outputs"]["by_kind"] == dict.fromkeys(
        ["report", "quiz", "table", "mindmap", "infographic", "audio"], 0
    )
    assert empty["outputs"]["by_status"] == dict.fromkeys(
        ["waiting", "processing", "ready", "failed"], 0
    )
    assert empty["jobs"] == {"pending": 0, "running": 0, "failed": 0}
    assert empty["shared"] == {"outputs": 0}

    store.create_output(NOTEBOOK, "quiz", "processing")
    assert store.claim_output("w1", 600) is not None  # the oldest row: the quiz
    store.create_output(NOTEBOOK, "report", "processing")  # not yet claimed
    store.create_output(NOTEBOOK, "audio", "failed")
    ready = store.create_output(NOTEBOOK, "report", "ready")
    store.update_output(ready.id, share_token="t")
    store.insert_message(NOTEBOOK, CONVERSATION, "user", "hi", [])

    stats = admin_stats(store).model_dump()
    assert stats["notebooks"]["total"] == len(store.notebooks)
    assert stats["messages"]["total"] == 1
    assert stats["outputs"]["by_kind"]["report"] == 2
    assert stats["outputs"]["by_kind"]["audio"] == 1
    assert stats["outputs"]["by_status"] == {
        "waiting": 0,
        "processing": 2,
        "ready": 1,
        "failed": 1,
    }
    # the claimed processing row runs; the unclaimed one is pending
    assert stats["jobs"] == {"pending": 1, "running": 1, "failed": 1}
    assert stats["shared"] == {"outputs": 1}


def test_stats_are_read_by_viewers_and_admins_only(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get(STATS).status_code == 401
    for path in (STATS, f"{STATS}/daily"):
        r = client.get(path, headers=AUTH)
        assert (r.status_code, r.json()) == (403, {"error": "admin only"})

    for store in (FakeStore(admins={OWNER}), FakeStore(viewers={OWNER})):
        client = make_client(settings, store, FakeRetriever([]), FakeLLM())
        r = client.get(STATS, headers=AUTH)
        assert r.status_code == 200
        assert set(r.json()) == {"notebooks", "messages", "outputs", "jobs", "shared"}
        assert client.get(f"{STATS}/daily", headers=AUTH).status_code == 200


def test_a_viewer_is_a_user_everywhere_else(settings):
    store = FakeStore(balance=0, viewers={OWNER})
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    r = client.post(f"/api/rag/notebooks/{NOTEBOOK}/outputs", json={"kind": "report"}, headers=AUTH)
    assert (r.status_code, r.json()) == (402, {"error": "credit exhausted"})


def test_an_admin_without_balance_gets_402_like_everyone(settings):
    store = FakeStore(balance=0, admins={OWNER})
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    r = client.post(f"/api/rag/notebooks/{NOTEBOOK}/outputs", json={"kind": "report"}, headers=AUTH)
    assert (r.status_code, r.json()) == (402, {"error": "credit exhausted"})


def test_daily_stats_have_every_day_and_kind(settings):
    store = FakeStore(admins={OWNER})
    today = datetime.now(UTC).date()
    store.daily[(today - timedelta(days=1)).isoformat()] = (4, {"report": 2, "audio": 1})
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())

    days = client.get(f"{STATS}/daily?days=3", headers=AUTH).json()["days"]
    assert [d["day"] for d in days] == [(today - timedelta(days=n)).isoformat() for n in (2, 1, 0)]
    yesterday = days[1]
    assert (yesterday["messages"], yesterday["outputs"]) == (4, 3)
    assert yesterday["outputs_by_kind"] == {
        "report": 2,
        "quiz": 0,
        "table": 0,
        "mindmap": 0,
        "infographic": 0,
        "audio": 1,
    }
    assert days[2]["outputs"] == 0 and sum(days[2]["outputs_by_kind"].values()) == 0
    assert len(client.get(f"{STATS}/daily", headers=AUTH).json()["days"]) == 30
    for bad in ("0", "366", "x"):
        assert client.get(f"{STATS}/daily?days={bad}", headers=AUTH).status_code == 422


def test_daily_stats_are_admin_only(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get(f"{STATS}/daily").status_code == 401
    assert client.get(f"{STATS}/daily", headers=AUTH).status_code == 403
