"""A new user's first library access copies the starter notebook."""

from uuid import UUID, uuid4

from lasteverlm_core import DEMO_USER_ID, Chunk, StorageError

from lasteverlm_ingest.repository import StarterRef
from lasteverlm_ingest.starter import ensure_starter
from lasteverlm_ingest.worker import TRANSCRIBED_NAME
from tests.fakes import InMemoryRepository, InMemoryStorage

ADMIN = uuid4()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _starter(repo, storage):
    """The admin's notebook: a PDF, a text, a converted recording, a URL,
    one still processing, one trashed, and an output (rag's)."""
    nb = repo.create_notebook(ADMIN, "Getting started with lasteverLM")
    made = {}
    for name, kind, data in (
        ("handbook.pdf", "pdf", b"%PDF-1.4"),
        ("faq.txt", "text", b"questions"),
        ("shot.png", "image", PNG),
        ("talk.m4a", "audio", b"\x00\x00\x00\x20ftypM4A "),
        ("https://x.test/prices", "url", b"https://x.test/prices"),
    ):
        key = f"{ADMIN}/{name}"
        storage.put(key, data, "x/original")
        lib = repo.add_source(nb.id, name, kind, key).library_id
        repo.set_library_status(lib, "ready")
        repo.set_library_summary(lib, f"summary of {name}")
        repo.replace_chunks(lib, [Chunk(idx=0, text=name, page=1)], [[1.0, 0.0]])
        made[name] = lib
    storage.put(f"{ADMIN}/converted", b"ID3mp3", "audio/mpeg")
    repo.set_transcribed_path(made["talk.m4a"], f"{ADMIN}/converted")
    repo.add_source(nb.id, "busy.txt", "text", "busy")  # still processing: not copied
    gone = repo.add_source(nb.id, "old.txt", "text", "old").library_id
    repo.set_library_status(gone, "ready")
    repo.trash_library_source(ADMIN, gone)  # trashed: not copied
    repo.add_output(nb.id, "Report")  # rag copies outputs
    repo.starter = StarterRef(owner_id=ADMIN, notebook_id=nb.id)
    return nb, made


def test_a_new_user_gets_a_ready_copy_of_the_starter_notebook():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    nb, made = _starter(repo, storage)
    user = uuid4()
    assert ensure_starter(repo, storage, user) == 5
    [notebook] = repo.list_notebooks(user)
    assert notebook.title == "Getting started with lasteverLM" and notebook.id != nb.id
    sources = repo.list_sources(notebook.id)
    assert sorted(s.name for s in sources) == sorted(made)
    for source in sources:
        old = repo.library[made[source.name]]
        copy = repo.library[source.library_id]
        assert copy.owner == user and copy.starter and copy.status == "ready"
        assert copy.summary == old.summary and copy.dedupe_key == old.dedupe_key
        assert repo.chunks[copy.id] == repo.chunks[old.id]  # embeddings copied, not made
        assert copy.storage_path.startswith(f"{user}/{copy.id}/")
        assert storage.objects[copy.storage_path] == storage.objects[old.storage_path]
    audio = next(repo.library[s.library_id] for s in sources if s.kind == "audio")
    assert audio.transcribed_path == f"{user}/{audio.id}/{TRANSCRIBED_NAME}"
    assert storage.types[audio.transcribed_path] == "audio/mpeg"
    image = next(repo.library[s.library_id] for s in sources if s.kind == "image")
    assert storage.types[image.storage_path] == "image/png"
    # No processing, no charge.
    assert repo.pending() == 1 and repo.usage == []  # the admin's busy.txt only
    # rag's handover row, with the old -> new link and library ids.
    [(target, source_nb, owner, maps)] = repo.output_copies
    assert (target, source_nb, owner) == (notebook.id, nb.id, user)
    by_old = {UUID(k): UUID(v) for k, v in maps["source_map"].items()}
    assert {by_old[made[s.name]] for s in sources} == {s.library_id for s in sources}
    assert {
        by_old[link] for link, (n, _, _) in list(repo.links.items()) if n == nb.id if link in by_old
    } == {s.id for s in sources}


def test_only_once_and_only_into_an_empty_library():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    _starter(repo, storage)
    user = uuid4()
    assert ensure_starter(repo, storage, user) == 5
    objects = len(storage.objects)
    assert ensure_starter(repo, storage, user) == 0 and len(storage.objects) == objects
    # Someone with an upload of their own is not seeded; nothing is left behind.
    busy = uuid4()
    repo.add_source(repo.create_notebook(busy, "mine").id, "own.txt", "text", "own")
    assert ensure_starter(repo, storage, busy) == 0
    assert len(storage.objects) == objects and repo.list_notebooks(busy)[0].title == "mine"
    # The starter's author gets no copy of their own notebook.
    assert ensure_starter(repo, storage, ADMIN) == 0


def test_without_a_starter_nothing_is_seeded_until_one_is_set():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    user = uuid4()
    assert ensure_starter(repo, storage, user) == 0
    assert repo.list_notebooks(user) == [] and not repo.is_seeded(user)
    repo.starter = StarterRef(owner_id=ADMIN, notebook_id=uuid4())  # deleted since
    assert ensure_starter(repo, storage, user) == 0 and not repo.is_seeded(user)
    _starter(repo, storage)
    assert ensure_starter(repo, storage, user) == 5


def test_a_storage_failure_copies_nothing_and_tries_again(monkeypatch):
    repo, storage = InMemoryRepository(), InMemoryStorage()
    _starter(repo, storage)
    before = dict(storage.objects)
    calls = []
    real_put = storage.put

    def flaky(key, data, media_type):
        calls.append(key)
        if len(calls) == 3:
            raise StorageError("bucket down")
        real_put(key, data, media_type)

    monkeypatch.setattr(storage, "put", flaky)
    user = uuid4()
    assert ensure_starter(repo, storage, user) == 0
    assert storage.objects == before and repo.list_notebooks(user) == []
    monkeypatch.setattr(storage, "put", real_put)
    assert ensure_starter(repo, storage, user) == 5


def test_the_copy_happens_on_first_library_access_and_shows_the_badge(client, repo, storage):
    _starter(repo, storage)
    entries = client.get("/api/ingest/library").json()
    assert len(entries) == 5 and all(e["starter"] and e["status"] == "ready" for e in entries)
    [notebook] = client.get("/api/ingest/notebooks").json()
    listed = client.get(f"/api/ingest/notebooks/{notebook['id']}/sources").json()
    assert {s["starter"] for s in listed} == {True}
    # The copies are the user's own: deletable like any upload.
    lib = entries[0]["id"]
    assert client.delete(f"/api/ingest/library/{lib}").status_code == 204
    assert client.delete(f"/api/ingest/library/{lib}/purge").status_code == 204
    assert UUID(lib) not in repo.library
    assert all(e["id"] != lib for e in client.get("/api/ingest/library").json())
    assert DEMO_USER_ID in repo.seeded
