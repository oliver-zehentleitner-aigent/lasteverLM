import json
from datetime import UTC, datetime, timedelta

from lasteverlm_rag.worker import PURGE_INTERVAL_S, Worker

from .conftest import (
    AUTH,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
LIBRARY = "/api/rag/library/outputs"
REPORT = json.dumps({"title": "Sky report", "markdown": "## Sky\n\nThe sky is blue."})
AUDIO = json.dumps(
    {"title": "The sky, read aloud", "paragraphs": [{"text": "The sky is blue. It is."}]}
)


def ready_output(settings, kind="report", objects=None):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    tts = FakeTTS() if kind == "audio" else None
    llm = FakeLLM(AUDIO if kind == "audio" else REPORT)
    client = make_client(settings, store, FakeRetriever([]), llm, tts, objects)
    output_id = client.post(OUTPUTS, json={"kind": kind}, headers=AUTH).json()["id"]
    client.worker.run_once()
    assert store.outputs[output_id]["status"] == "ready"
    return store, client, output_id


def generated_in_notebook(store):
    return [s["id"] for s in store.sources.values() if s["kind"] == "generated"]


def test_delete_moves_to_the_trash_and_restore_brings_it_back(settings):
    store, client, output_id = ready_output(settings)
    source_id = store.outputs[output_id]["source_id"]
    assert generated_in_notebook(store) == [source_id]

    assert client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH).status_code == 204
    assert client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).status_code == 404
    assert client.get(OUTPUTS, headers=AUTH).json() == []
    assert generated_in_notebook(store) == []  # out of the chat, chunks kept
    assert client.get(LIBRARY, headers=AUTH).json() == []
    (trashed,) = client.get(f"{LIBRARY}?trash=true", headers=AUTH).json()
    assert trashed["id"] == output_id and trashed["deleted_at"] and trashed["purge_at"]
    assert client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH).status_code == 404

    restore = f"/api/rag/outputs/{output_id}/restore"
    assert client.post(restore, headers=AUTH).status_code == 204
    assert client.post(restore, headers=AUTH).status_code == 204  # nothing to do, still fine
    assert generated_in_notebook(store) == [source_id]
    (back,) = client.get(LIBRARY, headers=AUTH).json()
    assert back["deleted_at"] is None and back["purge_at"] is None


def test_purge_needs_the_trash_and_removes_file_source_and_row(settings):
    objects = FakeObjects()
    store, client, output_id = ready_output(settings, "audio", objects)
    source_id = store.outputs[output_id]["source_id"]
    purge = f"/api/rag/outputs/{output_id}/purge"
    r = client.delete(purge, headers=AUTH)
    assert (r.status_code, r.json()) == (409, {"error": "output is not in the trash"})

    client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH)
    objects.fail_delete = True
    (key,) = objects.objects
    r = client.delete(purge, headers=AUTH)
    assert (r.status_code, r.json()) == (502, {"error": f"could not delete stored object {key}"})
    assert output_id in store.outputs and source_id in store.trashed_sources

    objects.fail_delete = False
    assert client.delete(purge, headers=AUTH).status_code == 204
    assert objects.objects == {} and output_id not in store.outputs
    assert source_id not in store.trashed_sources and source_id not in store.chunks
    assert client.delete(purge, headers=AUTH).status_code == 404


def test_an_output_outlives_its_notebook(settings):
    store, client, output_id = ready_output(settings)
    store.delete_notebook(NOTEBOOK)  # ingest's delete, "keep the outputs"

    (row,) = client.get(LIBRARY, headers=AUTH).json()
    assert row["notebook_id"] is None and row["origin_title"] == "My notebook"
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert out["content"]["markdown"] == "## Sky\n\nThe sky is blue."
    # trash and restore work without the notebook; there is nothing to relink
    client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH)
    client.post(f"/api/rag/outputs/{output_id}/restore", headers=AUTH)
    assert store.outputs[output_id]["deleted_at"] is None and store.sources == {}


def test_deleting_a_notebooks_outputs_trashes_each_of_them(settings):
    store, client, output_id = ready_output(settings)
    second = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    assert client.delete(OUTPUTS, headers=AUTH).status_code == 204
    trashed = {o["id"] for o in client.get(f"{LIBRARY}?trash=true", headers=AUTH).json()}
    assert trashed == {output_id, second}
    # a trashed job is never claimed
    assert client.worker.run_once() == 0 and store.outputs[second]["status"] == "processing"
    other = f"/api/rag/notebooks/{OTHER_NOTEBOOK}/outputs"
    assert client.delete(other, headers=AUTH).status_code == 404


def test_the_library_lists_the_callers_outputs_by_kind(settings):
    store, client, output_id = ready_output(settings)
    store.create_output(OTHER_NOTEBOOK, "report", "ready")  # someone else's
    quiz = client.post(OUTPUTS, json={"kind": "quiz"}, headers=AUTH).json()["id"]
    assert [o["id"] for o in client.get(LIBRARY, headers=AUTH).json()] == [quiz, output_id]
    reports = client.get(f"{LIBRARY}?kind=report", headers=AUTH).json()
    assert [o["id"] for o in reports] == [output_id]
    assert client.get(f"{LIBRARY}?kind=poem", headers=AUTH).status_code == 422


def test_an_output_trashed_while_generating_takes_its_new_source_along(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(REPORT))
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    job = store.claim_output("w", 600)
    client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH)

    assert client.worker._outputs.process(job)
    assert generated_in_notebook(store) == []
    assert store.outputs[output_id]["source_id"] in store.trashed_sources


def test_a_job_whose_notebook_is_gone_fails(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(REPORT))
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    store.delete_notebook(NOTEBOOK)
    client.worker.run_once()
    row = store.outputs[output_id]
    assert (row["status"], row["error"]) == ("failed", "the notebook was deleted")


def test_the_worker_purges_expired_trash_at_start_and_then_hourly(settings):
    objects = FakeObjects()
    store, client, output_id = ready_output(settings, "audio", objects)
    client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH)
    now = [0.0]
    worker = Worker(store, client.worker._outputs, worker_id="w", clock=lambda: now[0])

    assert worker.purge_if_due() == 0  # in the trash, not expired yet
    store.outputs[output_id]["deleted_at"] = (
        datetime.now(UTC) - timedelta(days=store.trash_days, seconds=1)
    ).isoformat()
    now[0] = PURGE_INTERVAL_S - 1
    assert worker.purge_if_due() == 0  # not due again before the interval
    objects.fail_delete = True
    now[0] = PURGE_INTERVAL_S
    assert worker.purge_if_due() == 0 and output_id in store.outputs  # loud, kept for later
    objects.fail_delete = False
    now[0] = 2 * PURGE_INTERVAL_S
    assert worker.purge_if_due() == 1
    assert output_id not in store.outputs and objects.objects == {}
