"""The decision provider through the real OpenAI SDK against a fake transport:
what `/systemone` receives, how its answers and usage are read, and what
is refused before any request."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from openai import OpenAI

from lasteverlm_core import (
    DEFAULT_DECISION_MODEL,
    InferenceSettings,
    OpenAICompatibleDecision,
    ProviderError,
    Usage,
    validate_decision_questions,
)

QUESTIONS: dict[str, dict[str, Any]] = {
    "growth": {"type": "noul", "instructions": "Did revenue grow?"},
    "risk": {
        "type": "choice",
        "instructions": "Biggest risk?",
        "criteria": {"churn": "customers leaving", "pricing": None},
    },
    "health": {"type": "score", "criteria": ["poor", "mixed", "good"]},
}

# The shape the platform answered with in the live probe of 2026-10-14.
ANSWERS = {
    "growth": {"type": "noul", "noul": 0.98},
    "risk": {
        "type": "choice",
        "choice": "churn",
        "probabilities": {"churn": 0.82, "pricing": 0.18},
        "confidence": 0.64,
    },
    "health": {
        "type": "score",
        "score": 1.04,
        "legend": {"0": "poor", "1": "mixed", "2": "good"},
        "probabilities": {"0": 0.03, "1": 0.91, "2": 0.06},
        "confidence": 0.86,
    },
}


def decision_client(requests: list[httpx.Request], answer: Any = None, status: int = 200) -> OpenAI:
    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        requests.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": "too long"}})
        return httpx.Response(200, json=answer)

    return OpenAI(
        base_url="http://fake/v1",
        api_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )


def test_decide_posts_state_and_questions_and_reads_answers_and_usage() -> None:
    requests: list[httpx.Request] = []
    body = {"model": "clef", "answers": ANSWERS, "usage": {"input_tokens": 348, "output_tokens": 0}}
    decision = OpenAICompatibleDecision(decision_client(requests, body), "clef")
    result = decision.decide({"report": "Revenue grew."}, QUESTIONS)
    assert result.answers == ANSWERS
    assert result.usage == Usage("decision", "clef", 348, 0)
    (request,) = requests
    assert request.method == "POST" and request.url.path == "/v1/systemone"
    assert json.loads(request.content) == {
        "model": "clef",
        "state": {"report": "Revenue grew."},
        "questions": QUESTIONS,
    }


def test_only_the_asked_questions_come_back() -> None:
    body = {
        "answers": {**ANSWERS, "extra": {"type": "noul", "noul": 1}},
        "usage": {"input_tokens": 1},
    }
    result = OpenAICompatibleDecision(decision_client([], body), "clef").decide("s", QUESTIONS)
    assert set(result.answers) == set(QUESTIONS)


def test_a_response_without_usage_is_an_error() -> None:
    decision = OpenAICompatibleDecision(decision_client([], {"answers": ANSWERS}), "clef")
    with pytest.raises(ProviderError, match="reported no usage") as caught:
        decision.decide("s", QUESTIONS)
    assert caught.value.usage is None


@pytest.mark.parametrize(
    "answers",
    [
        {k: v for k, v in ANSWERS.items() if k != "risk"},  # a question missing
        {**ANSWERS, "risk": {"type": "noul", "noul": 0.5}},  # answered as another type
        {**ANSWERS, "health": {"type": "score", "score": 1.0}},  # without its distribution
    ],
)
def test_an_incomplete_answer_is_an_error_carrying_the_usage(answers: dict[str, Any]) -> None:
    body = {"answers": answers, "usage": {"input_tokens": 50, "output_tokens": 0}}
    decision = OpenAICompatibleDecision(decision_client([], body), "clef")
    with pytest.raises(ProviderError, match="decision model clef") as caught:
        decision.decide("s", QUESTIONS)
    assert caught.value.usage == Usage("decision", "clef", 50, 0)


@pytest.mark.parametrize(("status", "permanent"), [(422, True), (429, False), (529, False)])
def test_http_errors_map_like_every_call(status: int, permanent: bool) -> None:
    decision = OpenAICompatibleDecision(decision_client([], status=status), "clef")
    with pytest.raises(ProviderError, match="decision request failed") as caught:
        decision.decide("s", QUESTIONS)
    assert caught.value.permanent is permanent


@pytest.mark.parametrize(
    ("questions", "message"),
    [
        ({}, "1 to 64 questions"),
        ({f"q{i}": {"type": "noul"} for i in range(65)}, "1 to 64 questions"),
        ({"": {"type": "noul"}}, "non-empty"),
        ({"a": {"type": "rank"}}, "type must be one of"),
        ({"a": {"type": "noul", "hint": "x"}}, "unknown keys"),
        ({"a": {"type": "noul", "criteria": {"maybe": "x"}}}, '"true" and "false"'),
        ({"a": {"type": "choice"}}, "1 to 255 options"),
        ({"a": {"type": "choice", "criteria": {}}}, "1 to 255 options"),
        ({"a": {"type": "choice", "criteria": {str(i): None for i in range(256)}}}, "255"),
        ({"a": {"type": "score", "criteria": {"low": "x"}}}, "1 to 10 levels"),
        ({"a": {"type": "score", "criteria": [str(i) for i in range(11)]}}, "1 to 10 levels"),
    ],
)
def test_malformed_questions_are_refused_before_any_request(
    questions: dict[str, Any], message: str
) -> None:
    requests: list[httpx.Request] = []
    decision = OpenAICompatibleDecision(decision_client(requests, {}), "clef")
    with pytest.raises(ValueError, match=message):
        decision.decide("s", questions)
    assert requests == []


def test_well_formed_edges_pass_validation() -> None:
    validate_decision_questions(
        {
            "yes": {"type": "noul", "criteria": {"true": "it does", "false": None}},
            "one": {"type": "choice", "criteria": {"only": None}},
            "ten": {"type": "score", "criteria": [None] * 10},
            **{f"q{i}": {"type": "noul"} for i in range(61)},
        }
    )


def test_decision_model_setting_defaults_to_clef() -> None:
    env = {"INFERENCE_API_KEY": "k", "LLM_MODEL": "l", "EMBEDDING_MODEL": "e"}
    assert InferenceSettings.from_env(env).decision_model == DEFAULT_DECISION_MODEL == "clef"
    assert InferenceSettings.from_env({**env, "DECISION_MODEL": "clef-flash"}).decision_model == (
        "clef-flash"
    )
