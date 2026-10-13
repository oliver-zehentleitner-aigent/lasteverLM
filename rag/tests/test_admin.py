from lasteverlm_rag.admin import admin_stats

from .conftest import NOTEBOOK, FakeStore


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
    store.insert_message(NOTEBOOK, "user", "hi", [])

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
