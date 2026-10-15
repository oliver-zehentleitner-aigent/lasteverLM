"""Copying a starter notebook's ready outputs into a new user's copy."""

import json
import logging
import uuid

from lasteverlm_rag.starter import OutputCopy, remap_options, remap_provenance

from .conftest import (
    AUTH,
    NOTEBOOK,
    SOURCE_1,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    chunk,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day.")
GRASS = chunk(2, "Grass is green in spring.")
NEW_USER, TARGET = str(uuid.uuid4()), str(uuid.uuid4())
NEW_SOURCE, NEW_CHUNK = str(uuid.uuid4()), str(uuid.uuid4())
REPORT = json.dumps({"title": "Sky", "markdown": "The sky is blue. [1]\n\nGrass is green. [2]"})
AUDIO = json.dumps({"title": "Spoken", "paragraphs": [{"text": "The sky is blue.", "refs": [1]}]})


def starter(settings):
    """The maintainer's notebook with a ready report and audio, a trashed
    table, a job still waiting and a shared report; the new user's copy."""
    store, objects = FakeStore(), FakeObjects()
    upload = store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    llm = FakeLLM(REPORT, AUDIO, '{"title": "t", "columns": ["a"], "rows": [["1"]]}')
    client = make_client(
        settings, store, FakeRetriever([SKY, GRASS]), llm, tts=FakeTTS(), objects=objects
    )
    ids = {}
    for kind in ("report", "audio", "table"):
        ids[kind] = client.post(OUTPUTS, json={"kind": kind}, headers=AUTH).json()["id"]
        client.worker.run_once()
    store.trash_outputs([ids["table"]])
    client.post(f"/api/rag/outputs/{ids['report']}/share", headers=AUTH)
    store.update_output(ids["report"], content={**store.outputs[ids["report"]]["content"]})
    store.outputs[ids["report"]]["content"]["units"][0]["judge"] = {"verdict": "supported"}
    store.add_source(NOTEBOOK, "slow.pdf", status="processing")  # the quiz waits for it
    waiting = client.post(OUTPUTS, json={"kind": "quiz"}, headers=AUTH).json()["id"]
    store.notebooks[TARGET] = {"id": TARGET, "owner": NEW_USER, "title": "Welcome"}
    return store, objects, client, ids, waiting, upload


def queue(store: FakeStore, upload: str) -> None:
    store.copies[TARGET] = {
        "target_notebook": TARGET,
        "source_notebook": NOTEBOOK,
        "owner": NEW_USER,
        # only the first passage's chunk and source exist in the copy
        "source_map": {SOURCE_1: NEW_SOURCE, upload: NEW_SOURCE},
        "chunk_map": {SKY.chunk_id: NEW_CHUNK},
        "attempts": 0,
        "claimed_by": None,
        "error": None,
    }


def copies(store: FakeStore) -> dict[str, dict]:
    return {r["copied_from"]: r for r in store.outputs.values() if r["notebook_id"] == TARGET}


def test_ready_outputs_are_copied_with_their_ids_rewritten_and_nothing_charged(settings):
    store, objects, client, ids, waiting, upload = starter(settings)
    usage_before = len(store.usage)
    queue(store, upload)
    client.worker.run_once()

    copied = copies(store)
    assert set(copied) == {ids["report"], ids["audio"]}  # not the trashed or the waiting one
    report = copied[ids["report"]]
    original = store.outputs[ids["report"]]
    assert (report["owner"], report["origin_title"], report["share_token"]) == (
        NEW_USER,
        "Welcome",
        None,
    )
    assert report["title"] == original["title"] and report["kind"] == "report"
    assert report["content"] == original["content"]  # judge annotations kept
    assert report["content"]["units"][0]["judge"] == {"verdict": "supported"}
    # passages and candidates point into the copy; the unmapped one is dropped
    passages = report["provenance"]["passages"]
    assert [(p["chunk_id"], p["source_id"]) for p in passages] == [(NEW_CHUNK, NEW_SOURCE)]
    candidates = report["provenance"]["retrieval"]["candidates"]
    assert {c["chunk_id"] for c in candidates} == {NEW_CHUNK}
    assert SKY.chunk_id not in json.dumps(report) and GRASS.chunk_id not in json.dumps(report)
    # its generated source and chunks are the copy's own
    source = store.sources[report["source_id"]]
    assert source["notebook_id"] == TARGET and source["kind"] == "generated"
    assert store.chunks[report["source_id"]] == store.chunks[original["source_id"]]

    audio = copied[ids["audio"]]
    key = audio["content"]["key"]
    assert key.startswith(f"{TARGET}/") and key != store.outputs[ids["audio"]]["content"]["key"]
    assert objects.objects[key] == objects.objects[store.outputs[ids["audio"]]["content"]["key"]]

    assert len(store.usage) == usage_before  # no model call, no charge
    assert store.copies == {}
    assert waiting not in copied


def test_a_copy_run_again_adds_nothing(settings):
    store, objects, client, ids, _, upload = starter(settings)
    queue(store, upload)
    client.worker.run_once()
    count, files = len(store.outputs), len(objects.objects)
    queue(store, upload)
    client.worker.run_once()
    assert (len(store.outputs), len(objects.objects)) == (count, files)
    assert store.copies == {}


def test_a_failing_copy_is_retried_then_kept_with_its_error(settings):
    store, objects, client, ids, _, upload = starter(settings)
    objects.objects.clear()  # the starter's audio file is gone
    queue(store, upload)
    for _ in range(3):
        client.worker.run_once()
    row = store.copies[TARGET]
    assert row["attempts"] == 3 and row["error"] is not None
    client.worker.run_once()
    assert store.copies[TARGET]["attempts"] == 3  # failed for good: not claimed again


def test_options_drop_what_cannot_be_mapped():
    job = OutputCopy(TARGET, NOTEBOOK, NEW_USER, {"s1": "n1"}, {"c1": "m1"}, 1)
    options = {
        "sources": ["s1", "s2"],
        "charts": [{"passages": [{"n": 1, "chunk_id": "c1"}, {"n": 2, "chunk_id": "c2"}]}],
    }
    assert remap_options(options, job) == {
        "sources": ["n1"],
        "charts": [{"passages": [{"n": 1, "chunk_id": "m1"}]}],
    }
    assert remap_options({"sources": ["s2"]}, job) == {}
    assert remap_provenance(None, job) is None
    log = {"passages": [{"n": 1, "chunk_id": "c1", "source_id": "s9"}], "judgements": [1]}
    assert remap_provenance(log, job) == {
        "passages": [{"n": 1, "chunk_id": "m1", "source_id": None}],
        "judgements": [1],
    }


def test_the_log_says_how_many_were_copied_and_skipped(settings, caplog):
    store, _, client, _, _, upload = starter(settings)
    caplog.set_level(logging.INFO, logger="lasteverlm_rag.service")
    queue(store, upload)
    client.worker.run_once()
    # the report and the audio; the quiz still waits; the trashed table is not listed
    assert (
        f"starter outputs into notebook {TARGET}: copied 2, skipped 1 not ready, "
        "0 already copied"
    ) in caplog.messages
    queue(store, upload)
    client.worker.run_once()
    assert (
        f"starter outputs into notebook {TARGET}: copied 0, skipped 1 not ready, "
        "2 already copied"
    ) in caplog.messages


def test_a_starter_without_ready_outputs_is_a_warning(settings, caplog):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    store.notebooks[TARGET] = {"id": TARGET, "owner": NEW_USER, "title": "Welcome"}
    queue(store, "unused")
    caplog.set_level(logging.INFO, logger="lasteverlm_rag.service")
    client.worker.run_once()
    (warning,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.getMessage() == (
        f"starter notebook {NOTEBOOK} has no ready outputs: none copied into notebook "
        f"{TARGET} (0 not ready)"
    )
    assert store.copies == {}
