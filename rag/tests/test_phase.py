"""What a running output is doing: the steps the worker really took, in order."""

import json

from .conftest import (
    AUTH,
    NOTEBOOK,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    chunk,
    make_client,
)
from .test_judging import judges, report, revision

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day.")


def steps(store, output_id):
    return [
        (p["step"], *(p[k] for k in ("n", "of") if k in p)) for p in store.phases.get(output_id, [])
    ]


def test_a_judged_report_goes_through_its_real_steps_in_order(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    client = make_client(
        settings,
        store,
        FakeRetriever([SKY]),
        FakeLLM(
            report("The sky is blue. [1]", "The sky is wrong green. [1]"),
            revision({"index": 1, "action": "revise", "unit": {"text": "Grass is green. [1]"}}),
        ),
        judges=judges(),
    )
    output_id = client.post(
        OUTPUTS, json={"kind": "report", "options": {"judge": "low"}}, headers=AUTH
    ).json()["id"]
    client.worker.run_once()
    assert steps(store, output_id) == [
        ("retrieving",),
        ("writing",),
        ("checking",),
        ("judging", 1, 3),
        ("revising", 1),
        ("judging", 2, 3),
        ("indexing",),
    ]
    since = [p["since"] for p in store.phases[output_id]]
    assert since == sorted(since)
    # done: the phase is cleared
    assert store.outputs[output_id]["phase"] is None
    assert store.outputs[output_id]["status"] == "ready"


def test_audio_counts_its_speech_segments(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    script = json.dumps(
        {"title": "A", "paragraphs": [{"text": "One. " * 300}, {"text": "Two. " * 300}]}
    )
    client = make_client(
        settings, store, FakeRetriever([SKY]), FakeLLM(script), FakeTTS(), FakeObjects()
    )
    output_id = client.post(OUTPUTS, json={"kind": "audio"}, headers=AUTH).json()["id"]
    client.worker.run_once()
    seen = steps(store, output_id)
    assert seen[:3] == [("retrieving",), ("writing",), ("checking",)]
    speech = [s for s in seen if s[0] == "synthesizing_speech"]
    assert speech[0] == ("synthesizing_speech", 1, speech[0][2]) and speech[0][2] > 1
    assert seen[-1] == ("indexing",)
    assert all(step[0] != "judging" for step in seen)  # no judge, no judging step


def test_a_failed_attempt_shows_the_retry_and_a_final_failure_clears_it(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    client = make_client(settings, store, FakeRetriever([SKY]), FakeLLM(""))
    output_id = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()["id"]
    client.worker.run_once()  # two attempts, released
    phase = store.outputs[output_id]["phase"]
    assert (phase["step"], phase["n"], phase["of"]) == ("retry", 3, 3)
    assert phase["error"] == "test-llm: empty answer"
    client.worker.run_once()
    assert store.outputs[output_id]["status"] == "failed"
    assert store.outputs[output_id]["phase"] is None


def test_the_api_shows_the_phase_only_while_an_output_runs(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "slow.pdf", status="processing")
    client = make_client(settings, store, FakeRetriever([SKY]), FakeLLM(report("Sky. [1]")))
    created = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH).json()
    phase = created["phase"]
    assert (phase["step"], phase["sources"]) == ("waiting_for_sources", ["slow.pdf"])
    listed = client.get(OUTPUTS, headers=AUTH).json()[0]["phase"]
    assert listed["step"] == "waiting_for_sources"

    row = store.outputs[created["id"]]
    row.update(status="processing", phase={"step": "writing", "since": "2026-10-15T10:00:00+00:00"})
    out = client.get(f"/api/rag/outputs/{created['id']}", headers=AUTH).json()
    assert out["phase"] == {"step": "writing", "since": "2026-10-15T10:00:00+00:00"}

    row.update(status="ready")  # a finished row's last phase is never shown
    assert client.get(f"/api/rag/outputs/{created['id']}", headers=AUTH).json()["phase"] is None
