"""Sources are read when used: added stores, POST /sources/process reads."""

from uuid import UUID, uuid4


def _upload(client, nb, name, data=b"some text"):
    url = f"/api/ingest/notebooks/{nb}/sources"
    return client.post(url, files={"file": (name, data, "text/plain")}).json()["library_id"]


def test_added_sources_are_read_only_when_asked_for(client, repo, run_queue):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    a, b = _upload(client, nb, "a.txt", b"first"), _upload(client, nb, "b.txt", b"second")
    assert repo.claim_library_source("w", 600) is None  # nothing reads them on its own
    r = client.post("/api/ingest/sources/process", json={"library_ids": [a]})
    assert r.status_code == 200 and r.json() == {"queued": [a], "unchanged": []}
    assert repo.claim_library_source("w", 600) == UUID(a)
    assert repo.library[UUID(b)].status == "added"
    # Asking again for one being read, and for both: idempotent.
    r = client.post("/api/ingest/sources/process", json={"library_ids": [a, b, a]})
    assert r.json() == {"queued": [b], "unchanged": [a]}


def test_process_is_all_or_nothing_for_the_callers_sources(client, repo):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    mine = _upload(client, nb, "a.txt")
    theirs = repo.add_source(repo.create_notebook(uuid4(), "x").id, "x", "text", "k").library_id
    unknown = uuid4()
    r = client.post(
        "/api/ingest/sources/process", json={"library_ids": [mine, str(theirs), str(unknown)]}
    )
    assert r.status_code == 404
    assert r.json()["error"] == f"library sources not found: {theirs}, {unknown}"
    assert repo.library[UUID(mine)].status == "added"
    for bad in ([], ["nope"]):
        assert (
            client.post("/api/ingest/sources/process", json={"library_ids": bad}).status_code == 422
        )
