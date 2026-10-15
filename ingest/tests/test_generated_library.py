"""Outputs as library items: rag writes a generated library source per
output; ingest lists them on their own and links them into any of the
owner's notebooks, reusing their chunks."""

from uuid import UUID

from lasteverlm_core import DEMO_USER_ID


def _notebook(client, title="nb") -> str:
    return client.post("/api/ingest/notebooks", json={"title": title}).json()["id"]


def test_ready_outputs_are_listed_with_their_origin(client, repo):
    origin = _notebook(client, "Thesis")
    report = repo.add_output(UUID(origin), "Report")
    repo.add_output(UUID(origin), "Still writing", status="processing")
    trashed = repo.add_output(UUID(origin), "Trashed")
    repo.library[trashed] = repo.library[trashed].model_copy(
        update={"deleted_at": repo.library[trashed].created_at}
    )
    other_users = repo.create_notebook(UUID(int=7), "theirs")
    repo.add_output(other_users.id, "Not mine")

    [entry] = client.get("/api/ingest/library?kind=generated").json()
    assert entry["id"] == str(report) and entry["name"] == "Report"
    assert entry["kind"] == "generated" and entry["preview_url"] is None
    assert entry["origin"] == {"id": origin, "title": "Thesis"}
    assert [n["id"] for n in entry["notebooks"]] == [origin]
    # The uploads list stays uploads only.
    assert all(e["kind"] != "generated" for e in client.get("/api/ingest/library").json())
    assert client.get("/api/ingest/library?kind=pdf").status_code == 422


def test_an_output_is_linked_into_another_notebook_without_processing(client, repo):
    origin, other = _notebook(client, "Thesis"), _notebook(client, "Talk")
    report = repo.add_output(UUID(origin), "Report")
    repo.replace_chunks(report, [], [])
    r = client.post(f"/api/ingest/notebooks/{other}/sources", json={"library_id": str(report)})
    assert r.status_code == 202 and r.json()["kind"] == "generated"
    assert r.json()["status"] == "ready" and repo.pending() == 0
    # Linking again is the existing link.
    again = client.post(f"/api/ingest/notebooks/{other}/sources", json={"library_id": str(report)})
    assert again.status_code == 200 and again.json()["id"] == r.json()["id"]
    [entry] = client.get("/api/ingest/library?kind=generated").json()
    assert {n["title"] for n in entry["notebooks"]} == {"Thesis", "Talk"}
    assert repo.usage == []


def test_only_ready_untrashed_own_outputs_can_be_linked(client, repo):
    nb = _notebook(client)
    url = f"/api/ingest/notebooks/{nb}/sources"
    busy = repo.add_output(UUID(nb), "Busy", status="processing")
    theirs = repo.add_output(repo.create_notebook(UUID(int=7), "x").id, "Theirs")
    for library_id in (busy, theirs):
        assert client.post(url, json={"library_id": str(library_id)}).status_code == 404


def test_an_output_outlives_its_origin_notebook_and_its_unlinking(client, repo):
    origin, other = _notebook(client, "Thesis"), _notebook(client, "Talk")
    report = repo.add_output(UUID(origin), "Report")
    client.post(f"/api/ingest/notebooks/{other}/sources", json={"library_id": str(report)})
    # Unlinked from its origin (the origin link has the row's id; it is not
    # in the origin's source list): the origin still names that notebook.
    assert client.get(f"/api/ingest/notebooks/{origin}/sources").json() == []
    assert client.delete(f"/api/ingest/sources/{report}").status_code == 204
    [entry] = client.get("/api/ingest/library?kind=generated").json()
    assert entry["origin"] == {"id": origin, "title": "Thesis"}
    # The origin notebook deleted: the title snapshot remains, the id goes.
    assert client.delete(f"/api/ingest/notebooks/{origin}").status_code == 204
    [entry] = client.get("/api/ingest/library?kind=generated").json()
    assert entry["origin"] == {"id": None, "title": "Thesis"}
    assert [n["title"] for n in entry["notebooks"]] == ["Talk"]
    assert repo.library[report].owner == DEMO_USER_ID


def test_an_output_is_no_source_of_its_own_notebook_but_of_one_it_is_linked_into(client, repo):
    """The origin link (rag writes it under the generated row's id) is the
    output itself, listed under Outputs; a link into another notebook is a
    source there. An orphan (a row no output points to, left by an abandoned
    attempt) is an origin link too and stays out of the list."""
    origin, other = _notebook(client, "Thesis"), _notebook(client, "Talk")
    upload = client.post(
        f"/api/ingest/notebooks/{origin}/sources",
        files={"file": ("notes.txt", b"some notes", "text/plain")},
    ).json()
    report = repo.add_output(UUID(origin), "Report")
    orphan = repo.add_output(UUID(origin), "Is the web interface well-designed?")
    del repo.outputs[orphan], repo.output_ids[orphan]  # no output points to it
    listed = client.get(f"/api/ingest/notebooks/{origin}/sources").json()
    assert [s["id"] for s in listed] == [upload["id"]]
    added = client.post(
        f"/api/ingest/notebooks/{other}/sources", json={"library_id": str(report)}
    ).json()
    [linked] = client.get(f"/api/ingest/notebooks/{other}/sources").json()
    assert linked["id"] == added["id"] != str(report) and linked["kind"] == "generated"
