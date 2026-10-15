"""Charts stay inside the user's selection: Find charts reads and searches
only the selected sources, and a candidate proposed for another selection
is refused on Create, never drawn."""

from .conftest import (
    AUTH,
    NOTEBOOK,
    FakeIngest,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    chunk_uuid,
    make_client,
)
from .test_chart import OUTPUTS, PROPOSAL, PROPOSE, SHARE, VISITORS

GENERATED = chunk(3, "The report says 3.000 visitors.", source_kind="generated")


def source(store: FakeStore, piece, name: str, status: str = "ready", kind: str = "pdf") -> str:
    """A notebook source with the id the chunk carries."""
    store.sources[piece.source_id] = {
        "id": piece.source_id,
        "notebook_id": NOTEBOOK,
        "name": name,
        "kind": kind,
        "status": status,
        "summary": f"{name} figures.",
        "error": None,
    }
    return str(piece.source_id)


def setup(settings, *replies, unread_share=False):
    store = FakeStore()
    visitors = source(store, VISITORS, "visitors.pdf")
    share = source(store, SHARE, "share.pdf", status="added" if unread_share else "ready")
    source(store, GENERATED, "Report", kind="generated")
    retriever, llm, ingest = (
        FakeRetriever([VISITORS, SHARE, GENERATED]),
        FakeLLM(*replies),
        FakeIngest(),
    )
    client = make_client(settings, store, retriever, llm, ingest=ingest)
    return store, retriever, llm, ingest, client, visitors, share


def test_find_charts_searches_only_the_selected_sources(settings):
    _, retriever, llm, _, client, _, share = setup(settings, PROPOSAL)
    r = client.post(PROPOSE, json={"source_ids": [share]}, headers=AUTH)
    assert r.status_code == 200, r.text
    searches = [c for c in retriever.calls if "embedding" in c or "k" in c]
    assert searches and all(c["source_ids"] == [share] or c["source_id"] == share for c in searches)
    # every passage the proposal could cite comes from the selected source
    assert VISITORS.text not in llm.calls[0][1] and SHARE.text in llm.calls[0][1]


def test_find_charts_reads_an_unread_selected_source_first(settings):
    store, _, llm, ingest, client, _, share = setup(settings, PROPOSAL, unread_share=True)
    r = client.post(PROPOSE, json={"source_ids": [share]}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert ("process", AUTH["Authorization"], [share]) in ingest.calls
    # the test waits 0 s: still being read, nothing proposed, no model call
    assert r.json() == {
        "candidates": [],
        "reason": "still being read: share.pdf; find charts again in a moment",
    }
    assert llm.calls == []


def test_a_candidate_from_another_selection_is_refused_on_create(settings):
    store, _, _, _, client, visitors, share = setup(settings, PROPOSAL)
    everything = client.post(PROPOSE, json={}, headers=AUTH).json()["candidates"]
    visitors_chart = everything[0]  # cites the visitors source
    body = {"kind": "chart", "options": {"charts": [visitors_chart]}, "source_ids": [share]}
    r = client.post(OUTPUTS, json=body, headers=AUTH)
    assert (r.status_code, r.json()) == (
        409,
        {
            "error": "charts: a candidate cites a source outside the selected sources; "
            "find charts again",
            "code": "chart_out_of_scope",
        },
    )
    assert store.outputs == {}
    # with that source selected it is drawn
    body["source_ids"] = [visitors]
    assert client.post(OUTPUTS, json=body, headers=AUTH).status_code == 202


def test_a_candidate_citing_a_generated_or_foreign_passage_is_refused(settings):
    store, _, _, _, client, _, _ = setup(settings, PROPOSAL)
    candidate = client.post(PROPOSE, json={}, headers=AUTH).json()["candidates"][0]
    forged = {
        **candidate,
        "passages": [{**candidate["passages"][0], "chunk_id": GENERATED.chunk_id}],
    }
    r = client.post(OUTPUTS, json={"kind": "chart", "options": {"charts": [forged]}}, headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "chart_out_of_scope"
    missing = {**candidate, "passages": [{**candidate["passages"][0], "chunk_id": chunk_uuid(9)}]}
    r = client.post(OUTPUTS, json={"kind": "chart", "options": {"charts": [missing]}}, headers=AUTH)
    assert (r.status_code, r.json()["error"]) == (
        409,
        "charts: a cited passage is not in this notebook",
    )
