"""A job runs once: its claim is kept fresh while it runs, a worker that lost
the claim to a takeover discards what it made, and generated sources no output
points at are found (and, when switched on, deleted) after an hour."""

import json
import logging
import time
from datetime import UTC, datetime, timedelta

from lasteverlm_rag.orphans import UNLINKED, orphan_counts
from lasteverlm_rag.worker import Worker

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, chunk, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
REPORT = json.dumps({"title": "Sky report", "markdown": "The sky is blue. [1]"})


def claimed(settings, *replies):
    """A report job claimed by worker w1, not run yet."""
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    client = make_client(
        settings, store, FakeRetriever([chunk(1, "The sky is blue.")]), FakeLLM(*replies)
    )
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    job = store.claim_output("w1", 600)
    assert job is not None and job.id == output_id
    return store, client.worker._outputs, job


def generated(store):
    return [s for s in store.sources.values() if s["kind"] == "generated"]


def take_over_while_indexing(store, by="w2"):
    """Another worker takes the claim while this one indexes."""
    create = store.create_generated_source

    def taken(*args):
        store.outputs[next(iter(store.outputs))]["claimed_by"] = by
        return create(*args)

    store.create_generated_source = taken


# -- the fence --


def test_the_worker_holding_the_claim_writes_the_result(settings):
    store, outputs, job = claimed(settings, REPORT)
    assert outputs.process(job, "w1")
    row = store.outputs[job.id]
    assert row["status"] == "ready" and row["title"] == "Sky report"
    assert [s["id"] for s in generated(store)] == [row["source_id"]]


def test_a_worker_that_lost_the_claim_discards_its_result(settings, caplog):
    store, outputs, job = claimed(settings, REPORT)
    take_over_while_indexing(store)
    with caplog.at_level(logging.WARNING, logger="lasteverlm_rag.service"):
        assert outputs.process(job, "w1")
    row = store.outputs[job.id]
    # the row is the other worker's: nothing of this run on it
    assert row["status"] == "processing" and row["source_id"] is None
    assert row["title"] != "Sky report" and row["claimed_by"] == "w2"
    assert generated(store) == []  # its generated source went with it
    assert "taken over by another worker" in caplog.text


def test_a_failure_after_a_takeover_leaves_the_row_to_the_other_worker(settings):
    store, outputs, job = claimed(settings, "")  # an empty reply: the attempt fails
    store.outputs[job.id]["claimed_by"] = "w2"
    assert outputs.process(job, "w1")
    row = store.outputs[job.id]
    # no release (it would free the other's claim), no error, no attempt booked
    assert row["claimed_by"] == "w2" and row["error"] is None
    assert not row.get("attempt_log") and row["status"] == "processing"


# -- the claim kept fresh --


def test_the_claim_is_refreshed_while_indexing(settings):
    store, outputs, job = claimed(settings, REPORT)
    outputs._beat_interval_s = 0.01
    create = store.create_generated_source
    during: list[int] = []

    def slow(*args):
        before = store.beats.count(job.id)
        time.sleep(0.1)  # a long embedding, say: no model call starts meanwhile
        during.append(store.beats.count(job.id) - before)
        return create(*args)

    store.create_generated_source = slow
    assert outputs.process(job, "w1")
    assert during[0] >= 2
    beats = store.beats.count(job.id)
    time.sleep(0.05)
    assert store.beats.count(job.id) == beats  # the beat ends with the job


# -- orphaned generated sources --


def orphans(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    upload = store.add_source(NOTEBOOK, "old.pdf")
    linked = store.add_source(NOTEBOOK, "Report", kind="generated")
    orphan = store.add_source(NOTEBOOK, "Gone", kind="generated")
    loose = store.add_source("", "Nowhere", kind="generated")
    fresh = store.add_source(NOTEBOOK, "Indexing now", kind="generated")
    for source_id in (upload, linked, orphan, loose):
        store.sources[source_id]["created_at"] = old
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    store.outputs[output_id]["source_id"] = linked
    return store, client, (linked, orphan, loose, fresh)


def test_only_old_generated_sources_no_output_points_at_are_orphans(settings):
    store, client, (linked, orphan, loose, fresh) = orphans(settings)
    found = client.worker._outputs.sweep_orphans(apply=False)
    assert found == sorted(
        [{"id": orphan, "notebook_ids": [NOTEBOOK]}, {"id": loose, "notebook_ids": []}],
        key=lambda r: r["id"],
    )
    assert orphan in store.sources  # a dry run deletes nothing
    assert orphan_counts(store) == {NOTEBOOK: 1, UNLINKED: 1}


def test_the_sweep_deletes_them_only_when_switched_on(settings):
    store, client, (linked, orphan, loose, fresh) = orphans(settings)
    client.worker.purge_if_due()  # the default: off
    assert orphan in store.sources and loose in store.sources
    worker = Worker(store, client.worker._outputs, worker_id="w", orphan_sweep=True)
    worker.purge_if_due()
    assert orphan not in store.sources and loose not in store.sources
    # the output's own and the one being indexed stay
    assert linked in store.sources and fresh in store.sources
