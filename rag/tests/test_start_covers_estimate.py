"""An output or a plan starts only if the balance covers its estimated
maximum plus what the user's started work still holds; a 402 says how much
it needs and how much there is."""

from decimal import Decimal

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, make_client
from .test_agent import ACTIONS, QUIZ, URL, ask, plan_path, setup
from .test_judging import OUTPUTS, SKY

REPORT = {"kind": "report", "options": {"judge": "high"}}


def client_with(settings, balance):
    store = FakeStore(balance=balance)
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    return store, make_client(settings, store, FakeRetriever([SKY]), FakeLLM())


def output_max(client, body=REPORT):
    r = client.post("/api/rag/estimate", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    return Decimal(str(r.json()["charge_cents_max"]))


def test_an_output_its_balance_does_not_cover_is_refused_with_the_amounts(settings):
    store, client = client_with(settings, 1)
    needed = output_max(client)
    assert needed > 1
    r = client.post(OUTPUTS, json=REPORT, headers=AUTH)
    assert r.status_code == 402
    assert r.json() == {
        "error": "credit does not cover this",
        "code": "credit_insufficient",
        "needed_cents": float(needed),
        "held_cents": 0.0,
        "available_cents": 1.0,
    }
    assert store.outputs == {}


def test_a_waiting_output_holds_its_maximum_until_it_ends(settings):
    store, client = client_with(settings, 0)
    needed = output_max(client)
    store.balance = int(needed * 3 // 2) + 1  # covers one, not two
    first = client.post(OUTPUTS, json=REPORT, headers=AUTH)
    assert first.status_code == 202
    assert store.reserved[first.json()["id"]] == float(needed)
    second = client.post(OUTPUTS, json=REPORT, headers=AUTH)
    assert second.status_code == 402
    assert second.json()["held_cents"] == float(needed)
    # once the first has ended, it holds nothing
    store.outputs[first.json()["id"]]["status"] = "ready"
    assert client.post(OUTPUTS, json=REPORT, headers=AUTH).status_code == 202


def test_reads_ingest_still_holds_count_too(settings):
    store, client = client_with(settings, 0)
    needed = output_max(client)
    store.balance = int(needed) + 1
    store.ingest_held = 5
    r = client.post(OUTPUTS, json=REPORT, headers=AUTH)
    assert r.status_code == 402 and r.json()["held_cents"] == 5.0


def test_a_plan_is_confirmed_only_when_its_maximum_and_ingests_lines_fit(settings):
    store, _, _, client = setup(settings, [ACTIONS], QUIZ)
    plan = ask(client, f"Add {URL} and make a quiz of 5 questions, then explain it.")["plan"]
    needed = plan["estimate"]["max"] + sum(line["max"] for line in plan["separate"])
    store.balance = int(needed) - 1 if needed >= 2 else 0
    r = client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    assert r.status_code == 402
    assert r.json()["needed_cents"] >= needed - 0.01
    assert client.get(plan_path(plan["plan_id"]), headers=AUTH).json()["status"] == "proposed"
    store.balance = int(needed) + 1
    r = client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    assert r.status_code == 200, r.text
    # its output holds its own maximum while it waits
    output_id = r.json()["steps"][1]["result"]["output_id"]
    assert store.reserved[output_id] > 0
