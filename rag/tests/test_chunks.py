from .conftest import (
    AUTH,
    CHUNK_1,
    OWNER,
    SOURCE_1,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk_uuid,
    make_client,
)

VIEW = {
    "chunk_id": CHUNK_1,
    "source_id": SOURCE_1,
    "source_name": "vnc.pdf",
    "source_kind": "pdf",
    "page": 3,
    "chunk_index": 11,
    "chunk_count": 43,
    "text": "  VNC listens on port 5900.\n",
}


def test_the_owner_reads_the_exact_chunk_behind_a_citation(settings):
    store = FakeStore()
    store.chunk_rows[CHUNK_1] = (OWNER, VIEW)
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    r = client.get(f"/api/rag/chunks/{CHUNK_1}", headers=AUTH)
    assert (r.status_code, r.json()) == (200, VIEW)


def test_someone_elses_or_an_unknown_chunk_is_not_found(settings):
    store = FakeStore()
    store.chunk_rows[CHUNK_1] = ("someone-else", VIEW)
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    for chunk_id in (CHUNK_1, chunk_uuid(99)):
        r = client.get(f"/api/rag/chunks/{chunk_id}", headers=AUTH)
        assert (r.status_code, r.json()) == (404, {"error": "chunk not found"})
    assert client.get(f"/api/rag/chunks/{CHUNK_1}").status_code == 401
    assert client.get("/api/rag/chunks/not-a-uuid", headers=AUTH).status_code == 422
