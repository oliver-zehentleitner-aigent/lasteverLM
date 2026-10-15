"""The agent chat asks an open choice that changes the cost or the result,
instead of deciding it: first use, how thoroughly the documents are checked."""

from .conftest import AUTH, CONVERSATION, OWNER
from .test_agent import ask, plan_path, setup

QUIZ = [("create_output", {"kind": "quiz", "options": {"question_count": 5}})]
LEVELS = ["verification:basic", "verification:standard", "verification:thorough"]


def options(plan, n=1):
    return plan["steps"][n - 1]["args"]["options"]


def test_at_basic_no_question_and_a_note(settings):
    store, _, _, client = setup(settings, [QUIZ])
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    assert plan["status"] == "proposed" and plan["question"] is None
    assert "verification" not in options(plan) and "judge" not in options(plan)
    assert plan["notes"] == [
        "Basic check only (words and negation): the new documents are not checked by "
        "a judge. Ask for one if you want it."
    ]
    assert client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH).status_code == 200


def test_above_basic_the_plan_asks_and_follows_the_answer(settings):
    store, _, _, client = setup(settings, [QUIZ, QUIZ])
    store.preferences[OWNER] = {"verification_level": "thorough"}
    body = ask(client, "Make a quiz of 5 questions.")
    plan = body["plan"]
    assert plan["status"] == "asking" and plan["notes"] == []
    question = plan["question"]
    assert [c["id"] for c in question["choices"]] == LEVELS
    assert question["choices"][2]["label"] == (
        "Thorough: a judge for everything, with revision (your default)"
    )
    assert question["default"] == "verification:thorough" and question["free_text"] is False
    assert "apply" not in question  # how an answer applies stays on the server
    basic, standard, thorough = (c["estimate"]["max"] for c in question["choices"])
    assert basic < standard < thorough
    assert body["answer"].endswith(question["text"])
    path = plan_path(plan["plan_id"])
    # nothing runs before the answer
    r = client.post(f"{path}/confirm", headers=AUTH)
    assert (r.status_code, r.json()) == (409, {"error": "answer the question first"})

    r = client.post(
        f"{path}/answer",
        json={"question_id": question["question_id"], "choice": "verification:thorough"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    answered = r.json()
    assert answered["status"] == "proposed"
    assert options(answered)["verification"] == "thorough"
    assert options(answered)["judge"] == "medium"
    assert answered["estimate"]["max"] == thorough
    messages = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == question["choices"][2]["label"]
    assert client.post(f"{path}/confirm", headers=AUTH).json()["status"] == "running"
    # the second plan, answered "basic": the legacy judge goes too
    second = ask(client, "Make another quiz.")["plan"]
    r = client.post(
        f"{plan_path(second['plan_id'])}/answer",
        json={"question_id": second["question"]["question_id"], "choice": "verification:basic"},
        headers=AUTH,
    )
    assert "verification" not in options(r.json()) and "judge" not in options(r.json())


def test_a_level_in_the_message_is_taken_without_asking(settings):
    said = [
        (
            "create_output",
            {"kind": "quiz", "options": {"question_count": 5, "verification": "thorough"}},
        ),
        ("create_output", {"kind": "report", "options": {"verification": "basic"}}),
        ("create_output", {"kind": "table", "options": {"verification": "default"}}),
        ("create_output", {"kind": "mindmap", "options": {"judge": "low"}}),  # an older planner
    ]
    store, _, _, client = setup(settings, [said, said])
    store.preferences[OWNER] = {"verification_level": "standard"}
    plan = ask(client, "A quiz checked thoroughly, a report unchecked, a table checked.")["plan"]
    assert plan["status"] == "proposed" and plan["question"] is None
    assert options(plan, 1)["verification"] == "thorough"
    assert "verification" not in options(plan, 2)  # basic is the absent default
    assert options(plan, 3)["verification"] == "standard"  # "checked": the user's own level
    assert options(plan, 4)["verification"] == "standard"  # judge low reads as standard
    store.preferences[OWNER] = {"verification_level": "basic"}
    again = ask(client, "The same with a check.")["plan"]
    assert options(again, 3)["verification"] == "thorough"  # they asked for a check


def test_an_older_judge_default_reads_as_its_level(settings):
    store, _, _, client = setup(settings, [QUIZ])
    store.preferences[OWNER] = {"judge_default": "low"}
    question = ask(client, "Make a quiz.")["plan"]["question"]
    assert question["default"] == "verification:standard"


def test_answers_that_do_not_fit_are_refused(settings):
    store, _, _, client = setup(settings, [QUIZ])
    store.preferences[OWNER] = {"verification_level": "standard"}
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    path, qid = plan_path(plan["plan_id"]), plan["question"]["question_id"]
    for body, status in (
        ({"question_id": qid, "choice": "verification:extreme"}, 422),
        ({"question_id": qid, "text": "maybe"}, 422),
        ({"question_id": qid}, 422),
        ({"question_id": "other", "choice": "verification:basic"}, 409),
    ):
        assert client.post(f"{path}/answer", json=body, headers=AUTH).status_code == status
    ok = {"question_id": qid, "choice": "verification:basic"}
    assert client.post(f"{path}/answer", json=ok, headers=AUTH).status_code == 200
    assert client.post(f"{path}/answer", json=ok, headers=AUTH).status_code == 409  # answered
    # a plan that asks can be cancelled
    store2, _, _, client2 = setup(settings, [QUIZ])
    store2.preferences[OWNER] = {"verification_level": "thorough"}
    asking = ask(client2, "Make a quiz.")["plan"]
    r = client2.post(f"{plan_path(asking['plan_id'])}/cancel", headers=AUTH)
    assert r.json()["status"] == "cancelled"
