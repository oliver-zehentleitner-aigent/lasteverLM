from uuid import UUID, uuid4

from lasteverlm_core import DEMO_USER_ID

from tests.test_loaders import minimal_pdf


def test_healthz_needs_no_token_and_answers_on_both_paths(client, monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("APP_COMMIT", raising=False)
    del client.headers["Authorization"]
    up = {"postgres": "ok", "storage": "ok", "inference": "ok"}
    unknown = {"status": "ok", "version": "unknown", "commit": "unknown", "dependencies": up}
    assert client.get("/api/ingest/healthz").json() == unknown
    assert client.get("/healthz").json() == unknown


def test_healthz_reports_the_build(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "v0.6.0")
    monkeypatch.setenv("APP_COMMIT", "abc1234")
    up = {"postgres": "ok", "storage": "ok", "inference": "ok"}
    build = {"status": "ok", "version": "v0.6.0", "commit": "abc1234", "dependencies": up}
    assert client.get("/healthz").json() == build
    assert client.get("/api/ingest/healthz").json() == build


def test_a_dependency_that_is_down_is_reported_and_the_service_stays_ok(client, checks):
    checks.up["storage"] = False
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["dependencies"] == {"postgres": "ok", "storage": "down", "inference": "ok"}


def test_the_probe_checks_what_ingest_uses(repo, storage):
    from lasteverlm_core import S3Settings, S3Storage

    from lasteverlm_ingest.main import dependency_probe
    from tests.conftest import make_settings
    from tests.test_worker import deps

    # Test doubles cannot be probed: only the inference API is checked.
    assert set(dependency_probe(deps(repo, storage, None))._checks) == {"inference"}
    s3 = S3Storage(S3Settings("https://s3.invalid", "b", "ak", "sk"), client=object())

    from lasteverlm_ingest.repository import PostgresRepository

    postgres = object.__new__(PostgresRepository)  # no pool: building the probe opens nothing
    d = deps(postgres, s3, None)
    d = d.__class__(**{**d.__dict__, "settings": make_settings()})
    assert set(dependency_probe(d)._checks) == {"postgres", "storage", "inference"}


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
    assert set(nb) == {"id", "title", "created_at", "share_token"} and nb["title"] == "Thesis"
    assert nb["share_token"] is None
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
    assert set(body) == {
        "id",
        "notebook_id",
        "name",
        "kind",
        "status",
        "error",
        "created_at",
        "library_id",
        "capture",
        "starter",
        "preview_url",
        "original_url",
    }
    assert body["capture"] is None  # only PDFs have a capture mode
    # The API only stored the file and queued the library source.
    assert list(storage.objects) == [f"{DEMO_USER_ID}/{body['library_id']}/notes.txt"]
    assert embedder.calls == [] and repo.usage == []
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert listed[0]["status"] == "processing"
    # A worker picks it up.
    assert run_queue() == 1
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert len(listed) == 1 and listed[0]["status"] == "ready"
    assert embedder.calls and [u.kind for u in repo.usage] == ["embedding", "llm"]
    assert repo.claimed[UUID(body["library_id"])] == "test"


def test_upload_pdf_source(client, repo, run_queue):
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("paper.pdf", minimal_pdf(["Hello ingest"]), "application/pdf")},
    )
    assert r.status_code == 202
    assert r.json()["kind"] == "pdf"
    run_queue()
    assert repo.chunks[UUID(r.json()["library_id"])][0][0].page == 1


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


def test_url_source_stores_the_url_for_the_worker(client, storage):
    nb = _notebook(client)
    url = "https://example.org/a/page?x=1"
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": url})
    assert r.status_code == 202
    body = r.json()
    assert body["kind"] == "url" and body["name"] == url and body["status"] == "processing"
    assert storage.objects == {f"{DEMO_USER_ID}/{body['library_id']}/url": url.encode()}


def test_url_source_validation(client, storage):
    nb = _notebook(client)
    for bad in ("ftp://example.org/x", "example.org", "https://user:pw@example.org/", "http://"):
        r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": bad})
        assert r.status_code == 400, bad
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"nope": 1})
    assert r.status_code == 400
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"library_id": "nope"})
    assert r.status_code == 422
    assert storage.objects == {}


def test_url_to_an_internal_address_fails_in_the_worker(client, run_queue):
    nb = _notebook(client)
    r = client.post(f"/api/ingest/notebooks/{nb}/sources", json={"url": "http://127.0.0.1:5432/"})
    assert r.status_code == 202
    run_queue()
    source = client.get(f"/api/ingest/notebooks/{nb}/sources").json()[0]
    assert source["status"] == "failed"
    assert "not a public address" in source["error"]


def test_without_credit_a_source_is_stored_and_waits_until_there_is_credit(client, repo, storage):
    repo.default_balance = 0
    nb = _notebook(client)
    url = f"/api/ingest/notebooks/{nb}/sources"
    r = client.post(url, files={"file": ("a.txt", b"text", "text/plain")})
    # Adding is always allowed: stored, queued, shown as waiting.
    assert r.status_code == 202 and r.json()["status"] == "waiting_for_credit"
    lib = UUID(r.json()["library_id"])
    assert len(storage.objects) == 1 and repo.library[lib].status == "processing"
    assert [s["status"] for s in client.get(url).json()] == ["waiting_for_credit"]
    [entry] = client.get("/api/ingest/library").json()
    assert entry["status"] == "waiting_for_credit"
    assert client.get(f"/api/ingest/library/{lib}").json()["status"] == "waiting_for_credit"
    # No worker takes it, no attempt is counted.
    assert repo.claim_library_source("w", 600) is None and repo.library[lib].attempts == 0
    # Credit arrives: it is shown and claimed as processing again.
    repo.credits[DEMO_USER_ID] = 100
    assert [s["status"] for s in client.get(url).json()] == ["processing"]
    assert repo.claim_library_source("w", 600) == lib
    # Uploading the same bytes again links the entry at no cost either way.
    again = client.post(url, files={"file": ("a.txt", b"text", "text/plain")})
    assert again.status_code == 200 and len(storage.objects) == 1


def test_delete_source_detaches_and_other_users_cannot(client, repo, storage):
    nb = _notebook(client)
    sid = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    ).json()["id"]
    other = repo.create_notebook(uuid4(), "theirs")
    theirs = repo.add_source(other.id, "b.txt", "text", "k")
    assert client.delete(f"/api/ingest/sources/{uuid4()}").status_code == 404
    assert client.delete(f"/api/ingest/sources/{theirs.id}").status_code == 404
    assert client.delete(f"/api/ingest/sources/{sid}").status_code == 204
    assert client.get(f"/api/ingest/notebooks/{nb}/sources").json() == []
    # Detached, not deleted: the library source and its object stay.
    assert len(storage.objects) == 1
    assert [e["notebooks"] for e in client.get("/api/ingest/library").json()] == [[]]


def test_generated_source_is_listed_and_detached_like_any_source(client, repo, storage):
    nb = _notebook(client)
    generated = repo.add_source(UUID(nb), "report.md", "generated", None)
    repo.set_library_status(generated.library_id, "ready")
    listed = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert [s["kind"] for s in listed] == ["generated"]
    assert "summary" not in listed[0]
    assert client.delete(f"/api/ingest/sources/{generated.id}").status_code == 204
    # The output lives on in the library; only the link went.
    assert storage.objects == {} and repo.links == {}
    assert generated.library_id in repo.library


def test_delete_notebook_keeps_its_sources_in_the_library(client, repo, storage):
    nb = _notebook(client)
    client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": ("a.txt", b"text", "text/plain")}
    )
    generated = repo.add_source(UUID(nb), "report.md", "generated", None)
    assert client.delete(f"/api/ingest/notebooks/{nb}").status_code == 204
    assert len(storage.objects) == 1
    [entry] = client.get("/api/ingest/library").json()
    assert entry["name"] == "a.txt" and entry["notebooks"] == []
    # rag's output keeps its generated library source.
    assert generated.library_id in repo.library


def test_filename_is_sanitized_for_the_object_key(client, storage):
    nb = _notebook(client)
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("../../etc/pass wd.txt", b"text", "text/plain")},
    )
    assert r.status_code == 202
    assert r.json()["name"] == "pass_wd.txt"
    assert list(storage.objects)[0].endswith("/pass_wd.txt")


def test_a_missing_exchange_rate_is_shown_on_every_queued_source(client, repo):
    from lasteverlm_core import PricingRules

    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"
    lib = client.post(url, files={"file": ("a.txt", b"text", "text/plain")}).json()["library_id"]
    rules, repo.rules = repo.rules, PricingRules()
    reason = "pricing has no exchange rate, ask an admin"
    [source] = client.get(url).json()
    assert source["status"] == "processing" and source["error"] == reason
    assert client.get(f"/api/ingest/library/{lib}").json()["error"] == reason
    repo.rules = rules  # the admin set the rate: nothing stale stays behind
    assert client.get(url).json()[0]["error"] is None
