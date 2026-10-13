import uuid

import pytest
from lasteverlm_core import DEMO_USER_ID, ConfigError, issue_jwt

from lasteverlm_rag.config import Settings
from lasteverlm_rag.service import REFUSAL

from .conftest import (
    AUTH,
    BASE_ENV,
    CHUNK_1,
    CONVERSATION,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    SOURCE_1,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"
MESSAGES = f"/api/rag/conversations/{CONVERSATION}/messages"


def test_healthz_needs_no_auth_and_reports_the_build(settings, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "0.6.1")
    monkeypatch.setenv("APP_COMMIT", "abc1234")
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    build = {"status": "ok", "version": "0.6.1", "commit": "abc1234"}
    assert client.get("/api/rag/healthz").json() == build
    assert client.get("/healthz").json() == build


def test_healthz_without_build_labels_says_unknown(settings, monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("APP_COMMIT", " ")
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get("/healthz").json() == {
        "status": "ok",
        "version": "unknown",
        "commit": "unknown",
    }


def test_ask_returns_cited_answer_persists_messages_and_accounts_usage(settings):
    store = FakeStore()
    retriever = FakeRetriever(
        [
            chunk(1, "The sky is blue.", page=2, similarity=0.81234, chunk_index=4, chunk_count=9),
            chunk(2, "Grass is green."),
        ]
    )
    llm = FakeLLM("The sky is blue [1]. Grass is green [2].")
    client = make_client(settings, store, retriever, llm)

    r = client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": " colors? "}, headers=AUTH
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "The sky is blue [1]. Grass is green [2]."
    assert [c["n"] for c in body["citations"]] == [1, 2]
    assert body["citations"][0] == {
        "n": 1,
        "source_id": SOURCE_1,
        "source_name": "doc1.pdf",
        "source_kind": "pdf",
        "chunk_id": CHUNK_1,
        "page": 2,
        "quote": "The sky is blue.",
        "similarity": 0.812,
        "chunk_index": 4,
        "chunk_count": 9,
    }
    # the persisted assistant message carries the same provenance
    assert store.messages[1]["citations"][0]["similarity"] == 0.812
    assert store.messages[1]["citations"][0]["chunk_count"] == 9
    # the question was stripped and the LLM saw the numbered passages
    assert llm.calls[0][1].endswith("Question: colors?")
    assert "[1] (doc1.pdf, page 2)" in llm.calls[0][1]
    # retrieval is scoped to the notebook with the configured parameters, unscoped by source
    assert retriever.calls[0] == {
        "notebook_id": NOTEBOOK,
        "k": 3,
        "floor": 0.5,
        "source_id": None,
        "include_generated": False,
    }
    # both messages stored, the assistant one carries the citations
    assert [m["role"] for m in store.messages] == ["user", "assistant"]
    assert store.messages[1]["id"] == body["message_id"]
    assert store.messages[1]["citations"][0]["chunk_id"] == CHUNK_1
    # one usage row per provider call, attributed to the user and notebook
    assert [(u.kind, u.tokens_in, u.tokens_out) for _, _, u in store.usage] == [
        ("embedding", 7, 0),
        ("llm", 50, 20),
    ]
    assert all((user, nb) == (str(DEMO_USER_ID), NOTEBOOK) for user, nb, _ in store.usage)


def test_ask_with_empty_model_content_is_a_502_and_stores_nothing(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([chunk(1, "fact")]), FakeLLM("  \n"))

    r = client.post(ASK, json={"conversation_id": CONVERSATION, "question": "q"}, headers=AUTH)

    assert r.status_code == 502
    assert r.json() == {"error": "the model did not answer; please try again"}
    assert store.messages == []
    assert [u.kind for _, _, u in store.usage] == ["embedding", "llm"]  # the tokens were spent


def test_ask_refuses_when_nothing_passes_the_floor(settings):
    store = FakeStore()
    llm = FakeLLM("should never be called")
    client = make_client(settings, store, FakeRetriever([chunk(1, "x", similarity=0.2)]), llm)

    body = client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": "x"}, headers=AUTH
    ).json()

    assert body["answer"] == REFUSAL
    assert body["citations"] == []
    assert llm.calls == []
    assert [m["role"] for m in store.messages] == ["user", "assistant"]
    assert [u.kind for _, _, u in store.usage] == ["embedding"]


def test_ask_is_402_without_credit_and_calls_no_provider(settings):
    store = FakeStore(balance=0)
    llm = FakeLLM("never")
    client = make_client(settings, store, FakeRetriever([chunk(1, "fact")]), llm)

    r = client.post(ASK, json={"conversation_id": CONVERSATION, "question": "q"}, headers=AUTH)

    assert r.status_code == 402
    assert r.json() == {"error": "credit exhausted"}
    assert llm.calls == [] and store.usage == [] and store.messages == []


def test_ask_scoped_to_an_output_restricts_retrieval_to_its_generated_source(settings):
    store = FakeStore()
    generated = store.add_source(NOTEBOOK, "Report", kind="generated")
    row = store.create_output(NOTEBOOK, "report", "processing")
    store.update_output(row.id, status="ready", source_id=generated)
    hits = [chunk(1, "from the pdf"), chunk(2, "from the report", source_kind="generated")]
    hits[1] = hits[1].__class__(**{**hits[1].__dict__, "source_id": generated})
    retriever = FakeRetriever(hits)
    client = make_client(settings, store, retriever, FakeLLM("Says so [1]."))

    r = client.post(
        ASK,
        json={"conversation_id": CONVERSATION, "question": "q", "scope": {"output_id": row.id}},
        headers=AUTH,
    )

    assert r.status_code == 200, r.text
    # scoped: that one source, no similarity floor, a larger k
    assert retriever.calls[0]["source_id"] == generated
    assert (retriever.calls[0]["floor"], retriever.calls[0]["k"]) == (0.0, 12)
    assert [c["source_kind"] for c in r.json()["citations"]] == ["generated"]


def test_scoped_summary_question_is_answered_even_when_nothing_matches_strongly(settings):
    store = FakeStore()
    generated = store.add_source(NOTEBOOK, "Report", kind="generated")
    row = store.create_output(NOTEBOOK, "report", "processing")
    store.update_output(row.id, status="ready", source_id=generated)
    weak = chunk(1, "the whole report", similarity=0.1, source_kind="generated")
    weak = weak.__class__(**{**weak.__dict__, "source_id": generated})
    client = make_client(settings, store, FakeRetriever([weak]), FakeLLM("One sentence [1]."))

    scoped = client.post(
        ASK,
        json={
            "conversation_id": CONVERSATION,
            "question": "Summarize this document.",
            "scope": {"output_id": row.id},
        },
        headers=AUTH,
    ).json()
    assert scoped["answer"] == "One sentence [1]." and len(scoped["citations"]) == 1
    # the same chunk is below the floor for an unscoped question
    assert (
        client.post(
            ASK, json={"conversation_id": CONVERSATION, "question": "Summarize."}, headers=AUTH
        ).json()["citations"]
        == []
    )


def test_unscoped_ask_leaves_generated_documents_out_unless_configured(settings):
    hits = [
        chunk(1, "from the pdf", similarity=0.8),
        chunk(2, "from a report", source_kind="generated"),
    ]
    retriever = FakeRetriever(hits)
    client = make_client(settings, FakeStore(), retriever, FakeLLM("Only the upload [1]."))
    body = client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": "q"}, headers=AUTH
    ).json()
    assert [c["source_kind"] for c in body["citations"]] == ["pdf"]
    assert retriever.calls[0]["include_generated"] is False

    on = Settings.from_env(
        {**BASE_ENV, "DEMO_TOKEN": "demo-secret", "RETRIEVAL_INCLUDE_GENERATED": "true"}
    )
    retriever = FakeRetriever(hits)
    client = make_client(on, FakeStore(), retriever, FakeLLM("Both [1] [2]."))
    body = client.post(
        ASK, json={"conversation_id": CONVERSATION, "question": "q"}, headers=AUTH
    ).json()
    assert [c["source_kind"] for c in body["citations"]] == ["pdf", "generated"]
    assert retriever.calls[0]["include_generated"] is True
    with pytest.raises(ConfigError, match="RETRIEVAL_INCLUDE_GENERATED"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "RETRIEVAL_INCLUDE_GENERATED": "maybe"})


def test_ask_scope_errors(settings):
    store = FakeStore()
    pending = store.create_output(NOTEBOOK, "quiz", "processing")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())

    r = client.post(
        ASK,
        json={"conversation_id": CONVERSATION, "question": "q", "scope": {"output_id": pending.id}},
        headers=AUTH,
    )
    assert (r.status_code, r.json()) == (409, {"error": "output is not ready"})

    r = client.post(
        ASK,
        json={"conversation_id": CONVERSATION, "question": "q", "scope": {"output_id": "nope"}},
        headers=AUTH,
    )
    assert (r.status_code, r.json()) == (404, {"error": "output not found"})


def test_messages_lists_history_in_order(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([chunk(1, "fact")]), FakeLLM("fact [1]"))
    client.post(ASK, json={"conversation_id": CONVERSATION, "question": "q"}, headers=AUTH)

    r = client.get(MESSAGES, headers=AUTH)

    assert r.status_code == 200
    assert [m["role"] for m in r.json()] == ["user", "assistant"]
    assert r.json()[1]["citations"][0]["n"] == 1


def test_missing_or_wrong_token_is_401(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get(MESSAGES).status_code == 401
    r = client.get(MESSAGES, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json() == {"error": "invalid bearer token"}


def test_foreign_or_unknown_notebook_is_404(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    foreign = client.get(f"/api/rag/notebooks/{OTHER_NOTEBOOK}/messages", headers=AUTH)
    assert foreign.status_code == 404
    r = client.post(
        "/api/rag/notebooks/00000000-0000-4000-8000-00000000dead/ask",
        json={"conversation_id": CONVERSATION, "question": "q"},
        headers=AUTH,
    )
    assert r.status_code == 404
    assert r.json() == {"error": "notebook not found"}


def test_validation_errors_use_the_error_shape(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.post(ASK, json={"conversation_id": CONVERSATION, "question": ""}, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"].startswith("question:")
    r = client.post(
        "/api/rag/notebooks/not-a-uuid/ask",
        json={"conversation_id": CONVERSATION, "question": "q"},
        headers=AUTH,
    )
    assert r.status_code == 422
    assert r.json()["error"].startswith("path.notebook_id:")


def test_session_jwt_from_the_account_service_is_accepted(settings):
    """Auth itself is core's; this checks the wiring: a JWT resolves to its user."""
    store = FakeStore()
    user = uuid.uuid4()
    store.notebooks[NOTEBOOK]["owner"] = str(user)
    s = Settings.from_env({**BASE_ENV, "AUTH_JWT_SECRET": "jwt-secret", "DEMO_TOKEN": "demo"})
    client = make_client(s, store, FakeRetriever([]), FakeLLM())
    token = issue_jwt(user, "jwt-secret")

    assert client.get(MESSAGES, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # the demo user does not own this notebook any more
    assert client.get(MESSAGES, headers={"Authorization": "Bearer demo"}).status_code == 404
    wrong = issue_jwt(user, "other-secret")
    assert client.get(MESSAGES, headers={"Authorization": f"Bearer {wrong}"}).status_code == 401


def test_rate_limit_middleware_is_wired(settings):
    s = Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "demo", "RATE_LIMIT_PER_MINUTE": "2"})
    client = make_client(s, FakeStore(), FakeRetriever([]), FakeLLM())
    codes = [
        client.get(MESSAGES, headers={"Authorization": "Bearer demo"}).status_code for _ in range(3)
    ]
    assert codes == [200, 200, 429]


@pytest.mark.parametrize(
    "missing", ["DATABASE_URL", "INFERENCE_API_KEY", "LLM_MODEL", "EMBEDDING_MODEL"]
)
def test_settings_fail_loud_on_missing_values(missing):
    env = {**BASE_ENV, "DEMO_TOKEN": "d"}
    env.pop(missing)
    with pytest.raises(ConfigError, match=missing):
        Settings.from_env(env)


def test_settings_require_one_auth_scheme_and_sane_numbers():
    with pytest.raises(ConfigError, match="AUTH_JWT_SECRET or DEMO_TOKEN"):
        Settings.from_env(BASE_ENV)
    with pytest.raises(ConfigError, match="SIMILARITY_FLOOR"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "SIMILARITY_FLOOR": "1.5"})
    with pytest.raises(ConfigError, match="RETRIEVAL_K"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "RETRIEVAL_K": "0"})
    s = Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d"})
    assert s.inference.embedding_dimension == 1536
    assert s.tts_model is None and s.tts_voice == "ryan" and s.s3 is None
    assert s.auth.demo_token == "d" and s.auth.jwt_secret is None


def test_audio_settings_need_object_storage():
    prices = '{"test-llm": {"in": 1, "out": 1}, "test-embedding": {"in": 1, "out": 0}, '
    prices += '"test-tts": {"in": 1, "out": 0}}'
    env = {**BASE_ENV, "DEMO_TOKEN": "d", "MODEL_PRICES": prices, "TTS_MODEL": "test-tts"}
    with pytest.raises(ConfigError, match="S3_ENDPOINT"):
        Settings.from_env(env)
    s3 = {
        "S3_ENDPOINT": "https://objects.test",
        "S3_BUCKET": "b",
        "S3_ACCESS_KEY": "a",
        "S3_SECRET_KEY": "s",
    }
    s = Settings.from_env({**env, **s3, "TTS_VOICE": "serena"})
    assert s.tts_voice == "serena" and s.s3 is not None and s.s3.bucket == "b"
