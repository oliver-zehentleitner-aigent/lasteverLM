"""Every failed attempt is kept on the output, and an admin finds an output
by the start of its id: support has the history after any deploy."""

from .conftest import (
    AUTH,
    NOTEBOOK,
    OWNER,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
FIND = "/api/rag/admin/outputs"


def failing(settings, **roles):
    store = FakeStore(**roles)
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    store.emails[OWNER] = "ada@example.org"
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(""))
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    for _ in range(3):
        client.worker.run_once()
    return store, client, output_id


def test_every_failed_attempt_is_kept_on_the_output(settings):
    store, _, output_id = failing(settings)
    row = store.outputs[output_id]
    assert row["status"] == "failed" and row["finished_at"]
    log = row["attempt_log"]
    assert [a["attempt"] for a in log] == [1, 2, 3]
    first = log[0]
    assert set(first) == {
        "at",
        "attempt",
        "model",
        "error_kind",
        "provider_status",
        "message",
        "service",
    }
    assert (first["model"], first["error_kind"], first["provider_status"], first["service"]) == (
        "test-llm",
        "provider",
        None,
        "rag",
    )
    assert first["message"] == "report: the model returned no content"
    # never the prompt or the source text
    assert "About the sky." not in str(log)


def test_an_admin_finds_an_output_by_its_short_id_with_the_full_email(settings):
    _, client, output_id = failing(settings, admins={OWNER})
    for prefix in (output_id[:8], output_id[:8].upper(), output_id[:13]):
        r = client.get(FIND, params={"id_prefix": prefix}, headers=AUTH)
        assert r.status_code == 200, r.text
        (match,) = r.json()["matches"]
        assert match["id"] == output_id and r.json()["truncated"] is False
    assert match["owner"] == {"id": OWNER, "email": "ada@example.org"}
    assert match["status"] == "failed" and match["finished_at"] and match["attempts"] == 3
    assert [a["attempt"] for a in match["attempt_log"]] == [1, 2, 3]
    assert match["notebook_id"] == NOTEBOOK and match["kind"] == "report"


def test_a_viewer_sees_the_owner_masked(settings):
    _, client, output_id = failing(settings, viewers={OWNER})
    (match,) = client.get(FIND, params={"id_prefix": output_id[:8]}, headers=AUTH).json()["matches"]
    assert match["owner"] == {"id": OWNER, "email": "a***a@example.org"}


def test_the_prefix_is_checked_and_the_matches_capped(settings):
    store = FakeStore(admins={OWNER})
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    for bad in ("3f9c2", "zzzzzz", "3f9c21ab" * 5):
        r = client.get(FIND, params={"id_prefix": bad}, headers=AUTH)
        assert (r.status_code, r.json()) == (422, {"error": "id_prefix: at least 6 hex characters"})
    r = client.get(FIND, params={"id_prefix": "000000"}, headers=AUTH)
    assert r.json() == {"matches": [], "truncated": False}
    rows = [store.create_output(NOTEBOOK, "report", "processing") for _ in range(25)]
    for i, row in enumerate(rows):  # one shared prefix, newest last
        new_id = f"abcdef{i:02x}-0000-4000-8000-000000000000"
        store.outputs[new_id] = {**store.outputs.pop(row.id), "id": new_id}
    body = client.get(FIND, params={"id_prefix": "abcdef"}, headers=AUTH).json()
    assert len(body["matches"]) == 20 and body["truncated"] is True
    assert body["matches"][0]["id"].startswith("abcdef18")  # newest first


def test_a_plain_user_cannot_search(settings):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.get(FIND, params={"id_prefix": "abcdef"}, headers=AUTH)
    assert (r.status_code, r.json()) == (403, {"error": "admin only"})


def test_the_owner_sees_the_attempts_on_the_output(settings):
    _, client, output_id = failing(settings)
    body = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert [a["attempt"] for a in body["attempt_log"]] == [1, 2, 3]
    assert body["attempt_log"][0]["error_kind"] == "provider"
