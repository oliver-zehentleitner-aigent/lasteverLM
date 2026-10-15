"""A stopping worker (a deploy's SIGTERM) claims nothing new, lets its running
job finish while its grace allows, and otherwise hands it to another worker
at once, fenced by the claim and without counting the attempt."""

import json
import logging

from lasteverlm_rag.worker import CALL_WORST_S, Worker

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, chunk, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
REPORT = json.dumps({"title": "Sky report", "markdown": "The sky is blue. [1]"})


def setup(settings, *replies):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    llm = FakeLLM(*replies)
    client = make_client(settings, store, FakeRetriever([chunk(1, "The sky is blue.")]), llm)
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    return store, llm, client, output_id


def worker(client, store, worker_id, grace_s):
    return Worker(store, client.worker._outputs, worker_id=worker_id, grace_s=grace_s)


def test_with_the_grace_short_the_job_is_handed_over_at_its_next_step(settings, caplog):
    store, llm, client, output_id = setup(settings, REPORT)
    first = worker(client, store, "w1", grace_s=30)  # less than one call's worst case
    job = store.claim_output("w1", 600)
    first.stop()  # SIGTERM
    with caplog.at_level(logging.WARNING, logger="lasteverlm_rag.service"):
        assert client.worker._outputs.process(job, "w1") is False
    row = store.outputs[output_id]
    assert row["claimed_by"] is None and row["attempts"] == 0  # not counted
    assert row["phase"]["step"] == "handing over" and row["status"] == "processing"
    (record,) = row["attempt_log"]
    assert (record["error_kind"], record["service"]) == ("handover", "rag")
    assert llm.calls == []  # handed over before its first model call
    assert "handed over: the worker is stopping" in caplog.text
    assert first.run_once() == 0  # a stopping worker claims nothing

    # another worker takes it at its next poll and finishes it
    client.worker._outputs._handover_at = None  # a fresh process
    second = worker(client, store, "w2", grace_s=2760)
    assert second.run_once() == 1
    row = store.outputs[output_id]
    assert row["status"] == "ready" and row["attempts"] == 1


def test_with_enough_grace_the_running_job_finishes_on_this_worker(settings):
    store, llm, client, output_id = setup(settings, REPORT)
    first = worker(client, store, "w1", grace_s=CALL_WORST_S + 600)
    job = store.claim_output("w1", 600)
    first.stop()
    assert client.worker._outputs.process(job, "w1") is True
    assert store.outputs[output_id]["status"] == "ready"
    assert not store.outputs[output_id].get("attempt_log")


def test_a_handover_counts_only_while_the_claim_is_held(settings, caplog):
    store, llm, client, output_id = setup(settings, REPORT)
    job = store.claim_output("w1", 600)
    store.outputs[output_id]["claimed_by"] = "w2"  # taken over meanwhile
    client.worker._outputs.hand_over_after(0)
    with caplog.at_level(logging.WARNING, logger="lasteverlm_rag.service"):
        assert client.worker._outputs.process(job, "w1") is False
    row = store.outputs[output_id]
    assert row["claimed_by"] == "w2" and row["attempts"] == 1
    assert not row.get("attempt_log")
    assert (row.get("phase") or {}).get("step") != "handing over"
    assert "was taken over already" in caplog.text
