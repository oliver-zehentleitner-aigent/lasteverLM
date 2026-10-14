from uuid import uuid4

from lasteverlm_core import DEMO_USER_ID, StorageError

OTHER = uuid4()


def _fill(repo, storage, owner):
    """Two notebooks, an upload, a converted recording (trashed), a
    generated row and the seed mark."""
    nb = repo.create_notebook(owner, "nb")
    repo.create_notebook(owner, "empty")
    doc = repo.add_source(nb.id, "a.txt", "text", f"{owner}/a/a.txt").library_id
    rec = repo.add_source(nb.id, "talk.m4a", "audio", f"{owner}/r/talk.m4a").library_id
    repo.set_transcribed_path(rec, f"{owner}/r/_transcribed.mp3")
    repo.trash_library_source(owner, rec)
    gen = repo.add_source(nb.id, "Report", "generated", None).library_id
    for key in (f"{owner}/a/a.txt", f"{owner}/r/talk.m4a", f"{owner}/r/_transcribed.mp3"):
        storage.put(key, b"x", "application/octet-stream")
    repo.claim_seed(owner)
    return doc, rec, gen


def test_only_admins_delete_a_user(client, repo):
    path = f"/api/ingest/admin/users/{OTHER}"
    assert client.delete(path, headers={"Authorization": ""}).status_code == 401
    assert client.delete(path).status_code == 403  # an ordinary user
    repo.viewers.add(DEMO_USER_ID)
    r = client.delete(path)
    assert r.status_code == 403 and r.json() == {"error": "admin only"}  # viewers only read


def test_deleting_a_user_removes_their_objects_then_their_rows(client, repo, storage):
    repo.admins.add(DEMO_USER_ID)
    _fill(repo, storage, OTHER)
    mine = repo.create_notebook(DEMO_USER_ID, "admin's")
    storage.put("keep", b"x", "text/plain")
    repo.add_source(mine.id, "keep.txt", "text", "keep")
    r = client.delete(f"/api/ingest/admin/users/{OTHER}")
    assert r.status_code == 204 and r.content == b""
    assert list(storage.objects) == ["keep"]
    assert all(lib.owner != OTHER for lib in repo.library.values())
    assert all(owner != OTHER for owner, _ in repo.notebooks.values())
    assert OTHER not in repo.seeded
    assert repo.get_notebook(DEMO_USER_ID, mine.id) is not None
    # Idempotent: nothing left, and a user that never existed, are 204 too.
    assert client.delete(f"/api/ingest/admin/users/{OTHER}").status_code == 204
    assert client.delete(f"/api/ingest/admin/users/{uuid4()}").status_code == 204


def test_a_storage_failure_keeps_every_row_for_the_retry(client, repo, storage, monkeypatch):
    repo.admins.add(DEMO_USER_ID)
    doc, rec, gen = _fill(repo, storage, OTHER)

    def broken(*keys):
        raise StorageError("delete failed: AccessDenied")

    monkeypatch.setattr(storage, "delete", broken)
    r = client.delete(f"/api/ingest/admin/users/{OTHER}")
    assert r.status_code == 503
    assert r.json()["error"] == (
        f"storage: 3 object(s) of user {OTHER} not deleted (first {OTHER}/a/a.txt): "
        "delete failed: AccessDenied"
    )
    assert {doc, rec, gen} <= set(repo.library) and OTHER in repo.seeded
    monkeypatch.undo()
    assert client.delete(f"/api/ingest/admin/users/{OTHER}").status_code == 204
    assert not ({doc, rec, gen} & set(repo.library))
