"""Adding several library entries to a notebook at once, and the one
library list (uploads and outputs together)."""

from uuid import UUID, uuid4


def _notebook(client, title="nb") -> str:
    return client.post("/api/ingest/notebooks", json={"title": title}).json()["id"]


def _upload(client, nb, name, data) -> str:
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources", files={"file": (name, data, "text/plain")}
    )
    return r.json()["library_id"]


def test_bulk_links_uploads_and_outputs_and_reports_what_was_there(client, repo):
    origin, target = _notebook(client, "Thesis"), _notebook(client, "Talk")
    a = _upload(client, origin, "a.txt", b"first")
    b = _upload(client, origin, "b.txt", b"second")  # still processing: linkable
    report = str(repo.add_output(UUID(origin), "Report"))
    _upload(client, target, "a.txt", b"first")  # a is in the target already
    url = f"/api/ingest/notebooks/{target}/sources/bulk"

    r = client.post(url, json={"library_ids": [a, b, report, b]})
    assert r.status_code == 200
    assert r.json() == {"added": [b, report], "already": [a]}
    listed = {s["library_id"] for s in client.get(f"/api/ingest/notebooks/{target}/sources").json()}
    assert listed == {a, b, report}
    assert repo.pending() == 2  # a and b from their uploads; linking queued nothing
    # Again: everything is there, nothing doubled.
    again = client.post(url, json={"library_ids": [report, a]}).json()
    assert again == {"added": [], "already": [report, a]}
    assert len(client.get(f"/api/ingest/notebooks/{target}/sources").json()) == 3


def test_bulk_adds_nothing_when_one_id_cannot_be_linked(client, repo):
    nb, target = _notebook(client), _notebook(client, "target")
    mine = _upload(client, nb, "a.txt", b"mine")
    trashed = _upload(client, nb, "t.txt", b"trashed")
    client.delete(f"/api/ingest/library/{trashed}")
    busy = str(repo.add_output(UUID(nb), "Busy", status="processing"))
    theirs = str(
        repo.add_source(repo.create_notebook(uuid4(), "x").id, "x", "text", "k").library_id
    )
    unknown = str(uuid4())
    url = f"/api/ingest/notebooks/{target}/sources/bulk"
    r = client.post(url, json={"library_ids": [mine, trashed, busy, theirs, unknown]})
    assert r.status_code == 404
    assert r.json()["error"] == (
        f"library sources not found: {trashed}, {busy}, {theirs}, {unknown}"
    )
    assert client.get(f"/api/ingest/notebooks/{target}/sources").json() == []


def test_bulk_needs_the_callers_notebook_and_a_sane_list(client, repo):
    nb = _notebook(client)
    a = _upload(client, nb, "a.txt", b"x")
    foreign = repo.create_notebook(uuid4(), "theirs")
    r = client.post(f"/api/ingest/notebooks/{foreign.id}/sources/bulk", json={"library_ids": [a]})
    assert r.status_code == 404
    url = f"/api/ingest/notebooks/{nb}/sources/bulk"
    assert client.post(url, json={"library_ids": []}).status_code == 422
    assert client.post(url, json={"library_ids": [a] * 201}).status_code == 422
    assert client.post(url, json={"library_ids": ["nope"]}).status_code == 422


def test_one_list_has_uploads_and_outputs_with_their_notebooks(client, repo):
    origin, other = _notebook(client, "Thesis"), _notebook(client, "Talk")
    a = _upload(client, origin, "a.txt", b"x")
    report = repo.add_output(UUID(origin), "Report")
    client.post(f"/api/ingest/notebooks/{other}/sources/bulk", json={"library_ids": [a]})

    entries = client.get("/api/ingest/library?kind=all").json()
    assert [e["id"] for e in entries] == [str(report), a]  # newest first
    out, upload = entries
    assert out["kind"] == "generated" and out["output_id"] == str(repo.output_ids[report])
    assert out["origin"] == {"id": origin, "title": "Thesis"}
    assert {n["title"] for n in upload["notebooks"]} == {"Thesis", "Talk"}
    assert upload["origin"] is None and upload["output_id"] is None
    assert [e["id"] for e in client.get("/api/ingest/library").json()] == [a]
