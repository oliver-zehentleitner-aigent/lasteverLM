"""The "As read" view: a source's chunks as the system read them."""

from uuid import UUID, uuid4

from lasteverlm_core import Chunk


def _source(client, repo, pages=5):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    src = repo.add_source(UUID(nb), "paper.pdf", "pdf", "k")
    repo.replace_chunks(
        src.library_id,
        [Chunk(idx=i, text=f"chunk {i}", page=i // 2 + 1) for i in reversed(range(pages))],
        [[float(i), 0.0] for i in reversed(range(pages))],
    )
    return src


def test_chunks_come_in_order_with_index_page_and_id(client, repo):
    src = _source(client, repo)
    r = client.get(f"/api/ingest/sources/{src.id}/chunks")
    assert r.status_code == 200
    body = r.json()
    assert (body["source_id"], body["library_id"]) == (str(src.id), str(src.library_id))
    assert body["kind"] == "pdf" and body["chunk_count"] == 5 and body["offset"] == 0
    assert [(c["index"], c["page"], c["text"]) for c in body["chunks"]] == [
        (i, i // 2 + 1, f"chunk {i}") for i in range(5)
    ]
    ids = repo.chunk_ids[src.library_id]
    assert {c["chunk_id"] for c in body["chunks"]} == {str(i) for i in ids}


def test_chunks_are_paged(client, repo):
    src = _source(client, repo)
    url = f"/api/ingest/sources/{src.id}/chunks"
    page = client.get(f"{url}?offset=3&limit=2").json()
    assert page["chunk_count"] == 5 and page["offset"] == 3
    assert [c["index"] for c in page["chunks"]] == [3, 4]
    assert client.get(f"{url}?offset=9").json()["chunks"] == []
    for bad in ("limit=0", "limit=201", "offset=-1"):
        assert client.get(f"{url}?{bad}").status_code == 422


def test_only_the_owner_reads_the_chunks(client, repo):
    theirs = repo.add_source(repo.create_notebook(uuid4(), "x").id, "a.txt", "text", "k")
    assert client.get(f"/api/ingest/sources/{theirs.id}/chunks").status_code == 404
    assert client.get(f"/api/ingest/sources/{uuid4()}/chunks").status_code == 404
