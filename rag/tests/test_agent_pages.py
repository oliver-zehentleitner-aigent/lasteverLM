"""The agent chat names what it made, asks before fetching web pages again,
and a plain answer says how old the web page it cites is."""

from datetime import UTC, datetime, timedelta

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    OWNER,
    FakeIngest,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)
from .test_agent import QUIZ, ToolLLM, ask, plan_path

READ = (datetime.now(UTC) - timedelta(hours=15)).isoformat()
MAKE_QUIZ = [("create_output", {"kind": "quiz", "options": {"question_count": 5}})]


def notebook_with_a_page(settings, plans, *replies, found=None):
    store = FakeStore()
    store.add_source(NOTEBOOK, "handbook.pdf", summary="The handbook.")
    page = store.add_source(NOTEBOOK, "https://example.org/prices", summary="Prices.", kind="url")
    store.sources[page]["read_at"] = READ
    llm = ToolLLM(plans, *replies)
    ingest = FakeIngest(store=store)
    client = make_client(settings, store, FakeRetriever(found or []), llm, ingest=ingest)
    return store, page, ingest, client


def test_the_done_message_names_and_links_what_was_made(settings):
    store, _, _, client = notebook_with_a_page(settings, [MAKE_QUIZ], QUIZ)
    store.sources = {k: v for k, v in store.sources.items() if v["kind"] != "url"}
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    client.worker.run_once()
    messages = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    done = messages[-1]
    assert done["content"] == 'The plan is done.\n\n✓ 1. Created the quiz "Sky quiz"'
    (step,) = done["plan"]["steps"]
    assert step["result"]["title"] == "Sky quiz" and step["result"]["output_id"]


def test_a_plan_reading_a_cached_page_asks_once_cached_by_default(settings):
    store, page, ingest, client = notebook_with_a_page(settings, [MAKE_QUIZ])
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    assert plan["status"] == "asking"
    question = plan["question"]
    assert question["text"] == (
        "https://example.org/prices was read 15 h ago: use that version or fetch again?"
    )
    assert question["default"] == "pages:cached"
    assert [c["id"] for c in question["choices"]] == ["pages:cached", "pages:fresh"]
    assert question["choices"][1]["label"] == "Fetch them again (+ up to €0.004)"
    sources = {s["name"]: s for s in plan["sources"]}
    assert sources["https://example.org/prices"]["read_at"] == READ
    assert "handbook.pdf" in sources

    answered = client.post(
        f"{plan_path(plan['plan_id'])}/answer",
        json={"question_id": question["question_id"], "choice": "pages:fresh"},
        headers=AUTH,
    ).json()
    assert answered["status"] == "proposed"
    assert answered["steps"][0]["args"]["url_refresh"] == [page]
    assert [line["label"] for line in answered["separate"]] == [
        "Re-read https://example.org/prices if it changed"
    ]
    assert answered["answered"][0]["answer"]["choice"] == "pages:fresh"
    client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH)
    assert ("refetch", AUTH["Authorization"], page) in ingest.calls


def test_a_message_that_says_fresh_or_cached_is_not_asked(settings):
    fresh = [("create_output", {"kind": "quiz", "web_pages": "fresh"})]
    cached = [("create_output", {"kind": "quiz", "web_pages": "cached"})]
    _, page, _, client = notebook_with_a_page(settings, [fresh, cached])
    plan = ask(client, "Make a quiz, neu laden.")["plan"]
    assert plan["status"] == "proposed" and plan["steps"][0]["args"]["url_refresh"] == [page]
    plan = ask(client, "Make a quiz from the cached pages.")["plan"]
    assert plan["status"] == "proposed" and "url_refresh" not in plan["steps"][0]["args"]


def test_a_judge_question_and_a_page_question_come_one_after_the_other(settings):
    store, _, _, client = notebook_with_a_page(settings, [MAKE_QUIZ])
    store.preferences[OWNER] = {"judge_default": "high"}
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    path = plan_path(plan["plan_id"])
    first = plan["question"]
    assert first["default"] == "judge:high" and plan["answered"] == []
    second = client.post(
        f"{path}/answer",
        json={"question_id": first["question_id"], "choice": "judge:off"},
        headers=AUTH,
    ).json()
    assert second["status"] == "asking" and second["question"]["default"] == "pages:cached"
    assert [q["answer"]["choice"] for q in second["answered"]] == ["judge:off"]
    r = client.post(f"{path}/confirm", headers=AUTH)
    assert r.status_code == 409
    done = client.post(
        f"{path}/answer",
        json={"question_id": second["question"]["question_id"], "choice": "pages:cached"},
        headers=AUTH,
    ).json()
    assert done["status"] == "proposed"
    assert [q["answer"]["choice"] for q in done["answered"]] == ["judge:off", "pages:cached"]


def test_a_plain_answer_says_how_old_the_cited_web_page_is(settings):
    store = FakeStore()
    page_chunk = chunk(1, "A page costs 2 cents.", source_kind="url")
    store.sources[page_chunk.source_id] = {
        "id": page_chunk.source_id,
        "notebook_id": NOTEBOOK,
        "name": "https://example.org/prices",
        "kind": "url",
        "status": "ready",
        "summary": "Prices.",
        "error": None,
        "read_at": READ,
    }
    llm = ToolLLM([[]], "A page costs 2 cents [1].")
    client = make_client(settings, store, FakeRetriever([page_chunk]), llm)
    body = ask(client, "What does a page cost?")
    assert body["web_pages"] == [
        {
            "library_id": page_chunk.source_id,
            "name": "https://example.org/prices",
            "fetched_at": READ,
        }
    ]
    listed = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert listed[-1]["web_pages"] == body["web_pages"] and listed[0]["web_pages"] == []
