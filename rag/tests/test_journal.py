"""A job that another worker takes over (a retry, a handover, a stale claim)
answers the model calls an earlier attempt finished from the output's
journal: nothing is called or booked twice, and the journal goes once the
output is ready."""

import json

from lasteverlm_core import CompletionResult, ProviderError, Usage

from lasteverlm_rag import journal
from lasteverlm_rag.journal import Journal

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, make_client
from .test_judging import SKY, judges, report, revision

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
DRAFT = report("The sky is blue. [1]", "The sky is wrong green. [1]")
REVISED = revision({"index": 1, "action": "revise", "unit": {"text": "Grass is green. [1]"}})


class FlakyLLM(FakeLLM):
    """FakeLLM whose ``fail_at``-th call fails once, as a provider would."""

    def __init__(self, *replies, fail_at):
        super().__init__(*replies)
        self.fail_at = fail_at
        self.made = 0

    def complete(self, system, user, max_tokens=None, *, thinking=None):
        self.made += 1
        if self.made == self.fail_at:
            raise ProviderError("completion request failed")
        return super().complete(system, user, max_tokens, thinking=thinking)


def judged_report(settings, llm):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    judge_models = judges()
    client = make_client(settings, store, FakeRetriever([SKY]), llm, judges=judge_models)
    r = client.post(OUTPUTS, json={"kind": "report", "options": {"judge": "low"}}, headers=AUTH)
    return store, judge_models, client, r.json()["id"]


def booked(store, model):
    return [u for _, _, u in store.usage if u.model == model]


def test_a_retry_resumes_after_the_draft_and_the_first_round(settings):
    # the draft and round 1's two verdicts are made, then the revision fails
    llm = FlakyLLM(DRAFT, REVISED, fail_at=2)
    store, judge_models, client, output_id = judged_report(settings, llm)
    client.worker.run_once()  # the attempt fails at the revision; the retry follows
    row = store.outputs[output_id]
    assert row["status"] == "ready", row["error"]
    assert row["attempts"] == 2 and row["attempt_log"][0]["attempt"] == 1
    # the draft was written once; the second attempt made only the revision
    assert len(llm.calls) == 2 and "correct parts of a document" in llm.calls[1][0]
    # round 1 was not judged again: only the revised unit was
    assert judge_models["low"].statements == [
        "The sky is blue.",
        "The sky is wrong green.",
        "Grass is green.",
    ]
    # one usage row per call made, none for what the journal answered
    assert len(booked(store, "test-llm")) == 2
    assert len(booked(store, "test-judge-low")) == 3
    # the log still counts every call of the output, the first attempt's included
    judge_log = row["provenance"]["judge"]
    assert [r["judged"] for r in judge_log["rounds"]] == [2, 1]
    assert row["provenance"]["usage"]["judge"] == {"tokens_in": 360, "tokens_out": 45}
    assert row["checkpoint"] == {}  # done with the job: the journal goes


def test_a_handed_over_job_resumes_on_the_next_worker_from_the_journal(settings):
    llm = FakeLLM(DRAFT, REVISED)
    store, judge_models, client, output_id = judged_report(settings, llm)
    outputs = client.worker._outputs
    judge = judge_models["low"]
    complete = judge.complete

    def stopping(*args, **kwargs):
        result = complete(*args, **kwargs)
        outputs.hand_over_after(0)  # SIGTERM with no grace left, after the first verdict
        return result

    judge.complete = stopping
    job = store.claim_output("w1", 600)
    assert outputs.process(job, "w1") is False  # handed over before its next call
    assert store.outputs[output_id]["claimed_by"] is None
    # the focus embedding, the draft and the verdicts made before the handover
    assert len(store.outputs[output_id]["checkpoint"]) >= 3

    judge.complete = complete
    outputs._handover_at = None  # the next worker's process
    job = store.claim_output("w2", 600)
    assert outputs.process(job, "w2") is True
    row = store.outputs[output_id]
    assert row["status"] == "ready" and row["attempts"] == 1
    assert len(llm.calls) == 2  # the draft once, then the revision
    # each verdict was made once, on one worker or the other
    assert sorted(judge.statements) == [
        "Grass is green.",
        "The sky is blue.",
        "The sky is wrong green.",
    ]
    assert len(booked(store, "test-judge-low")) == 3 and len(booked(store, "test-llm")) == 2
    assert len(booked(store, "test-embedding")) == 2  # the focus query once, the index once


def test_the_same_request_twice_in_one_run_is_two_calls():
    store = FakeStore()
    store.outputs["o"] = {"claimed_by": "w1", "checkpoint": {}}
    first = Journal(store, "o", "w1", {})
    replies = iter(["one", "two", "three"])

    def call():
        return CompletionResult(next(replies), Usage("llm", "m", 1, 1))

    assert first.complete(["m", "s", "u"], call)[0].text == "one"
    assert first.complete(["m", "s", "u"], call)[0].text == "two"  # a deliberate retry
    # a later attempt answers both from the journal, in the same order
    again = Journal(store, "o", "w1", store.get_checkpoint("o"))
    assert [again.complete(["m", "s", "u"], call)[0].text for _ in range(2)] == ["one", "two"]
    assert again.replayed == 2
    assert again.complete(["m", "s", "u"], call)[0].text == "three"  # a third is new


def test_a_journal_write_counts_only_while_the_claim_is_held_and_stays_small(monkeypatch):
    store = FakeStore()
    store.outputs["o"] = {"claimed_by": "w2", "checkpoint": {}}
    lost = Journal(store, "o", "w1", {})
    lost.complete(["m", "s", "u"], lambda: CompletionResult("x", Usage("llm", "m", 1, 1)))
    assert store.outputs["o"]["checkpoint"] == {}  # w1 lost the claim: nothing kept

    monkeypatch.setattr(journal, "ENTRY_MAX_BYTES", 300)
    held = Journal(store, "o", "w2", {})
    big = "x" * 400
    result, replayed = held.complete(
        ["m", "s", "big"], lambda: CompletionResult(big, Usage("llm", "m", 1, 1))
    )
    assert result.text == big and not replayed  # used, just not kept
    held.complete(["m", "s", "small"], lambda: CompletionResult("y", Usage("llm", "m", 1, 1)))
    assert [
        json.loads(json.dumps(e))["text"] for e in store.outputs["o"]["checkpoint"].values()
    ] == ["y"]
