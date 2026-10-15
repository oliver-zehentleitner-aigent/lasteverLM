"""The agent chat makes a document from the sources the user means: those
named in the message, the ones just discussed when the user picks them, and
a correction ("falsches PDF") is a new plan, never a question to the sources."""

import pytest

from lasteverlm_rag.agent import is_correction, match_source

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    FakeIngest,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
    source_uuid,
)
from .test_agent import ASK, ToolLLM, plan_path

NAMES = [
    "Eurowings_Boarding_Pass.pdf",
    "Senior_Database_Engineer.pdf",
    "Lohnabrechnung_2026-09.pdf",
    "Dienstzeugnis.pdf",
]
BOARDING, SENIOR, PAYSLIP, REFERENCE = (source_uuid(i) for i in range(1, 5))
ALL = [BOARDING, SENIOR, PAYSLIP, REFERENCE]
MINDMAP = [("create_output", {"kind": "mindmap"})]
REPORT = [("create_output", {"kind": "report"})]


def setup(settings, plans, *replies, found=()):
    store = FakeStore()
    for i, name in enumerate(NAMES, start=1):
        added = store.add_source(NOTEBOOK, name, summary=f"About {name}.")
        store.sources[source_uuid(i)] = {**store.sources.pop(added), "id": source_uuid(i)}
    llm = ToolLLM(plans, *replies)
    client = make_client(settings, store, FakeRetriever(list(found)), llm, ingest=FakeIngest())
    return store, llm, client


def ask(client, question, selected=ALL):
    r = client.post(
        ASK,
        json={"question": question, "conversation_id": CONVERSATION, "source_ids": selected},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    return r.json()


def answer(client, plan, choice):
    r = client.post(
        f"{plan_path(plan['plan_id'])}/answer",
        json={"question_id": plan["question"]["question_id"], "choice": choice},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    return r.json()


def reads(plan):
    return [s["name"] for s in plan["sources"]]


# -- 1. sources the message names --


@pytest.mark.parametrize(
    "named",
    [
        ["Senior_Database_Engineer.pdf"],
        None,  # the planner left them out: read from the message itself
    ],
)
def test_a_named_source_is_the_only_one_read(settings, named):
    call = {"kind": "mindmap", **({"sources": named} if named else {})}
    store, _, client = setup(settings, [[("create_output", call)]])
    plan = ask(client, "erstelle bitte aus Senior_Database_Engineer.pdf ein mindmap")["plan"]
    assert plan["status"] == "proposed" and plan["question"] is None
    step = plan["steps"][0]
    assert step["args"]["source_ids"] == [SENIOR]
    assert step["label"] == "Create a mindmap from Senior_Database_Engineer.pdf"
    assert reads(plan) == ["Senior_Database_Engineer.pdf"]
    r = client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    assert r.status_code == 200, r.text
    (output,) = store.outputs.values()
    assert output["options"]["sources"] == [SENIOR]


@pytest.mark.parametrize(
    ("message", "written", "expected"),
    [
        ("make a mind map of senior database engineer", "senior database engineer", SENIOR),
        ("Mindmap aus der Lohnabrechnung bitte", "Lohnabrechnung", PAYSLIP),
        ("Mindmap aus dienstzeugnis.PDF", "dienstzeugnis.PDF", REFERENCE),
    ],
)
def test_a_name_matches_without_case_extension_or_by_a_unique_part(
    settings, message, written, expected
):
    _, _, client = setup(settings, [[("create_output", {"kind": "mindmap", "sources": [written]})]])
    plan = ask(client, message)["plan"]
    assert plan["steps"][0]["valid"] and plan["steps"][0]["args"]["source_ids"] == [expected]


def test_a_name_that_matches_nothing_or_several_is_a_struck_step(settings):
    plans = [
        [("create_output", {"kind": "mindmap", "sources": ["Gehaltszettel.pdf"]})],
        [("create_output", {"kind": "mindmap", "sources": ["Zeugnis"]})],
        [("create_output", {"kind": "mindmap", "sources": ["Arbeitsvertrag.pdf"]})],
    ]
    store, _, client = setup(settings, plans)
    store.add_source(NOTEBOOK, "Arbeitszeugnis_alt.pdf")
    nothing = ask(client, "Mindmap aus Gehaltszettel.pdf")["plan"]["steps"][0]
    assert not nothing["valid"]
    assert nothing["invalid_reason"] == 'no source in this notebook matches "Gehaltszettel.pdf"'
    several = ask(client, "eine Mindmap aus dem Zeugnis")["plan"]["steps"][0]
    assert not several["valid"] and "matches several sources" in several["invalid_reason"]
    # a name the user did not write (read from a document, say) is never followed
    unsaid = ask(client, "eine Mindmap bitte")["plan"]
    assert unsaid["steps"][0]["invalid_reason"] == '"Arbeitsvertrag.pdf" is not in your message'


def test_matching_prefers_the_exact_name_over_a_part():
    sources = {"a": "Zeugnis.pdf", "b": "Dienstzeugnis.pdf"}
    assert match_source("Zeugnis.pdf", sources) == ("a", "")
    assert match_source("zeugnis", sources) == ("a", "")
    assert match_source("dienst", sources) == ("b", "")
    assert match_source("eugnis", sources)[0] is None


# -- 2. no source named: all selected, or the ones just discussed --


def test_after_an_answer_about_one_source_the_plan_asks_which(settings):
    cited = chunk(2, "Senior database engineers run PostgreSQL.")
    store, _, client = setup(settings, [[], REPORT], "They run PostgreSQL [1].", found=[cited])
    first = ask(client, "Was macht ein Senior Database Engineer?")
    assert first["plan"] is None and first["citations"][0]["source_id"] == SENIOR
    plan = ask(client, "report erstellen bitte")["plan"]
    assert plan["status"] == "asking"
    question = plan["question"]
    assert question["text"] == "Which sources should the new documents be made from?"
    assert [c["label"] for c in question["choices"]] == [
        "All 4 selected sources",
        "Only Senior_Database_Engineer.pdf (just discussed)",
    ]
    assert question["default"] == "sources:discussed"
    done = answer(client, plan, "sources:discussed")
    assert done["status"] == "proposed"
    assert done["steps"][0]["args"]["source_ids"] == [SENIOR]
    assert done["steps"][0]["label"].endswith("from Senior_Database_Engineer.pdf")
    assert reads(done) == ["Senior_Database_Engineer.pdf"]
    assert reads(client.get(plan_path(plan["plan_id"]), headers=AUTH).json()) == reads(done)


def test_all_selected_stays_all_and_one_selected_is_not_asked(settings):
    cited = chunk(2, "Senior database engineers run PostgreSQL.")
    _, _, client = setup(settings, [[], REPORT, REPORT], "PostgreSQL [1].", found=[cited])
    ask(client, "Was macht ein Senior Database Engineer?")
    plan = ask(client, "report erstellen bitte")["plan"]
    done = answer(client, plan, "sources:all")
    assert done["steps"][0]["args"]["source_ids"] == ALL
    assert reads(done) == NAMES
    only = ask(client, "report erstellen bitte", selected=[PAYSLIP])["plan"]
    assert only["question"] is None
    assert only["steps"][0]["args"]["source_ids"] == [PAYSLIP]
    assert reads(only) == ["Lohnabrechnung_2026-09.pdf"]


def test_without_an_answer_before_the_selection_is_used_without_asking(settings):
    _, _, client = setup(settings, [REPORT])
    plan = ask(client, "create a report", selected=[SENIOR, REFERENCE])["plan"]
    assert plan["question"] is None
    assert plan["steps"][0]["args"]["source_ids"] == [SENIOR, REFERENCE]
    assert reads(plan) == ["Senior_Database_Engineer.pdf", "Dienstzeugnis.pdf"]


# -- 3. a correction is a new plan --


@pytest.mark.parametrize(
    "message",
    [
        "danke aber das ist voll falschen pdf",
        "falsches PDF",
        "nicht das",
        "Das ist nicht das richtige Dokument",
        "nochmal mit dem anderen",
        "wrong document",
        "not that one",
        "redo it with another file",
    ],
)
def test_corrections_are_recognised(message):
    assert is_correction(message)


@pytest.mark.parametrize(
    "message",
    [
        "Ist das nicht das gleiche wie vorher?",
        "What went wrong in the 2023 migration?",
        "Was steht im Dienstzeugnis?",
        "Ist die Antwort falsch, oder fehlt eine Quelle?",
    ],
)
def test_questions_are_not_corrections(message):
    assert not is_correction(message)


def test_a_correction_proposes_the_same_document_again_with_the_source_question(settings):
    store, llm, client = setup(settings, [MINDMAP])
    first = ask(client, "erstelle bitte ein mindmap")["plan"]
    assert first["steps"][0]["args"]["source_ids"] == ALL
    client.post(f"{plan_path(first['plan_id'])}/confirm", headers=AUTH)
    planned = len(llm.planned)
    body = ask(client, "danke aber das ist voll falschen pdf")
    assert len(llm.planned) == planned and llm.calls == []  # no planner, no answer
    plan = body["plan"]
    assert plan["status"] == "asking" and plan["plan_id"] != first["plan_id"]
    assert plan["steps"][0]["args"]["kind"] == "mindmap"
    # all four were wrong: each one alone is offered
    assert [c["label"] for c in plan["question"]["choices"]] == [f"Only {n}" for n in NAMES]
    done = answer(client, plan, f"sources:{REFERENCE}")
    assert done["steps"][0]["args"]["source_ids"] == [REFERENCE]
    assert reads(done) == ["Dienstzeugnis.pdf"]


def test_a_correction_that_names_the_source_needs_no_question(settings):
    _, llm, client = setup(settings, [MINDMAP])
    ask(client, "make a mind map")
    plan = ask(client, "redo with Dienstzeugnis.pdf")["plan"]
    assert plan["status"] == "proposed" and plan["question"] is None
    assert plan["steps"][0]["args"]["source_ids"] == [REFERENCE]
    assert llm.calls == []


def test_a_correction_without_a_plan_is_asked_back_never_answered(settings):
    store, llm, client = setup(settings, [], "should not be used")
    body = ask(client, "falsches PDF")
    assert body["plan"] is None and body["citations"] == []
    assert body["answer"].startswith("Which document should I use?")
    assert llm.planned == [] and llm.calls == []
    assert store.usage == []
