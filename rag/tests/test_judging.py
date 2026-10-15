"""The judge in generation (rounds, revision, removal) and on request
(an output, a chat answer)."""

import json
import threading

import pytest
from lasteverlm_core import CompletionResult, Usage

from lasteverlm_rag.judging import stored_units
from lasteverlm_rag.models import Passage
from lasteverlm_rag.outputs import registry
from lasteverlm_rag.outputs.mindmap import Mindmap, MindmapGenerator
from lasteverlm_rag.outputs.report import Report, ReportGenerator
from lasteverlm_rag.outputs.table import Table, TableGenerator
from lasteverlm_rag.provenance import check_units

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    FakeDecision,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day. Grass is green in spring.")


class RuleJudge:
    """A judge model that decides by keyword in the statement: "wrong" is
    contradicted, "missing" is not in the source, anything else supported;
    ``broken`` answers without JSON."""

    def __init__(self, model: str, broken: bool = False) -> None:
        self.model = model
        self.broken = broken
        self.statements: list[str] = []
        self._lock = threading.Lock()

    def complete(self, system, user, max_tokens=None, *, thinking=None):
        statement = user.split("\n")[1]
        with self._lock:
            self.statements.append(statement)
        if "wrong" in statement:
            verdict = "contradicted"
        elif "missing" in statement:
            verdict = "not_in_source"
        else:
            verdict = "supported"
        reply = (
            "not json"
            if self.broken
            else json.dumps(
                {"verdict": verdict, "reason": f"{verdict} by rule", "quote": "The sky is blue"}
            )
        )
        return CompletionResult(reply, Usage("llm", self.model, 120, 15))


def judges(broken: bool = False) -> dict[str, RuleJudge]:
    return {lv: RuleJudge(f"test-judge-{lv}", broken) for lv in ("low", "medium", "high")}


def revision(*units) -> str:
    return json.dumps({"units": [dict(u) for u in units]})


def run(settings, kind, options, *replies, found=(SKY,), judge_models=None, **extra):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    llm = FakeLLM(*replies)
    judge_models = judge_models or judges()
    client = make_client(
        settings, store, FakeRetriever(list(found)), llm, judges=judge_models, **extra
    )
    r = client.post(OUTPUTS, json={"kind": kind, "options": options}, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    return client, store, llm, judge_models, out


def report(*paragraphs: str) -> str:
    return json.dumps({"title": "Sky", "markdown": "## Sky\n\n" + "\n\n".join(paragraphs)})


def test_a_failing_paragraph_is_revised_and_judged_again(settings):
    _, store, llm, judge_models, out = run(
        settings,
        "report",
        {"judge": "low"},
        report("The sky is blue. [1]", "The sky is wrong green. [1]"),
        revision({"index": 1, "action": "revise", "unit": {"text": "Grass is green. [1]"}}),
    )
    assert out["status"] == "ready", out
    units = out["content"]["units"]
    assert [u["text"] for u in units] == ["The sky is blue. [1]", "Grass is green. [1]"]
    assert "Grass is green. [1]" in out["content"]["markdown"]
    assert [(u["judge"]["verdict"], u["judge"]["round"]) for u in units] == [
        ("supported", 1),
        ("supported", 2),
    ]
    assert units[0]["judge"]["model"] == "test-judge-low" and units[0]["judge"]["level"] == "low"
    # only the revised paragraph was judged again
    assert judge_models["low"].statements[2:] == ["Grass is green."]
    # the revision got only the failing unit, with the judge's reason
    revise_system, revise_user = llm.calls[1]
    assert "correct parts of a document" in revise_system
    assert '"index": 1' in revise_user and "contradicted by rule" in revise_user
    assert '"index": 0' not in revise_user
    log = out["provenance"]["judge"]
    assert log["rounds"] == [
        {
            "round": 1,
            "judged": 2,
            "verdicts": {"supported": 1, "contradicted": 1},
            "usage": {"tokens_in": 240, "tokens_out": 30},
            # the contradicted one searched for again: nothing it did not cite was found
            "searched_again": 1,
            "revision": {
                "revised": 1,
                "dropped": 0,
                "usage": {"tokens_in": 50, "tokens_out": 20},
            },
        },
        {
            "round": 2,
            "judged": 1,
            "verdicts": {"supported": 1},
            "usage": {"tokens_in": 120, "tokens_out": 15},
            "searched_again": 0,
        },
    ]
    assert log["removed"] == []
    assert out["provenance"]["usage"]["judge"] == {"tokens_in": 360, "tokens_out": 45}
    # every judge call is a usage row of the judge model
    models = [u.model for _, _, u in store.usage]
    assert models.count("test-judge-low") == 3


def test_a_unit_that_still_fails_after_three_rounds_is_removed_and_listed(settings):
    still_wrong = revision({"index": 0, "action": "revise", "unit": {"text": "Still wrong. [1]"}})
    _, _, _, judge_models, out = run(
        settings,
        "report",
        {"judge": "medium"},
        report("The sky is wrong red. [1]", "The sky is blue. [1]"),
        still_wrong,
    )
    assert out["status"] == "ready", out
    assert [u["text"] for u in out["content"]["units"]] == ["The sky is blue. [1]"]
    assert "wrong" not in out["content"]["markdown"]
    log = out["provenance"]["judge"]
    assert [r["round"] for r in log["rounds"]] == [1, 2, 3]
    assert "revision" not in log["rounds"][2]  # no revision after the last round
    assert log["removed"] == [
        {
            "text": "Still wrong. [1]",
            "verdict": "contradicted",
            "reason": "contradicted by rule",
            "round": 3,
        }
    ]
    assert len(judge_models["medium"].statements) == 2 + 1 + 1


def test_a_unit_the_reviser_drops_is_removed_without_another_judgement(settings):
    _, _, _, judge_models, out = run(
        settings,
        "report",
        {"judge": "high"},
        report("The sky is blue. [1]", "Clouds are missing here. [1]"),
        revision({"index": 1, "action": "drop", "unit": {}}),
    )
    assert [u["text"] for u in out["content"]["units"]] == ["The sky is blue. [1]"]
    assert out["provenance"]["judge"]["removed"] == [
        {
            "text": "Clouds are missing here. [1]",
            "verdict": "dropped in revision",
            "reason": "not_in_source by rule",
            "round": 1,
        }
    ]
    assert len(judge_models["high"].statements) == 2


def test_a_revision_that_does_not_fit_the_form_counts_as_none(settings):
    quiz = json.dumps(
        {
            "title": "Q",
            "questions": [
                {"question": "Color?", "options": ["blue", "red"], "answer": "blue", "refs": [1]}
            ]
            * 9
            + [{"question": "Is it wrong?", "options": ["a", "b"], "answer": "a", "refs": [1]}],
        }
    )
    # the answer is not among the options: not a valid question
    bad = {"question": "Fixed?", "options": ["a", "b"], "answer": "c", "refs": [1]}
    _, _, _, _, out = run(
        settings,
        "quiz",
        {"judge": "low"},
        quiz,
        revision({"index": 9, "action": "revise", "unit": bad}),
    )
    assert out["status"] == "ready", out
    assert len(out["content"]["questions"]) == 9
    assert out["provenance"]["judge"]["removed"][0]["verdict"] == "contradicted"
    assert out["provenance"]["judge"]["rounds"][0]["revision"]["revised"] == 0


def test_an_audio_script_is_judged_before_it_is_spoken(settings):
    from .conftest import FakeObjects, FakeTTS

    script = json.dumps(
        {
            "title": "Sky",
            "paragraphs": [
                {"text": "The sky is blue.", "refs": [1]},
                {"text": "The sky is wrong purple.", "refs": [1]},
            ],
        }
    )
    tts = FakeTTS()
    _, _, _, _, out = run(
        settings,
        "audio",
        {"judge": "low"},
        script,
        revision({"index": 1, "action": "drop", "unit": {}}),
        tts=tts,
        objects=FakeObjects(),
    )
    assert out["status"] == "ready", out
    assert [t["text"] for t in out["content"]["transcript"]] == ["The sky is blue."]
    assert len(tts.settings) == 1  # only what survived the judge was synthesized


def test_a_decisions_evidence_is_judged_and_its_agreement_follows(settings):
    evidence = json.dumps(
        {
            "verdict_text": "Yes.",
            "llm_choice": None,
            "evidence_for": [
                {"text": "The sky is blue on a clear day.", "refs": [1]},
                {"text": "The sky is wrong always blue.", "refs": [1]},
            ],
            "evidence_against": [],
            "gaps": [],
        }
    )
    _, _, _, _, out = run(
        settings,
        "decision",
        {"question": "Is the sky blue?", "judge": "low"},
        evidence,
        revision({"index": 1, "action": "drop", "unit": {}}),
        decision=FakeDecision({"type": "noul", "noul": 0.9}),
    )
    assert out["status"] == "ready", out
    content = out["content"]
    assert [e["text"] for e in content["evidence_for"]] == ["The sky is blue on a clear day."]
    assert content["evidence_for"][0]["judge"]["verdict"] == "supported"
    assert content["agreement"] == "consistent"


def test_a_judge_without_a_usable_answer_marks_the_unit_and_never_fails_the_output(settings):
    # 0.20.0: one unusable judge answer failed, and charged again, a whole output
    _, store, _, judge_models, out = run(
        settings,
        "report",
        {"judge": "low"},
        report("The sky is blue. [1]", "The sky is wrong green. [1]"),
        judge_models=judges(broken=True),
    )
    assert out["status"] == "ready", out
    units = out["content"]["units"]
    assert len(units) == 2  # kept, never removed or revised
    assert {u["judge"]["verdict"] for u in units} == {None}
    assert units[0]["judge"]["reason"] == "the judge gave no usable answer: unparseable answer"
    log = out["provenance"]["judge"]
    assert log["rounds"] == [
        {
            "round": 1,
            "judged": 2,
            "verdicts": {"no_usable_answer": 2},
            "usage": {"tokens_in": 480, "tokens_out": 60},
            "searched_again": 0,
        }
    ]
    assert log["removed"] == []
    # each unit: the call and one more try, both billed
    assert len(judge_models["low"].statements) == 4
    assert [u.model for _, _, u in store.usage].count("test-judge-low") == 4


def test_a_judge_answer_that_fails_once_is_tried_again(settings):
    flaky = judges()
    calls = {"n": 0}
    inner = flaky["low"].complete

    def once_broken(system, user, max_tokens=None, *, thinking=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return CompletionResult("", Usage("llm", "test-judge-low", 10, 1))
        return inner(system, user, max_tokens)

    flaky["low"].complete = once_broken
    _, _, _, _, out = run(
        settings, "report", {"judge": "low"}, report("The sky is blue. [1]"), judge_models=flaky
    )
    assert out["content"]["units"][0]["judge"]["verdict"] == "supported"


@pytest.mark.parametrize(
    ("kind", "options", "message"),
    [
        ("report", {"judge": "extreme"}, "judge: unknown value"),
        ("chart", {"judge": "low", "charts": []}, "judge: not an option of chart"),
    ],
)
def test_judge_options_that_do_not_fit_are_422(settings, kind, options, message):
    client = make_client(settings, FakeStore(), FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": kind, "options": options}, headers=AUTH)
    assert r.status_code == 422 and message in r.json()["error"], r.text


def test_judge_off_is_the_default_and_stays_absent(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM())
    r = client.post(OUTPUTS, json={"kind": "table", "options": {"judge": "off"}}, headers=AUTH)
    assert r.json()["options"] == {}
    catalogue = client.get("/api/rag/outputs/options", headers=AUTH).json()
    assert catalogue["judge"] == {
        "levels": ["off", "low", "medium", "high"],
        "default": "off",
        "models": {
            "low": "test-judge-low",
            "medium": "test-judge-medium",
            "high": "test-judge-high",
        },
    }


# -- on request ----------------------------------------------------------------


def test_a_ready_output_is_judged_on_request_without_revision(settings):
    client, store, _, judge_models, out = run(
        settings, "report", {}, report("The sky is blue. [1]", "The sky is wrong red. [1]")
    )
    path = f"/api/rag/outputs/{out['id']}/judge"
    r = client.post(path, json={"level": "high"}, headers=AUTH)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    client.worker.run_once()  # the judgement runs as a job
    stored = client.get(f"/api/rag/outputs/{out['id']}", headers=AUTH).json()
    units = stored["content"]["units"]
    assert [u["judge"]["verdict"] for u in units] == ["supported", "contradicted"]
    assert len(units) == 2  # nothing is removed on request
    assert stored["content"]["units"][1]["judge"]["model"] == "test-judge-high"
    (entry,) = stored["provenance"]["judgements"]
    assert entry["verdicts"] == {"supported": 1, "contradicted": 1}
    assert entry["usage"] == {"tokens_in": 240, "tokens_out": 30}
    assert client.post(path, json={"level": "ultra"}, headers=AUTH).status_code == 422
    assert client.post(path, json={"level": "low"}).status_code == 401


def test_judging_on_request_needs_a_ready_output_with_passages(settings):
    store = FakeStore()
    client = make_client(settings, store, FakeRetriever([]), FakeLLM(), judges=judges())
    old = store.create_output(NOTEBOOK, "report", "ready")
    store.update_output(old.id, content={"markdown": "x", "units": []})
    r = client.post(f"/api/rag/outputs/{old.id}/judge", json={"level": "low"}, headers=AUTH)
    assert (r.status_code, r.json()) == (409, {"error": "nothing to judge: no cited passages"})
    chart = store.create_output(NOTEBOOK, "chart", "ready").id
    r = client.post(f"/api/rag/outputs/{chart}/judge", json={"level": "low"}, headers=AUTH)
    assert r.status_code == 422
    theirs = store.create_output(OTHER_NOTEBOOK, "report", "ready").id
    r = client.post(f"/api/rag/outputs/{theirs}/judge", json={"level": "low"}, headers=AUTH)
    assert r.status_code == 404


def test_a_chat_answer_is_judged_on_request(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf")
    llm = FakeLLM("The sky is blue [1].\n\nThe sky is wrong at night [1].")
    judge_models = judges()
    client = make_client(settings, store, FakeRetriever([SKY]), llm, judges=judge_models)
    ask = f"/api/rag/notebooks/{NOTEBOOK}/ask"
    answer = client.post(ask, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH)
    message_id = answer.json()["message_id"]
    r = client.post(f"/api/rag/messages/{message_id}/judge", json={"level": "low"}, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    listed = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert [u["judge"]["verdict"] for u in listed[-1]["units"]] == ["supported", "contradicted"]
    assert listed[-1]["units"][1]["judge"]["reason"] == "contradicted by rule"
    question_id = listed[0]["id"]
    r = client.post(f"/api/rag/messages/{question_id}/judge", json={"level": "low"}, headers=AUTH)
    assert r.status_code == 409
    other = store.insert_message(OTHER_NOTEBOOK, CONVERSATION, "assistant", "x", [])
    r = client.post(f"/api/rag/messages/{other.id}/judge", json={"level": "low"}, headers=AUTH)
    assert (r.status_code, r.json()) == (404, {"error": "message not found"})


# -- editing and the stored units ------------------------------------------------


def test_a_removed_mind_map_node_leaves_its_children_in_its_place():
    doc = Mindmap.model_validate(
        {
            "title": "m",
            "root": {
                "label": "R",
                "children": [
                    {"label": "A", "children": [{"label": "A1"}, {"label": "A2"}]},
                    {"label": "B"},
                ],
            },
        }
    )
    gen = MindmapGenerator()
    edited = gen.edit(doc, 2, {"label": "A1 fixed", "refs": [1]})
    assert gen.editable(edited, 2) == {"label": "A1 fixed", "refs": [1]}
    pruned = gen.remove(edited, {1})
    labels = [u.text for u in gen.to_output(pruned).units]
    assert labels == ["R", "A1 fixed", "A2", "B"]
    assert gen.remove(doc, {0}).root.label == "R"  # the root stays


def test_table_and_report_edits_keep_their_form():
    table = Table(title="t", columns=["a", "b"], rows=[["1", "2"]], row_refs=[[1]])
    gen = TableGenerator()
    with pytest.raises(ValueError):
        gen.edit(table, 0, {"cells": ["only one"], "refs": [1]})
    assert gen.edit(table, 0, {"cells": ["3", "4"], "refs": [2]}).rows == [["3", "4"]]
    report_doc = Report(title="r", markdown="## H\n\nOne. [1]\n\nTwo. [1]")
    rgen = ReportGenerator()
    edited = rgen.edit(report_doc, 1, {"text": "# Not a\n\nheading [1]"})
    assert edited.markdown == "## H\n\nOne. [1]\n\nNot a heading [1]"
    with pytest.raises(ValueError):
        rgen.edit(report_doc, 0, {"text": "  "})


@pytest.mark.parametrize(
    ("kind", "document"),
    [
        ("report", {"title": "r", "markdown": "## H\n\nThe sky is blue. [1]\n\nMore [1]."}),
        (
            "quiz",
            {
                "title": "q",
                "questions": [
                    {"question": "C?", "options": ["a", "b"], "answer": "a", "explanation": "e",
                     "refs": [1]}
                ],
            },
        ),
        ("table", {"title": "t", "columns": ["a", "b"], "rows": [["1", "2"]], "row_refs": [[1]]}),
        (
            "mindmap",
            {"title": "m", "root": {"label": "R", "children": [{"label": "A", "refs": [1]}]}},
        ),
        (
            "infographic",
            {
                "title": "i",
                "headline": "h",
                "facts": [{"label": "L", "value": "V", "refs": [1]}],
                "sections": [{"title": "S", "text": "T", "refs": [1]}],
            },
        ),
        (
            "audio",
            {
                "title": "a",
                "turns": [
                    {"speaker": "interviewer", "text": "Why?"},
                    {"speaker": "expert", "text": "Because.", "refs": [1]},
                ],
            },
        ),
    ],
)  # fmt: skip
def test_stored_units_are_the_units_the_generator_made(kind, document):
    gen = registry(tts_available=True)[kind]
    _, schema = gen.prompt({"audio_style": "conversation", "question_count": 1})
    out = gen.to_output(schema.model_validate(document))
    passages = [Passage(1, "c", "s", "doc.pdf", "pdf", None, "The sky is blue.")]
    check_units(out.units, passages)
    stored = stored_units(kind, out.content)
    assert [(u.text, u.refs, u.claim) for u in stored] == [
        (u.text, u.target.get("refs", []), u.claim) for u in out.units
    ]
