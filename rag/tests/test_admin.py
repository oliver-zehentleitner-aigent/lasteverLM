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


def test_stats_endpoint_is_admin_only(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get(STATS).status_code == 401
    r = client.get(STATS, headers=AUTH)
    assert (r.status_code, r.json()) == (403, {"error": "admin only"})

    client = make_client(settings, FakeStore(admins={OWNER}), FakeRetriever([]), FakeLLM())
    r = client.get(STATS, headers=AUTH)
    assert r.status_code == 200
    assert set(r.json()) == {"notebooks", "messages", "outputs", "jobs", "shared"}


def test_an_admin_without_balance_still_has_credit(settings):
    store = FakeStore(balance=0, admins={OWNER})
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    assert (
        client.post(
            f"/api/rag/notebooks/{NOTEBOOK}/outputs", json={"kind": "report"}, headers=AUTH
        ).status_code
        == 202
    )
