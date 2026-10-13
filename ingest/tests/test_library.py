import hashlib
from uuid import UUID, uuid4

from lasteverlm_core import DEMO_USER_ID

from lasteverlm_ingest.loaders.url import normalize_url
from lasteverlm_ingest.repository import NewLibrarySource

TEXT = b"the same bytes, uploaded twice " * 10


def _notebook(client, title="nb") -> str:
    return client.post("/api/ingest/notebooks", json={"title": title}).json()["id"]


def _upload(client, nb, data=TEXT, name="notes.txt"):
    return client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": (name, data, "text/plain")}
    )


def test_same_bytes_are_stored_and_processed_once(client, repo, storage, embedder, run_queue):
    a, b = _notebook(client, "A"), _notebook(client, "B")
    first = _upload(client, a)
    assert first.status_code == 202
    assert run_queue() == 1
    calls = len(embedder.calls)
    # The same bytes in another notebook, under another name: a new link only.
    second = _upload(client, b, name="copy.txt")
    assert second.status_code == 202
    assert second.json()["library_id"] == first.json()["library_id"]
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["status"] == "ready" and second.json()["name"] == "notes.txt"
    # Again in the first notebook: the existing link, 200, same body shape.
    again = _upload(client, a)
    assert again.status_code == 200 and again.json() == first.json() | {"status": "ready"}
    assert run_queue() == 0 and len(embedder.calls) == calls
    assert len(storage.objects) == 1 and len(repo.library) == 1
    [entry] = client.get("/api/ingest/library").json()
    assert [(n["title"], n["source_id"]) for n in entry["notebooks"]] == [
        ("A", first.json()["id"]),
        ("B", second.json()["id"]),
    ]


def test_add_from_library_and_detach(client, repo, run_queue):
    a, b = _notebook(client, "A"), _notebook(client, "B")
    lib = _upload(client, a).json()["library_id"]
    run_queue()
    url = f"/api/ingest/notebooks/{b}/sources"
    added = client.post(url, json={"library_id": lib})
    assert added.status_code == 202 and added.json()["notebook_id"] == b
    assert client.post(url, json={"library_id": lib}).status_code == 200
    assert client.post(url, json={"library_id": str(uuid4())}).status_code == 404
    assert client.post(url, json={"url": "https://x.org", "library_id": lib}).status_code == 400
    assert client.delete(f"/api/ingest/sources/{added.json()['id']}").status_code == 204
    [entry] = client.get("/api/ingest/library").json()
    assert [n["title"] for n in entry["notebooks"]] == ["A"]
    assert UUID(lib) in repo.chunks


def test_delete_from_library_removes_it_everywhere(client, repo, storage, run_queue):
    a, b = _notebook(client, "A"), _notebook(client, "B")
    lib = _upload(client, a).json()["library_id"]
    client.post(f"/api/ingest/notebooks/{b}/sources", json={"library_id": lib})
    run_queue()
    assert client.get(f"/api/ingest/library/{lib}").json()["status"] == "ready"
    assert client.delete(f"/api/ingest/library/{lib}").status_code == 204
    assert client.get(f"/api/ingest/library/{lib}").status_code == 404
    assert client.delete(f"/api/ingest/library/{lib}").status_code == 404
    for nb in (a, b):
        assert client.get(f"/api/ingest/notebooks/{nb}/sources").json() == []
    assert storage.objects == {} and repo.chunks == {} and repo.library == {}


def test_generated_sources_never_appear_in_the_library(client, repo):
    nb = _notebook(client)
    generated = repo.add_source(UUID(nb), "Report", "generated", None, dedupe_key="g")
    lib = generated.library_id
    assert client.get("/api/ingest/library").json() == []
    assert client.get(f"/api/ingest/library/{lib}").status_code == 404
    assert client.delete(f"/api/ingest/library/{lib}").status_code == 404
    other = _notebook(client, "other")
    r = client.post(f"/api/ingest/notebooks/{other}/sources", json={"library_id": str(lib)})
    assert r.status_code == 404
    assert repo.find_library_source(DEMO_USER_ID, "g") is None
    # Still a source of its own notebook, and never claimed by the worker.
    assert [s["kind"] for s in client.get(f"/api/ingest/notebooks/{nb}/sources").json()] == [
        "generated"
    ]
    assert repo.claim_library_source("w", 600) is None


def test_users_never_share_a_library_source(client, repo, storage):
    theirs = repo.create_notebook(uuid4(), "theirs")
    their_lib = repo.create_library_source(
        NewLibrarySource(
            id=uuid4(),
            owner=repo.notebooks[theirs.id][0],
            name="notes.txt",
            kind="text",
            dedupe_key="sha256:" + hashlib.sha256(TEXT).hexdigest(),
            url=None,
            size_bytes=len(TEXT),
            storage_path="k",
        )
    )
    nb = _notebook(client)
    mine = _upload(client, nb)
    assert mine.status_code == 202 and mine.json()["library_id"] != str(their_lib.id)
    assert client.get(f"/api/ingest/library/{their_lib.id}").status_code == 404
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"library_id": str(their_lib.id)})
    assert r.status_code == 404
    assert [e["id"] for e in client.get("/api/ingest/library").json()] == [
        mine.json()["library_id"]
    ]


def test_a_failed_source_uploaded_again_is_retried(client, repo, run_queue):
    nb = _notebook(client)
    r = _upload(client, nb, data=b"   \n  ", name="blank.txt")
    run_queue()
    lib = UUID(r.json()["library_id"])
    assert repo.library[lib].status == "failed"
    again = _upload(client, nb, data=b"   \n  ", name="blank.txt")
    assert again.status_code == 200 and again.json()["status"] == "processing"
    assert repo.library[lib].attempts == 0 and repo.pending() == 1


def test_the_same_url_is_entered_once(client, repo, storage):
    a, b = _notebook(client, "A"), _notebook(client, "B")
    first = client.post(
        f"/api/ingest/notebooks/{a}/sources", json={"url": "HTTPS://Example.org:443/x?q=1#top"}
    )
    second = client.post(
        f"/api/ingest/notebooks/{b}/sources", json={"url": "https://example.org/x?q=1"}
    )
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["library_id"] == second.json()["library_id"]
    [entry] = client.get("/api/ingest/library").json()
    assert entry["kind"] == "url" and entry["size_bytes"] is None
    assert entry["url"] == "https://Example.org:443/x?q=1#top"
    assert len(storage.objects) == 1


def test_normalize_url():
    assert normalize_url("HTTP://Example.ORG:80") == "http://example.org/"
    assert normalize_url("https://example.org:8443/a/B?x=Y#f") == "https://example.org:8443/a/B?x=Y"
    assert normalize_url("http://[::1]:8080/") == "http://[::1]:8080/"
