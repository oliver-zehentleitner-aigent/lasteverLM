"""The sources the user ticked: chat and generation use only those."""

from dataclasses import replace

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"
OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
REPORT = '{"title": "VNC report", "markdown": "## VNC"}'


def notebook_with_two_pdfs():
    store = FakeStore()
    vi = store.add_source(NOTEBOOK, "vi.pdf", summary="About vi.")
    vnc = store.add_source(NOTEBOOK, "vnc.pdf", summary="About VNC.")
    hits = [
        replace(chunk(1, "vi chunk", similarity=0.9), source_id=vi, source_name="vi.pdf"),
        replace(chunk(2, "vnc chunk", similarity=0.8), source_id=vnc, source_name="vnc.pdf"),
    ]
    return store, vi, vnc, FakeRetriever(hits)


def ask(client, **body):
    return client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": "q", **body}, headers=AUTH
    )


def test_ask_retrieves_only_the_selected_sources_and_marks_the_rest(settings):
    store, vi, vnc, retriever = notebook_with_two_pdfs()
    llm = FakeLLM("VNC [1].")
    client = make_client(settings, store, retriever, llm)

    body = ask(client, source_ids=[vnc]).json()

    assert [c["source_name"] for c in body["citations"]] == ["vnc.pdf"]
    # the uploads search is filtered; the generated slots are not
    assert [(c["generated"], c["source_ids"]) for c in retriever.calls] == [
        (False, [vnc]),
        (True, None),
    ]
    system, prompt = llm.calls[0]
    assert "vi chunk" not in prompt
    assert "- PDF (uploaded, not in scope): vi.pdf" in system
    assert "- PDF (uploaded): vnc.pdf" in system


def test_absent_or_empty_selection_means_all_sources(settings):
    store, _, _, retriever = notebook_with_two_pdfs()
    llm = FakeLLM("Both [1] [2].")
    client = make_client(settings, store, retriever, llm)
    for body in ({}, {"source_ids": []}):
        ask(client, **body)
    assert [c["source_ids"] for c in retriever.calls if not c["generated"]] == [None, None]
    assert all("(uploaded, not in scope)" not in system for system, _ in llm.calls)


def test_a_source_outside_the_notebook_is_a_422(settings):
    store, vi, _, retriever = notebook_with_two_pdfs()
    foreign = store.add_source(OTHER_NOTEBOOK, "elsewhere.pdf")
    generated = store.add_source(NOTEBOOK, "Report", kind="generated")
    llm = FakeLLM("x")
    client = make_client(settings, store, retriever, llm)
    for bad in (foreign, generated, "00000000-0000-0000-0000-000000000000"):
        for r in (
            ask(client, source_ids=[vi, bad]),
            client.post(OUTPUTS, json={"kind": "report", "source_ids": [bad]}, headers=AUTH),
        ):
            assert (r.status_code, r.json()) == (
                422,
                {"error": f"source_ids: {bad} is not a source of this notebook"},
            )
    assert llm.calls == [] and store.outputs == {} and store.usage == []


def test_a_scope_wins_over_the_selection(settings):
    store, _, vnc, retriever = notebook_with_two_pdfs()
    generated = store.add_source(NOTEBOOK, "Report", kind="generated")
    row = store.create_output(NOTEBOOK, "report", "processing")
    store.update_output(row.id, status="ready", source_id=generated)
    client = make_client(settings, store, retriever, FakeLLM("x"))
    ask(client, source_ids=[vnc], scope={"output_id": row.id})
    assert retriever.calls[0]["source_id"] == generated
    assert retriever.calls[0]["source_ids"] is None


def test_an_output_is_made_from_the_selected_sources_and_records_them(settings):
    store, vi, vnc, retriever = notebook_with_two_pdfs()
    llm = FakeLLM(REPORT)
    client = make_client(settings, store, retriever, llm)

    r = client.post(OUTPUTS, json={"kind": "report", "source_ids": [vnc, vnc]}, headers=AUTH)
    assert r.status_code == 202, r.text
    assert r.json()["options"] == {"sources": [vnc]}
    assert client.worker.run_once() == 1

    prompt = llm.calls[0][1]
    assert "- vnc.pdf: About VNC." in prompt and "vi.pdf" not in prompt
    assert "vnc chunk" in prompt and "vi chunk" not in prompt
    # balanced over the selection: vnc's own best chunks, then the rest within it
    assert [(c["source_id"], c["source_ids"]) for c in retriever.calls] == [
        (vnc, None),
        (None, [vnc]),
    ]
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready" and out["options"] == {"sources": [vnc]}


def test_an_output_whose_selected_sources_are_gone_fails_visibly(settings):
    store, _, vnc, retriever = notebook_with_two_pdfs()
    client = make_client(settings, store, retriever, FakeLLM(REPORT))
    r = client.post(OUTPUTS, json={"kind": "report", "source_ids": [vnc]}, headers=AUTH)
    store.delete_source(vnc)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert (out["status"], out["error"]) == ("failed", "none of the selected sources is ready")


def test_the_shared_view_does_not_reveal_the_selected_source_ids(settings):
    store, _, vnc, retriever = notebook_with_two_pdfs()
    client = make_client(settings, store, retriever, FakeLLM(REPORT))
    body = {"kind": "report", "options": {"language": "de"}, "source_ids": [vnc]}
    output_id = client.post(OUTPUTS, json=body, headers=AUTH).json()["id"]
    client.worker.run_once()
    token = client.post(f"/api/rag/outputs/{output_id}/share", headers=AUTH).json()["share_token"]
    shared = client.get(f"/api/rag/shared/{token}").json()
    assert shared["options"] == {"language": "de"}
    assert vnc not in str(shared)


def test_an_output_waits_only_for_its_selected_sources(settings):
    store, _, vnc, retriever = notebook_with_two_pdfs()
    slow = store.add_source(NOTEBOOK, "slow.pdf", status="processing")
    client = make_client(settings, store, retriever, FakeLLM(REPORT, REPORT))

    # an unselected source still processing does not hold the job back
    picked = client.post(OUTPUTS, json={"kind": "report", "source_ids": [vnc]}, headers=AUTH)
    assert picked.json()["status"] == "processing"
    waiting = client.post(OUTPUTS, json={"kind": "report", "source_ids": [slow]}, headers=AUTH)
    assert waiting.json()["status"] == "waiting"
    assert client.worker.run_once() == 1
    assert store.outputs[picked.json()["id"]]["status"] == "ready"
    assert store.outputs[waiting.json()["id"]]["attempts"] == 0
