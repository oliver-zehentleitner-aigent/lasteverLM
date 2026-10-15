"""The agent chat asks an open choice that changes the cost or the result,
instead of deciding it: first use, whether a judge checks the documents."""

from .conftest import AUTH, CONVERSATION, OWNER
from .test_agent import ask, plan_path, setup

QUIZ = [("create_output", {"kind": "quiz", "options": {"question_count": 5}})]


def options(plan, n=1):
    return plan["steps"][n - 1]["args"]["options"]


def test_with_judge_default_off_no_question_and_a_note(settings):
    store, _, _, client = setup(settings, [QUIZ])
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    assert plan["status"] == "proposed" and plan["question"] is None
    assert "judge" not in options(plan)
    assert plan["notes"] == [
        "Without a judge: the new documents are not checked by a second model. "
        "Ask for one if you want it."
    ]
    assert client.post(f"{plan_path(plan['plan_id'])}/confirm", headers=AUTH).status_code == 200


def test_with_a_judge_default_the_plan_asks_and_follows_the_answer(settings):
    store, _, _, client = setup(settings, [QUIZ, QUIZ])
    store.preferences[OWNER] = {"judge_default": "high"}
    body = ask(client, "Make a quiz of 5 questions.")
    plan = body["plan"]
    assert plan["status"] == "asking" and plan["notes"] == []
    question = plan["question"]
    assert [c["id"] for c in question["choices"]] == ["judge:high", "judge:off"]
    assert question["choices"][0]["label"] == "With a judge (High, your default)"
    assert question["default"] == "judge:high" and question["free_text"] is False
    assert "apply" not in question  # how an answer applies stays on the server
    with_judge, without = (c["estimate"]["max"] for c in question["choices"])
    assert with_judge > without
    assert body["answer"].endswith(question["text"])
    path = plan_path(plan["plan_id"])
    # nothing runs before the answer
    r = client.post(f"{path}/confirm", headers=AUTH)
    assert (r.status_code, r.json()) == (409, {"error": "answer the question first"})

    r = client.post(
        f"{path}/answer",
        json={"question_id": question["question_id"], "choice": "judge:high"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    answered = r.json()
    assert answered["status"] == "proposed"
    assert options(answered)["judge"] == "high"
    assert answered["estimate"]["max"] == with_judge
    assert answered["question"]["answer"]["choice"] == "judge:high"
    messages = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "With a judge (High, your default)"
    assert messages[-2]["plan"]["status"] == "proposed"  # the proposing message follows
    assert client.post(f"{path}/confirm", headers=AUTH).json()["status"] == "running"
    # the second plan, answered "without"
    second = ask(client, "Make another quiz.")["plan"]
    r = client.post(
        f"{plan_path(second['plan_id'])}/answer",
        json={"question_id": second["question"]["question_id"], "choice": "judge:off"},
        headers=AUTH,
    )
    assert "judge" not in options(r.json())


def test_an_explicit_judge_in_the_message_is_taken_without_asking(settings):
    said = [
        ("create_output", {"kind": "quiz", "options": {"question_count": 5, "judge": "high"}}),
        ("create_output", {"kind": "report", "options": {"judge": "off"}}),
        ("create_output", {"kind": "table", "options": {"judge": "default"}}),
    ]
    store, _, _, client = setup(settings, [said, said])
    store.preferences[OWNER] = {"judge_default": "low"}
    plan = ask(client, "Make a quiz with judge high, a report ohne Prüfung, a table with judge.")[
        "plan"
    ]
    assert plan["status"] == "proposed" and plan["question"] is None
    assert options(plan, 1)["judge"] == "high"
    assert "judge" not in options(plan, 2)  # "off" is the absent default
    assert options(plan, 3)["judge"] == "low"  # "with a judge": the user's own level
    store.preferences[OWNER] = {"judge_default": "off"}
    again = ask(client, "The same with judge.")["plan"]
    assert options(again, 3)["judge"] == "medium"  # no default level: the middle one


def test_answers_that_do_not_fit_are_refused(settings):
    store, _, _, client = setup(settings, [QUIZ])
    store.preferences[OWNER] = {"judge_default": "medium"}
    plan = ask(client, "Make a quiz of 5 questions.")["plan"]
    path, qid = plan_path(plan["plan_id"]), plan["question"]["question_id"]
    for body, status in (
        ({"question_id": qid, "choice": "judge:extreme"}, 422),
        ({"question_id": qid, "text": "maybe"}, 422),
        ({"question_id": qid}, 422),
        ({"question_id": "other", "choice": "judge:off"}, 409),
    ):
        assert client.post(f"{path}/answer", json=body, headers=AUTH).status_code == status
    ok = {"question_id": qid, "choice": "judge:off"}
    assert client.post(f"{path}/answer", json=ok, headers=AUTH).status_code == 200
    assert client.post(f"{path}/answer", json=ok, headers=AUTH).status_code == 409  # answered
    # a plan that asks can be cancelled
    store2, _, _, client2 = setup(settings, [QUIZ])
    store2.preferences[OWNER] = {"judge_default": "high"}
    asking = ask(client2, "Make a quiz.")["plan"]
    r = client2.post(f"{plan_path(asking['plan_id'])}/cancel", headers=AUTH)
    assert r.json()["status"] == "cancelled"
