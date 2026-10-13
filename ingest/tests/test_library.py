import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from lasteverlm_core import DEMO_USER_ID

from lasteverlm_ingest.loaders.url import normalize_url
from lasteverlm_ingest.repository import NewLibrarySource
from lasteverlm_ingest.worker import purge_trash

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


def test_delete_moves_to_the_trash_and_detaches_everywhere(client, repo, storage, run_queue):
    a, b = _notebook(client, "A"), _notebook(client, "B")
    lib = _upload(client, a).json()["library_id"]
    client.post(f"/api/ingest/notebooks/{b}/sources", json={"library_id": lib})
    run_queue()
    assert client.delete(f"/api/ingest/library/{lib}").status_code == 204
    assert client.get(f"/api/ingest/library/{lib}").status_code == 404
    assert client.get("/api/ingest/library").json() == []
    assert client.delete(f"/api/ingest/library/{lib}").status_code == 404
    for nb in (a, b):
        assert client.get(f"/api/ingest/notebooks/{nb}/sources").json() == []
    # In the trash: chunks and object kept, not addable until restored.
    assert UUID(lib) in repo.chunks and len(storage.objects) == 1
    [trashed] = client.get("/api/ingest/library/trash").json()
    assert trashed["id"] == lib and "notebooks" not in trashed
    deleted = datetime.fromisoformat(trashed["deleted_at"])
    assert datetime.fromisoformat(trashed["purge_at"]) - deleted == timedelta(days=14)
    r = client.post(f"/api/ingest/notebooks/{a}/sources", json={"library_id": lib})
    assert r.status_code == 404


def test_restore_brings_it_back_without_notebooks(client, repo, run_queue):
    nb = _notebook(client)
    lib = _upload(client, nb).json()["library_id"]
    run_queue()
    client.delete(f"/api/ingest/library/{lib}")
    assert client.post(f"/api/ingest/library/{lib}/restore").status_code == 204
    assert client.post(f"/api/ingest/library/{lib}/restore").status_code == 404
    [entry] = client.get("/api/ingest/library").json()
    assert entry["id"] == lib and entry["status"] == "ready" and entry["notebooks"] == []
    assert client.get("/api/ingest/library/trash").json() == []
    added = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"library_id": lib})
    assert added.status_code == 202 and added.json()["status"] == "ready"


def test_uploading_trashed_bytes_restores_the_entry(client, repo, embedder, run_queue):
    nb = _notebook(client)
    lib = _upload(client, nb).json()["library_id"]
    run_queue()
    calls = len(embedder.calls)
    client.delete(f"/api/ingest/library/{lib}")
    again = _upload(client, nb)
    assert again.status_code == 202 and again.json()["library_id"] == lib
    assert again.json()["status"] == "ready" and len(repo.library) == 1
    assert client.get("/api/ingest/library/trash").json() == []
    assert run_queue() == 0 and len(embedder.calls) == calls


def test_purge_now_and_after_retention(client, repo, storage, run_queue):
    nb = _notebook(client)
    now_lib = _upload(client, nb, data=b"purge me now").json()["library_id"]
    old_lib = _upload(client, nb, data=b"retention over").json()["library_id"]
    kept = _upload(client, nb, data=b"still in the trash").json()["library_id"]
    run_queue()
    assert client.delete(f"/api/ingest/library/{now_lib}/purge").status_code == 404  # not trashed
    for lib in (now_lib, old_lib, kept):
        client.delete(f"/api/ingest/library/{lib}")
    assert client.delete(f"/api/ingest/library/{now_lib}/purge").status_code == 204
    assert UUID(now_lib) not in repo.library and UUID(now_lib) not in repo.chunks
    repo.trash_days[DEMO_USER_ID] = 3
    when = datetime.now(UTC) - timedelta(days=3, minutes=1)
    repo.library[UUID(old_lib)] = repo.library[UUID(old_lib)].model_copy(
        update={"deleted_at": when}
    )
    deps = SimpleNamespace(repository=repo, storage=storage)
    assert purge_trash(deps) == 1  # type: ignore[arg-type]
    assert [e["id"] for e in client.get("/api/ingest/library/trash").json()] == [kept]
    assert len(storage.objects) == 1 and UUID(kept) in repo.chunks


def test_trashed_sources_are_not_processed(client, repo, run_queue):
    nb = _notebook(client)
    lib = _upload(client, nb).json()["library_id"]
    client.delete(f"/api/ingest/library/{lib}")
    assert run_queue() == 0 and repo.claim_library_source("w", 600) is None
    client.post(f"/api/ingest/library/{lib}/restore")
    assert repo.claim_library_source("w", 600) == UUID(lib)


def test_the_worker_purges_at_start(repo, storage):
    import threading

    from lasteverlm_ingest.worker import run_worker
    from tests.conftest import make_settings

    nb = repo.create_notebook(DEMO_USER_ID, "nb")
    src = repo.add_source(nb.id, "a.txt", "text", "k")
    storage.put("k", b"x", "text/plain")
    repo.set_library_status(src.library_id, "ready")
    repo.trash_library_source(DEMO_USER_ID, src.library_id)
    repo.trash_days[DEMO_USER_ID] = 0
    stop = threading.Event()
    stop.set()  # no source is processed: only the purge at start runs
    deps = SimpleNamespace(repository=repo, storage=storage, settings=make_settings())
    assert run_worker(deps, stop, worker_id="w") == 0  # type: ignore[arg-type]
    assert repo.library == {} and storage.objects == {}


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
