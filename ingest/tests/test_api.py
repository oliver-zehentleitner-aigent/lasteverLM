from uuid import uuid4

from tests.test_loaders import minimal_pdf


def test_healthz_needs_no_token_and_answers_on_both_paths(client):
    del client.headers["Authorization"]
    assert client.get("/api/ingest/healthz").json() == {"status": "ok"}
    assert client.get("/healthz").json() == {"status": "ok"}


def test_missing_or_wrong_token(client):
    del client.headers["Authorization"]
    r = client.get("/api/ingest/notebooks")
    assert r.status_code == 401 and r.json() == {"error": "missing bearer token"}
    r = client.get("/api/ingest/notebooks", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401 and "error" in r.json()


def test_notebook_lifecycle(client):
    assert client.get("/api/ingest/notebooks").json() == []
    r = client.post("/api/ingest/notebooks", json={"title": "  Thesis  "})
    assert r.status_code == 201
    nb = r.json()
    assert set(nb) == {"id", "title", "created_at"} and nb["title"] == "Thesis"
    assert [n["id"] for n in client.get("/api/ingest/notebooks").json()] == [nb["id"]]
    assert client.delete(f"/api/ingest/notebooks/{nb['id']}").status_code == 204
    assert client.delete(f"/api/ingest/notebooks/{nb['id']}").status_code == 404
    assert client.get("/api/ingest/notebooks").json() == []


def test_validation_error_uses_error_shape(client):
    r = client.post("/api/ingest/notebooks", json={"title": ""})
    assert r.status_code == 422
    assert r.json()["error"].startswith("title:")


def test_other_users_notebook_is_not_found(client, repo):
    nb = repo.create_notebook(uuid4(), "theirs")
    assert client.get(f"/api/ingest/notebooks/{nb.id}/sources").status_code == 404
    assert client.delete(f"/api/ingest/notebooks/{nb.id}").status_code == 404


def _notebook(client) -> str:
    return client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]


def test_upload_text_source_is_queued_then_processed(client, repo, storage, embedder, run_queue):
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("notes.txt", b"hello " * 100, "text/plain")},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["kind"] == "text" and body["name"] == "notes.txt" and body["notebook_id"] == nb
    assert body["status"] == "processing"
    assert set(body) == {"id", "notebook_id", "name", "kind", "status", "error", "created_at"}
    # The API only stored the file and queued the row.
    assert list(storage.objects) == [f"{nb}/{body['id']}/notes.txt"]
    assert embedder.calls == [] and repo.usage == []
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert listed[0]["status"] == "processing"
    # A worker picks it up.
    assert run_queue() == 1
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert len(listed) == 1 and listed[0]["status"] == "ready"
    assert embedder.calls and [u.kind for u in repo.usage] == ["embedding", "llm"]
    assert repo.claimed[__import__("uuid").UUID(body["id"])] == "test"


def test_upload_pdf_source(client, repo, run_queue):
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("paper.pdf", minimal_pdf(["Hello ingest"]), "application/pdf")},
    )
    assert r.status_code == 202
    assert r.json()["kind"] == "pdf"
    sid = r.json()["id"]
    run_queue()
    assert repo.chunks[__import__("uuid").UUID(sid)][0][0].page == 1


def test_unsupported_kind_and_size_limits(client):
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("x.docx", b"...", "application/octet-stream")},
    )
    assert r.status_code == 415
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("big.txt", b"x" * 5000, "text/plain")},
    )
    assert r.status_code == 413
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert r.status_code == 400


def test_url_source_is_not_implemented_yet(client):
    nb = _notebook(client)
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": "https://example.org"})
    assert r.status_code == 501
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"nope": 1})
    assert r.status_code == 422


def test_no_credit_is_402_before_anything_is_stored(client, repo, storage):
    repo.default_balance = 0
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    )
    assert r.status_code == 402 and r.json() == {"error": "credit exhausted"}
    assert storage.objects == {} and repo.sources == {}


def test_delete_source_removes_object_and_other_users_cannot(client, repo, storage):
    nb = _notebook(client)
    sid = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    ).json()["id"]
    assert client.delete(f"/api/ingest/sources/{uuid4()}").status_code == 404
    assert client.delete(f"/api/ingest/sources/{sid}").status_code == 204
    assert storage.objects == {}
    assert client.get(f"/api/ingest/notebooks/{nb}/sources").json() == []


def test_generated_source_is_listed_and_deleted_without_storage(client, repo, storage):
    nb = _notebook(client)
    generated = repo.create_source(
        __import__("uuid").UUID(nb), uuid4(), "report.md", "generated", None
    )
    repo.set_source_status(generated.id, "ready")
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert [s["kind"] for s in listed] == ["generated"]
    assert "summary" not in listed[0]
    assert client.delete(f"/api/ingest/sources/{generated.id}").status_code == 204
    assert storage.objects == {} and repo.sources == {}


def test_delete_notebook_removes_its_objects(client, storage):
    nb = _notebook(client)
    client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    )
    assert len(storage.objects) == 1
    assert client.delete(f"/api/ingest/notebooks/{nb}").status_code == 204
    assert storage.objects == {}


def test_filename_is_sanitized_for_the_object_key(client, storage):
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("../../etc/pass wd.txt", b"text", "text/plain")},
    )
    assert r.status_code == 202
    assert r.json()["name"] == "pass_wd.txt"
    assert list(storage.objects)[0].endswith("/pass_wd.txt")
