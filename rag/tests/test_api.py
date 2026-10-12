import jwt
import pytest

from lasteverlm_rag.config import ConfigError, Settings
from lasteverlm_rag.contracts import DEMO_USER_ID, AuthError, verify_token
from lasteverlm_rag.service import REFUSAL

from .conftest import (
    AUTH,
    BASE_ENV,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"
MESSAGES = f"/api/rag/notebooks/{NOTEBOOK}/messages"


def test_healthz_needs_no_auth_at_root_and_under_prefix(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    assert client.get("/api/rag/healthz").json() == {"status": "ok"}
    assert client.get("/healthz").json() == {"status": "ok"}


def test_ask_returns_cited_answer_persists_messages_and_accounts_usage(settings):
    store = FakeStore()
    retriever = FakeRetriever([chunk(1, "The sky is blue.", page=2), chunk(2, "Grass is green.")])
    llm = FakeLLM("The sky is blue [1]. Grass is green [2].")
    client = make_client(settings, store, retriever, llm)

    r = client.post(ASK, json={"question": " colors? "}, headers=AUTH)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "The sky is blue [1]. Grass is green [2]."
    assert [c["n"] for c in body["citations"]] == [1, 2]
    assert body["citations"][0] == {
        "n": 1,
        "source_id": "source-1",
        "source_name": "doc1.pdf",
        "source_kind": "pdf",
        "chunk_id": "chunk-1",
        "page": 2,
        "quote": "The sky is blue.",
    }
    # the question was stripped and the LLM saw the numbered passages
    assert llm.calls[0][1].endswith("Question: colors?")
    assert "[1] (doc1.pdf, page 2)" in llm.calls[0][1]
    # retrieval is scoped to the notebook with the configured parameters, unscoped by source
    assert retriever.calls[0] == {"notebook_id": NOTEBOOK, "k": 3, "floor": 0.5, "source_id": None}
    # both messages stored, the assistant one carries the citations
    assert [m["role"] for m in store.messages] == ["user", "assistant"]
    assert store.messages[1]["id"] == body["message_id"]
    assert store.messages[1]["citations"][0]["chunk_id"] == "chunk-1"
    # one usage row per provider call, attributed to the user and notebook
    assert [(u.kind, u.tokens_in, u.tokens_out) for _, _, u in store.usage] == [
        ("embedding", 7, 0),
        ("llm", 50, 20),
    ]
    assert all((user, nb) == (DEMO_USER_ID, NOTEBOOK) for user, nb, _ in store.usage)


def test_ask_refuses_when_nothing_passes_the_floor(settings):
    store = FakeStore()
    llm = FakeLLM("should never be called")
    client = make_client(settings, store, FakeRetriever([chunk(1, "x", similarity=0.2)]), llm)

    body = client.post(ASK, json={"question": "x"}, headers=AUTH).json()

    assert body["answer"] == REFUSAL
    assert body["citations"] == []
    assert llm.calls == []
    assert [m["role"] for m in store.messages] == ["user", "assistant"]
    assert [u.kind for _, _, u in store.usage] == ["embedding"]


def test_ask_is_402_without_credit_and_calls_no_provider(settings):
    store = FakeStore(balance=0)
    llm = FakeLLM("never")
    client = make_client(settings, store, FakeRetriever([chunk(1, "fact")]), llm)

    r = client.post(ASK, json={"question": "q"}, headers=AUTH)

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

    r = client.post(ASK, json={"question": "q", "scope": {"output_id": row.id}}, headers=AUTH)

    assert r.status_code == 200, r.text
    assert retriever.calls[0]["source_id"] == generated
    assert r.json()["citations"] == [] or r.json()["citations"][0]["source_kind"] == "generated"


def test_ask_scope_errors(settings):
    store = FakeStore()
    pending = store.create_output(NOTEBOOK, "quiz", "processing")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())

    r = client.post(ASK, json={"question": "q", "scope": {"output_id": pending.id}}, headers=AUTH)
    assert (r.status_code, r.json()) == (409, {"error": "output is not ready"})

    r = client.post(ASK, json={"question": "q", "scope": {"output_id": "nope"}}, headers=AUTH)
    assert (r.status_code, r.json()) == (404, {"error": "output not found"})


def test_messages_lists_history_in_order(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([chunk(1, "fact")]), FakeLLM("fact [1]"))
    client.post(ASK, json={"question": "q"}, headers=AUTH)

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
        json={"question": "q"},
        headers=AUTH,
    )
    assert r.status_code == 404
    assert r.json() == {"error": "notebook not found"}


def test_validation_errors_use_the_error_shape(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.post(ASK, json={"question": ""}, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"].startswith("question:")
    r = client.post("/api/rag/notebooks/not-a-uuid/ask", json={"question": "q"}, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"].startswith("path.notebook_id:")


def test_jwt_is_tried_before_demo_token():
    token = jwt.encode({"sub": "user-42", "aud": "authenticated"}, "jwt-secret", algorithm="HS256")
    assert verify_token(token, "jwt-secret", "demo") == "user-42"
    assert verify_token("demo", "jwt-secret", "demo") == DEMO_USER_ID
    bad = jwt.encode({"sub": "user-42", "aud": "authenticated"}, "other", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(bad, "jwt-secret", "demo")
    with pytest.raises(AuthError):
        verify_token("demo", None, None)


@pytest.mark.parametrize(
    "missing", ["DATABASE_URL", "INFERENCE_BASE_URL", "LLM_MODEL", "EMBEDDING_MODEL"]
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
    with pytest.raises(ConfigError, match="EMBEDDING_DIMENSION"):
        Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "EMBEDDING_DIMENSION": "0"})
    s = Settings.from_env({**BASE_ENV, "DEMO_TOKEN": "d", "INFERENCE_BASE_URL": "https://x/v1/"})
    assert s.inference_base_url == "https://x/v1"
    assert s.embedding_dimension == 1536
    assert s.tts_model is None
