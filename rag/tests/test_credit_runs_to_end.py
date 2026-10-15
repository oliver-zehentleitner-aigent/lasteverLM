"""Credit is checked once, when an action starts: an action that has started
runs to the end, even if the balance goes negative on the way."""

import json

from .conftest import (
    AUTH,
    NOTEBOOK,
    FakeIngest,
    FakeLLM,
    FakeObjects,
    FakeRetriever,
    FakeStore,
    FakeTTS,
    make_client,
)
from .test_agent import ACTIONS, QUIZ, URL, ask, plan_path, setup
from .test_judging import OUTPUTS, SKY, judges, report, revision


def start_then_overspend(settings, kind, options, *replies, **extra):
    """Create the output with credit, then let the balance go negative
    before the worker runs it (as another action spending at the same time)."""
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    judge_models = judges()
    client = make_client(
        settings, store, FakeRetriever([SKY]), FakeLLM(*replies), judges=judge_models, **extra
    )
    r = client.post(OUTPUTS, json={"kind": kind, "options": options}, headers=AUTH)
    assert r.status_code == 202, r.text
    store.balance = -50
    client.worker.run_once()
    return client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json(), judge_models


def test_an_output_runs_every_judge_round_and_revision_on_a_negative_balance(settings):
    out, judge_models = start_then_overspend(
        settings,
        "report",
        {"judge": "low"},
        report("The sky is blue. [1]", "The sky is wrong green. [1]"),
        revision({"index": 1, "action": "revise", "unit": {"text": "Grass is green. [1]"}}),
    )
    assert out["status"] == "ready", out
    assert [u["judge"]["round"] for u in out["content"]["units"]] == [1, 2]
    assert judge_models["low"].statements[2:] == ["Grass is green."]


def test_an_audio_speaks_every_segment_on_a_negative_balance(settings):
    script = json.dumps(
        {
            "title": "Sky",
            "paragraphs": [
                {"text": "The sky is blue.", "refs": [1]},
                {"text": "Grass is green in spring.", "refs": [1]},
            ],
        }
    )
    tts = FakeTTS()
    out, _ = start_then_overspend(
        settings, "audio", {"judge": "low"}, script, tts=tts, objects=FakeObjects()
    )
    assert out["status"] == "ready", out
    assert len(tts.settings) == 2


class SpendingIngest(FakeIngest):
    """Adding the page spends the rest of the balance and more."""

    def add_url(self, bearer, notebook_id, url):
        self.store.balance = -50
        return super().add_url(bearer, notebook_id, url)


def test_a_confirmed_plan_runs_all_its_steps_when_a_step_overspends(settings):
    spending = SpendingIngest()
    store, _, _, client = setup(
        settings, [ACTIONS], QUIZ, "It tests the colour of the sky [1].", ingest=spending
    )
    spending.store = store
    plan = ask(client, f"Add {URL} and make a quiz of 5 questions, then explain it.")["plan"]
    r = client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    assert r.status_code == 200, r.text
    assert store.balance < 0
    assert [s["state"] for s in r.json()["steps"]] == ["done", "waiting", "waiting"]
    client.worker.run_once()
    done = client.get(plan_path(plan["plan_id"]), headers=AUTH).json()
    assert [s["state"] for s in done["steps"]] == ["done", "done", "done"], done["steps"]


def test_a_plan_is_not_confirmed_without_credit_and_nothing_runs(settings):
    store, _, ingest, client = setup(settings, [ACTIONS], QUIZ)
    plan = ask(client, f"Add {URL} and make a quiz of 5 questions, then explain it.")["plan"]
    store.balance = 0
    r = client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    assert r.status_code == 402
    assert ingest.calls == [] and store.outputs == {}
    assert client.get(plan_path(plan["plan_id"]), headers=AUTH).json()["status"] == "proposed"
