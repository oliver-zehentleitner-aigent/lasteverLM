"""A claim the judge rejects is searched for again across the selected
sources before anything is revised: one supported by a passage it did not
cite is "supported_elsewhere" and cites that passage too; an invented one
stays not_in_source; a supported unit costs no extra call."""

import json
import threading

from lasteverlm_core import CompletionResult, Usage

from lasteverlm_rag.estimate import judge_calls
from lasteverlm_rag.judging import SEARCH_AGAIN_K

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, chunk, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day.")
HANDBOOK = chunk(2, "The handbook shows a panel with notes of up to 500 characters.")
REPORT = json.dumps(
    {
        "title": "Sky",
        "markdown": "## Sky\n\nThe sky is blue. [1]\n\nThe handbook has a panel with notes. [1]"
        "\n\nThe handbook has an invented dashboard. [1]",
    }
)
DROP = json.dumps({"units": [{"index": 2, "action": "drop"}]})


class SearchedRetriever(FakeRetriever):
    """The prompt's search finds the sky only; searching a claim again (k of
    ``SEARCH_AGAIN_K``, no floor) finds the handbook too."""

    def search(self, notebook_id, embedding, k, floor, source_id=None, **kwargs):
        hits = super().search(notebook_id, embedding, k, floor, source_id, **kwargs)
        if k == SEARCH_AGAIN_K and floor == 0.0 and source_id is None:
            return [HANDBOOK, *hits]
        return [h for h in hits if h.chunk_id != HANDBOOK.chunk_id]


class PassageJudge:
    """Supports a statement when its key word is in the passages it is shown;
    "invented" is never supported."""

    def __init__(self, model):
        self.model = model
        self.statements: list[str] = []
        self._lock = threading.Lock()

    def complete(self, system, user, max_tokens=None, *, thinking=None):
        statement = user.split("\n")[1]
        shown = user.split("Passages:", 1)[1]
        with self._lock:
            self.statements.append(statement)
        if "invented" in statement:
            verdict, quote = "not_in_source", ""
        elif "panel" in statement:
            supported = "panel" in shown
            verdict = "supported" if supported else "not_in_source"
            quote = "a panel with notes" if supported else ""
        else:
            verdict, quote = "supported", "The sky is blue"
        reply = json.dumps({"verdict": verdict, "reason": f"{verdict} here", "quote": quote})
        return CompletionResult(reply, Usage("llm", self.model, 120, 15))


def run(settings, options, *replies):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky and the handbook.")
    judges = {lv: PassageJudge(f"test-judge-{lv}") for lv in ("low", "medium", "high")}
    client = make_client(
        settings, store, SearchedRetriever([SKY]), FakeLLM(*replies), judges=judges
    )
    r = client.post(OUTPUTS, json={"kind": "report", "options": options}, headers=AUTH)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    return store, client, judges, out


def test_an_under_cited_claim_is_supported_elsewhere_and_an_invented_one_is_not(settings):
    _, _, judges, out = run(settings, {"judge": "low"}, REPORT, DROP)
    assert out["status"] == "ready", out["error"]
    sky, panel = out["content"]["units"]  # the invented one was dropped
    assert panel["judge"]["verdict"] == "supported_elsewhere"
    assert panel["judge"]["added_refs"] == [2] and panel["refs"] == [1, 2]
    assert "added_refs" not in sky["judge"]
    passages = out["provenance"]["passages"]
    assert [(p["n"], p.get("added_by")) for p in passages] == [(1, None), (2, "judge")]
    assert passages[1]["chunk_id"] == HANDBOOK.chunk_id
    # the word check ran again with the passage the claim gained
    assert panel["support"] == "supported"
    log = out["provenance"]["judge"]
    first = log["rounds"][0]
    assert first["searched_again"] == 2
    assert first["verdicts"] == {"supported": 1, "supported_elsewhere": 1, "not_in_source": 1}
    # still in no source: not_in_source, revised (dropped) and listed
    assert [(r["verdict"], r["text"]) for r in log["removed"]] == [
        ("dropped in revision", "The handbook has an invented dashboard. [1]")
    ]
    # a supported unit is judged once; only the failing ones are judged again
    statements = judges["low"].statements
    assert statements.count("The sky is blue.") == 1
    assert statements.count("The handbook has a panel with notes.") == 2


def test_a_contradicted_claim_is_never_searched_into_supported(settings):
    wrong = json.dumps(
        {"title": "Sky", "markdown": "## Sky\n\nThe handbook has a panel, wrong colour. [1]"}
    )
    class Contradicting(PassageJudge):
        def complete(self, system, user, max_tokens=None, *, thinking=None):
            statement = user.split("\n")[1]
            with self._lock:
                self.statements.append(statement)
            reply = {"verdict": "contradicted", "reason": "the colour differs", "quote": ""}
            return CompletionResult(json.dumps(reply), Usage("llm", self.model, 120, 15))

    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    judges = {lv: Contradicting(f"test-judge-{lv}") for lv in ("low", "medium", "high")}
    client = make_client(settings, store, SearchedRetriever([SKY]), FakeLLM(wrong), judges=judges)
    r = client.post(OUTPUTS, json={"kind": "report", "options": {}}, headers=AUTH)
    client.worker.run_once()
    r = client.post(f"/api/rag/outputs/{r.json()['id']}/judge", json={"level": "low"}, headers=AUTH)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['target_id']}", headers=AUTH).json()
    (unit,) = out["content"]["units"]
    # the conflict stays visible: no second search, no added passage
    assert unit["judge"]["verdict"] == "contradicted" and "added_refs" not in unit["judge"]
    assert unit["refs"] == [1] and len(out["provenance"]["passages"]) == 1
    assert judges["low"].statements == ["The handbook has a panel, wrong colour."]
    assert out["provenance"]["judgements"][0]["searched_again"] == 0


def test_at_standard_a_doubted_claim_gains_the_passage_found(settings):
    _, _, _, out = run(settings, {"verification": "standard"}, REPORT)
    assert out["status"] == "ready", out["error"]
    by_text = {u["text"]: u for u in out["content"]["units"]}
    panel = by_text["The handbook has a panel with notes. [1]"]
    assert panel["judge"]["verdict"] == "supported_elsewhere" and panel["refs"] == [1, 2]
    invented = by_text["The handbook has an invented dashboard. [1]"]
    assert invented["judge"]["verdict"] == "not_in_source" and invented["refs"] == [1]
    assert out["provenance"]["passages"][-1]["added_by"] == "judge"


def test_on_request_the_found_passage_joins_the_output(settings):
    store, client, judges, out = run(settings, {}, REPORT)
    r = client.post(f"/api/rag/outputs/{out['id']}/judge", json={"level": "low"}, headers=AUTH)
    assert r.status_code == 202, r.text
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{out['id']}", headers=AUTH).json()
    panel = out["content"]["units"][1]
    assert panel["judge"]["verdict"] == "supported_elsewhere"
    assert panel["judge"]["added_refs"] == [2] and panel["refs"] == [1, 2]
    assert out["provenance"]["passages"][-1] == {
        **out["provenance"]["passages"][-1],
        "n": 2,
        "added_by": "judge",
    }
    (judgement,) = out["provenance"]["judgements"]
    assert judgement["verdicts"]["supported_elsewhere"] == 1
    assert judgement["searched_again"] == 2
    assert out["provenance"]["check"]["supported"] >= 1


def test_the_estimate_counts_one_more_judgement_per_failing_unit():
    from lasteverlm_rag.estimate import Models

    models = Models(llm="l", embedding="e", decision="d", judges={"low": "j"}, tts=None)
    low, high = (
        judge_calls("quiz", {"question_count": 5}, models, "low", case, revise=False)
        for case in (0, 1)
    )
    assert len(low) == 5 and len(high) == 10
