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

CONVERSATIONS = f"/api/rag/notebooks/{NOTEBOOK}/conversations"
ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"


def messages(client, conversation_id):
    return client.get(f"/api/rag/conversations/{conversation_id}/messages", headers=AUTH)


def test_conversations_are_created_listed_and_closed(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())

    listed = client.get(CONVERSATIONS, headers=AUTH).json()
    assert [(c["id"], c["title"]) for c in listed] == [(CONVERSATION, "Chat 1")]
    assert set(listed[0]) == {"id", "notebook_id", "title", "created_at"}

    second = client.post(CONVERSATIONS, headers=AUTH)
    assert second.status_code == 201 and second.json()["title"] == "Chat 2"
    named = client.post(CONVERSATIONS, json={"title": " Setup questions "}, headers=AUTH).json()
    assert named["title"] == "Setup questions"
    assert client.post(CONVERSATIONS, json={}, headers=AUTH).json()["title"] == "Chat 3"

    # closing a tab deletes the conversation and its messages
    store.insert_message(NOTEBOOK, named["id"], "user", "q", None)
    assert client.delete(f"/api/rag/conversations/{named['id']}", headers=AUTH).status_code == 204
    assert messages(client, named["id"]).status_code == 404
    assert all(m["conversation_id"] != named["id"] for m in store.messages)
    titles = [c["title"] for c in client.get(CONVERSATIONS, headers=AUTH).json()]
    assert titles == ["Chat 1", "Chat 2", "Chat 3"]


def test_other_peoples_conversations_are_not_found(settings):
    store = FakeStore()
    theirs = store.create_conversation(OTHER_NOTEBOOK, "Chat 1")
    client = make_client(settings, store, FakeRetriever([chunk(1, "x")]), FakeLLM("x [1]."))
    assert messages(client, theirs.id).status_code == 404
    assert client.delete(f"/api/rag/conversations/{theirs.id}", headers=AUTH).status_code == 404
    other = f"/api/rag/notebooks/{OTHER_NOTEBOOK}/conversations"
    assert client.get(other, headers=AUTH).status_code == 404
    assert client.post(other, headers=AUTH).status_code == 404
    r = client.post(ASK, json={"conversation_id": theirs.id, "question": "q"}, headers=AUTH)
    assert (r.status_code, r.json()) == (404, {"error": "conversation not found"})


def test_ask_needs_a_conversation_and_writes_into_it(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([chunk(1, "x")]), FakeLLM("x [1]."))
    r = client.post(ASK, json={"question": "q"}, headers=AUTH)
    assert r.status_code == 422 and "conversation_id" in r.json()["error"]

    second = client.post(CONVERSATIONS, headers=AUTH).json()["id"]
    client.post(ASK, json={"conversation_id": second, "question": "q"}, headers=AUTH)
    assert [m["role"] for m in messages(client, second).json()] == ["user", "assistant"]
    assert messages(client, CONVERSATION).json() == []


def test_the_model_sees_this_conversations_history_without_old_markers(settings):
    store = FakeStore()
    llm = FakeLLM("VNC is remote desktop access [1].", "Install it with apt [1].")
    client = make_client(settings, store, FakeRetriever([chunk(1, "VNC text")]), llm)
    other = client.post(CONVERSATIONS, headers=AUTH).json()["id"]

    client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": "what is vnc?"}, headers=AUTH
    )
    assert "Conversation so far" not in llm.calls[0][1]
    client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": "how to install it?"}, headers=AUTH
    )
    prompt = llm.calls[1][1]
    assert prompt.startswith("Conversation so far:")
    assert "User: what is vnc?\nAssistant: VNC is remote desktop access." in prompt
    assert prompt.endswith("Question: how to install it?")

    client.post(
        ASK, json={"conversation_id": other, "question": "how to install it?"}, headers=AUTH
    )
    assert "Conversation so far" not in llm.calls[2][1]


def test_a_scoped_question_lands_in_the_current_conversation(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    row = store.create_output(NOTEBOOK, "report", "ready")
    source = store.create_generated_source(NOTEBOOK, "Report", "s")
    store.update_output(row.id, source_id=source)
    retriever = FakeRetriever([chunk(1, "report text", source_kind="generated")])
    client = make_client(settings, store, retriever, FakeLLM("It says so [1]."))
    tab = client.post(CONVERSATIONS, headers=AUTH).json()["id"]
    r = client.post(
        ASK,
        json={"conversation_id": tab, "question": "Summarize.", "scope": {"output_id": row.id}},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    assert len(messages(client, tab).json()) == 2
    assert messages(client, CONVERSATION).json() == []


def test_a_conversation_is_renamed_with_a_trimmed_title(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([chunk(1, "x")]), FakeLLM("x [1]."))
    url = f"/api/rag/conversations/{CONVERSATION}"
    r = client.patch(url, json={"title": "  Setup questions  "}, headers=AUTH)
    assert r.status_code == 200 and r.json()["title"] == "Setup questions"
    assert client.get(CONVERSATIONS, headers=AUTH).json()[0]["title"] == "Setup questions"
    assert client.patch(url, json={"title": "x" * 80}, headers=AUTH).status_code == 200
    for bad in ({"title": "   "}, {"title": "x" * 81}, {}):
        r = client.patch(url, json=bad, headers=AUTH)
        assert r.status_code == 422 and "title" in r.json()["error"]


def test_other_peoples_conversations_cannot_be_renamed(settings):
    store = FakeStore()
    theirs = store.create_conversation(OTHER_NOTEBOOK, "Chat 1")
    client = make_client(settings, store, FakeRetriever([chunk(1, "x")]), FakeLLM("x [1]."))
    r = client.patch(f"/api/rag/conversations/{theirs.id}", json={"title": "Mine"}, headers=AUTH)
    assert (r.status_code, r.json()) == (404, {"error": "conversation not found"})
    assert store.get_conversation(theirs.id).title == "Chat 1"
