"""The providers through the real OpenAI SDK against a fake HTTP transport, so
what the server receives (the `dimensions` parameter, the thinking switch)
is what is asserted, not what a stub was handed. httpx2 is the HTTP client
the OpenAI SDK (3.x) is built on."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from openai import OpenAI

from lasteverlm_core import (
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    ProviderError,
    thinking_body,
)


class FakeServer:
    """Records every request body and answers from a queue of responses."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return httpx.Response(200, json=self.responses.pop(0))

    def client(self) -> OpenAI:
        return OpenAI(
            base_url="http://fake/v1",
            api_key="test",
            http_client=httpx.Client(transport=httpx.MockTransport(self.handler)),
            max_retries=0,
        )


def embeddings(*vectors: list[float], tokens: int = 9) -> dict[str, Any]:
    data = [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]
    return {
        "object": "list",
        "data": list(reversed(data)),
        "model": "embed",
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


def completion(
    content: str | None, finish: str = "stop", reasoning_tokens: int = 0, **extra: Any
) -> dict[str, Any]:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "llm",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, **extra},
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 5 + reasoning_tokens,
            "total_tokens": 16 + reasoning_tokens,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        },
    }


def test_embedder_requests_the_configured_dimension() -> None:
    server = FakeServer()
    server.responses.append(embeddings([0.0] * 4, [1.0] * 4))
    result = OpenAICompatibleEmbedder(server.client(), "embed", 4).embed(["a", "b"])
    assert server.requests[0]["dimensions"] == 4
    assert server.requests[0]["input"] == ["a", "b"]
    assert result.vectors == [[0.0] * 4, [1.0] * 4]  # ordered by index, not arrival
    assert (result.usage.kind, result.usage.model, result.usage.tokens_in) == (
        "embedding",
        "embed",
        9,
    )


def test_embedder_rejects_a_vector_of_another_width() -> None:
    server = FakeServer()
    server.responses.append(embeddings([0.0] * 2560))
    with pytest.raises(ProviderError, match="2560 dimensions although 1024 were requested"):
        OpenAICompatibleEmbedder(server.client(), "embed", 1024).embed(["a"])


def test_embedder_empty_input_makes_no_request() -> None:
    server = FakeServer()
    result = OpenAICompatibleEmbedder(server.client(), "embed", 4).embed([])
    assert result.vectors == [] and server.requests == []


def test_llm_disables_thinking_by_default_and_reports_tokens() -> None:
    server = FakeServer()
    server.responses.append(completion("\n\nVienna.", reasoning=None))
    llm = OpenAICompatibleLLM(server.client(), "llm")
    result = llm.complete("sys", "usr")
    body = server.requests[0]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["max_tokens"] == 1024
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["temperature"] == 0.0
    assert result.text == "Vienna."
    assert (result.usage.tokens_in, result.usage.tokens_out, result.finish_reason) == (
        11,
        5,
        "stop",
    )


def test_llm_thinking_per_call_and_per_instance() -> None:
    server = FakeServer()
    server.responses += [completion("a"), completion("b"), completion("c")]
    llm = OpenAICompatibleLLM(server.client(), "llm", max_tokens=300, thinking=True)
    llm.complete("s", "u")
    llm.complete("s", "u", thinking=False)
    llm.complete("s", "u", 40)
    assert [r["chat_template_kwargs"]["enable_thinking"] for r in server.requests] == [
        True,
        False,
        True,
    ]
    assert [r["max_tokens"] for r in server.requests] == [300, 300, 40]
    assert thinking_body(False) == {"chat_template_kwargs": {"enable_thinking": False}}


def test_llm_empty_answer_without_thinking_is_an_error() -> None:
    server = FakeServer()
    server.responses.append(completion("", finish="length"))
    with pytest.raises(ProviderError, match="empty answer.*length"):
        OpenAICompatibleLLM(server.client(), "llm").complete("s", "u", 40)


def test_llm_empty_answer_with_thinking_is_returned_for_the_caller_to_judge() -> None:
    server = FakeServer()
    server.responses.append(
        completion("", finish="length", reasoning_tokens=39, reasoning="We need")
    )
    result = OpenAICompatibleLLM(server.client(), "llm", thinking=True).complete("s", "u", 40)
    assert result.text == "" and result.finish_reason == "length"
    assert result.usage.tokens_out == 44  # reasoning tokens are billed completion tokens


def test_llm_http_error_becomes_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad dimensions"}})

    client = OpenAI(
        base_url="http://fake/v1",
        api_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    with pytest.raises(ProviderError, match="completion request failed"):
        OpenAICompatibleLLM(client, "llm").complete("s", "u")
    with pytest.raises(ProviderError, match="embedding request failed"):
        OpenAICompatibleEmbedder(client, "embed", 4).embed(["a"])
