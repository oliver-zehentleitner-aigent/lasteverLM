import json

import pytest

from lasteverlm_rag.models import Passage
from lasteverlm_rag.outputs import registry
from lasteverlm_rag.outputs._base import GenerationFailed, parse_json, render_material
from lasteverlm_rag.outputs.mindmap import MindmapGenerator
from lasteverlm_rag.outputs.quiz import QuizGenerator
from lasteverlm_rag.outputs.report import ReportGenerator
from lasteverlm_rag.outputs.table import TableGenerator

from .conftest import (
    AUTH,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    chunk,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
REPORT = json.dumps({"title": "Sky report", "markdown": "## Sky\n\nThe sky is blue."})
QUIZ = json.dumps(
    {
        "title": "Sky quiz",
        "questions": [
            {"question": "Color?", "options": ["blue", "red"], "answer": "blue", "explanation": "x"}
        ],
    }
)


# -- end to end: the API inserts the job, the worker runs it --


def test_report_end_to_end_is_generated_indexed_and_accounted(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    retriever = FakeRetriever([chunk(1, "The sky is blue.", page=1)])
    llm = FakeLLM(REPORT)
    client = make_client(settings, store, retriever, llm)

    r = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH)
    assert r.status_code == 202, r.text
    output_id = r.json()["id"]
    assert r.json()["status"] == "processing" and r.json()["source_id"] is None
    assert client.worker.run_once() == 1

    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert out["status"] == "ready", out
    assert out["title"] == "Sky report"
    assert out["content"] == {"markdown": "## Sky\n\nThe sky is blue."}
    assert out["error"] is None and out["share_token"] is None
    assert set(out) == {
        "id",
        "notebook_id",
        "kind",
        "title",
        "content",
        "status",
        "error",
        "share_token",
        "source_id",
        "options",
        "created_at",
    }
    # the generator saw the summaries and the focus-query passages
    prompt = llm.calls[0][1]
    assert "- sky.pdf: About the sky." in prompt and "[1] (doc1.pdf, page 1)" in prompt
    assert retriever.calls[0]["source_id"] is None
    # indexed as a ready generated source with embedded chunks
    generated = [s for s in store.sources.values() if s["kind"] == "generated"]
    assert len(generated) == 1 and generated[0]["status"] == "ready"
    assert generated[0]["name"] == "Sky report"
    assert generated[0]["summary"].startswith("Sky report ## Sky The sky is blue.")
    assert out["source_id"] == generated[0]["id"]
    assert len(store.chunks[generated[0]["id"]]) == 1
    # usage: focus-query embedding, generation, chunk embedding
    assert [u.kind for _, _, u in store.usage] == ["embedding", "llm", "embedding"]
    assert client.get(OUTPUTS, headers=AUTH).json()[0]["id"] == output_id


def test_output_waits_while_sources_process_then_runs_on_a_later_pass(settings):
    store = FakeStore()
    pending = store.add_source(NOTEBOOK, "slow.pdf", status="processing")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(QUIZ))

    r = client.post(OUTPUTS, json={"kind": "quiz"}, headers=AUTH)
    assert r.json()["status"] == "waiting"
    # not claimable while an uploaded source is processing: no attempt is spent
    assert client.worker.run_once() == 0
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "waiting"
    assert store.outputs[out["id"]]["attempts"] == 0

    store.sources[pending].update(status="ready", summary="done")
    assert client.worker.run_once() == 1
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready"
    assert out["content"]["questions"][0]["answer"] == "blue"
    assert store.outputs[out["id"]]["attempts"] == 1


def test_transient_failure_is_retried_and_the_third_attempt_fails_the_job(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")

    class FlakyLLM(FakeLLM):
        def complete(self, system, user, max_tokens=None, *, thinking=None):
            raise ConnectionError("inference endpoint unreachable")

    client = make_client(settings, store, FakeRetriever([]), FlakyLLM())
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]

    # a pass gives the job back once, then lets it rest; two passes = three attempts
    assert client.worker.run_once() == 0
    row = store.outputs[output_id]
    assert (row["status"], row["attempts"], row["claimed_by"]) == ("processing", 2, None)
    assert row["error"] == "inference endpoint unreachable"
    assert client.worker.run_once() == 1
    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert (out["status"], out["error"]) == ("failed", "inference endpoint unreachable")
    assert store.outputs[output_id]["attempts"] == 3
    assert not [s for s in store.sources.values() if s["kind"] == "generated"]


def test_output_fails_cleanly_and_leaves_no_half_indexed_source(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM("not json", "still not"))

    r = client.post(OUTPUTS, json={"kind": "table"}, headers=AUTH)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()

    # a schema failure is final on the first attempt: no retry burns more credit
    assert out["status"] == "failed"
    assert out["error"].startswith("table: model output did not match the schema")
    assert store.outputs[out["id"]]["attempts"] == 1
    assert not [s for s in store.sources.values() if s["kind"] == "generated"]


def test_empty_model_content_is_retried_as_a_provider_failure(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM("", "", REPORT))

    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    assert client.worker.run_once() == 0  # two attempts this pass, both empty, released
    row = store.outputs[output_id]
    assert (row["status"], row["attempts"]) == ("processing", 2)
    assert row["error"] == "report: the model returned no content"
    assert client.worker.run_once() == 1  # third attempt gets content
    assert client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()["status"] == "ready"


def test_output_without_ready_sources_fails(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "broken.pdf", status="failed")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(REPORT))

    r = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert (out["status"], out["error"]) == ("failed", "the notebook has no ready source")


AUDIO = json.dumps(
    {"title": "The sky, read aloud", "script": " ".join(f"Point {i} is told." for i in range(300))}
)


def test_audio_fails_without_tts_before_spending_tokens(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    llm = FakeLLM(AUDIO)
    client = make_client(settings, store, FakeRetriever([]), llm)
    r = client.post(OUTPUTS, json={"kind": "audio"}, headers=AUTH)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "failed" and "text-to-speech" in out["error"]
    assert llm.calls == []


def test_audio_is_synthesized_in_segments_stored_and_served_presigned(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    tts, objects = FakeTTS(), FakeObjects()
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(AUDIO), tts, objects)
    output_id = client.post(OUTPUTS, json={"kind": "audio"}, headers=AUTH).json()["id"]
    client.worker.run_once()

    key = f"{NOTEBOOK}/{output_id}/audio.mp3"
    assert store.outputs[output_id]["content"] == {"key": key}
    data, content_type = objects.objects[key]
    assert content_type == "audio/mpeg" and data.count(b"\xff\xf3") == len(tts.inputs) > 1
    tts_rows = [u for _, _, u in store.usage if u.kind == "tts"]
    assert [u.tokens_in for u in tts_rows] == [len(t) for t in tts.inputs]

    out = client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()
    assert out["status"] == "ready" and out["title"] == "The sky, read aloud"
    assert out["content"] == {"url": f"https://objects.test/{key}?expires=3600"}
    listed = client.get(OUTPUTS, headers=AUTH).json()
    assert listed[0]["content"] == out["content"]
    token = client.post(f"/api/rag/outputs/{output_id}/share", headers=AUTH).json()["share_token"]
    assert client.get(f"/api/rag/shared/{token}").json()["content"] == out["content"]

    assert client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH).status_code == 204
    assert objects.objects == {}


def test_audio_retries_a_failed_synthesis_without_leaving_a_file(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    objects = FakeObjects()
    client = make_client(
        settings, store, FakeRetriever([]), FakeLLM(AUDIO), FakeTTS(fail=True), objects
    )
    output_id = client.post(OUTPUTS, json={"kind": "audio"}, headers=AUTH).json()["id"]
    client.worker.run_once()
    row = store.outputs[output_id]
    assert row["status"] == "processing" and "speech request failed" in row["error"]
    assert objects.objects == {} and store.outputs[output_id]["source_id"] is None


def test_output_creation_needs_credit_and_a_known_kind(settings):
    client = make_client(settings, FakeStore(balance=0), FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH)
    assert (r.status_code, r.json()) == (402, {"error": "credit exhausted"})
    r = client.post(OUTPUTS, json={"kind": "poem"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["error"].startswith("kind:")


def test_delete_output_removes_its_generated_source(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(REPORT))
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    client.worker.run_once()
    assert any(s["kind"] == "generated" for s in store.sources.values())

    assert client.delete(f"/api/rag/outputs/{output_id}", headers=AUTH).status_code == 204

    assert not any(s["kind"] == "generated" for s in store.sources.values())
    assert client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).status_code == 404


def test_share_and_revoke(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(REPORT))
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    client.worker.run_once()

    token = client.post(f"/api/rag/outputs/{output_id}/share", headers=AUTH).json()["share_token"]
    assert len(token) >= 24
    # idempotent
    assert client.post(f"/api/rag/outputs/{output_id}/share", headers=AUTH).json() == {
        "share_token": token
    }
    shared = client.get(f"/api/rag/shared/{token}")
    assert shared.status_code == 200
    assert shared.json() == {
        "kind": "report",
        "title": "Sky report",
        "content": {"markdown": "## Sky\n\nThe sky is blue."},
        "options": {},
        "created_at": shared.json()["created_at"],
    }
    assert client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()["share_token"] == token

    assert client.delete(f"/api/rag/outputs/{output_id}/share", headers=AUTH).status_code == 204
    assert client.get(f"/api/rag/shared/{token}").status_code == 404
    assert client.get("/api/rag/shared/unknown").status_code == 404


def test_outputs_of_other_users_are_404(settings):
    store = FakeStore()
    theirs = store.create_output(OTHER_NOTEBOOK, "report", "ready")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    assert client.get(f"/api/rag/outputs/{theirs.id}", headers=AUTH).status_code == 404
    assert client.delete(f"/api/rag/outputs/{theirs.id}", headers=AUTH).status_code == 404
    assert client.post(f"/api/rag/outputs/{theirs.id}/share", headers=AUTH).status_code == 404
    assert (
        client.get(f"/api/rag/notebooks/{OTHER_NOTEBOOK}/outputs", headers=AUTH).status_code == 404
    )


# -- generators on their own --


def complete_with(*replies: str):
    llm = FakeLLM(*replies)
    return llm, llm.complete


def test_json_parsing_tolerates_fences_and_surrounding_text():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Here you go: {"a": [1, 2]} hope it helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        parse_json("no object here")


def test_generator_retries_once_with_the_validation_error():
    llm, complete = complete_with('{"title": "t"}', REPORT)
    out = ReportGenerator().generate(complete, "nb", [], [])
    assert out.title == "Sky report"
    assert len(llm.calls) == 2
    assert "Your previous answer was invalid" in llm.calls[1][1]
    llm, complete = complete_with("x", "y")
    with pytest.raises(GenerationFailed):
        ReportGenerator().generate(complete, "nb", [], [])


def test_quiz_requires_the_answer_among_the_options():
    bad = json.dumps(
        {"title": "q", "questions": [{"question": "?", "options": ["a", "b"], "answer": "c"}]}
    )
    _, complete = complete_with(bad, QUIZ)
    out = QuizGenerator().generate(complete, "nb", [], [])
    assert out.content["questions"][0]["answer"] == "blue"
    assert "Answer: blue. x" in out.index_text


def test_table_rows_must_match_columns_and_index_text_is_pipe_separated():
    bad = json.dumps({"title": "t", "columns": ["a", "b"], "rows": [["1"]]})
    good = json.dumps({"title": "t", "columns": ["a", "b"], "rows": [["1", "2"]]})
    _, complete = complete_with(bad, good)
    out = TableGenerator().generate(complete, "nb", [], [])
    assert out.content == {"columns": ["a", "b"], "rows": [["1", "2"]]}
    assert out.index_text == "t\n\na | b\n1 | 2"


def test_mindmap_index_text_is_an_outline():
    doc = json.dumps(
        {"title": "m", "root": {"label": "Root", "children": [{"label": "A", "children": []}]}}
    )
    _, complete = complete_with(doc)
    out = MindmapGenerator().generate(complete, "nb", [], [])
    assert out.content["root"]["children"][0]["label"] == "A"
    assert out.index_text == "m\n- Root\n  - A"


def test_registry_covers_every_kind():
    assert set(registry(tts_available=False)) == {
        "report",
        "quiz",
        "table",
        "mindmap",
        "infographic",
        "audio",
    }


def test_generators_are_told_not_to_reuse_the_notebook_name_as_title():
    from lasteverlm_rag.outputs._base import system_rules

    assert "never reuse the notebook's name" in system_rules(None)


def test_render_material_lists_summaries_and_numbered_passages():
    passage = Passage(1, "c", "s", "doc.pdf", "pdf", 4, "text")
    text = render_material("NB", [], [passage])
    assert text.startswith('Notebook: "NB"')
    assert "[1] (doc.pdf, page 4)\ntext" in text


def test_worker_pass_handles_all_runnable_jobs_and_stops(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "a.txt", summary="s")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(REPORT))
    for _ in range(3):
        client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH)
    assert client.worker.run_once() == 3
    assert client.worker.run_once() == 0
    assert all(o["status"] == "ready" for o in store.outputs.values())
