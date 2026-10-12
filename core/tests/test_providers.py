from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from lasteverlm_core import OpenAICompatibleEmbedder, OpenAICompatibleLLM, ProviderError


class FakeEmbeddings:
    def __init__(self, dims: int, tokens: int = 9) -> None:
        self.dims, self.tokens = dims, tokens

    def create(self, model: str, input: list[str]) -> Any:  # noqa: A002
        data = [SimpleNamespace(index=i, embedding=[0.0] * self.dims) for i in range(len(input))]
        return SimpleNamespace(
            data=list(reversed(data)), usage=SimpleNamespace(prompt_tokens=self.tokens)
        )


class FakeCompletions:
    kwargs: dict[str, Any]

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="answer [1]"))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=5),
        )


def fake_client(dims: int = 4) -> Any:
    return SimpleNamespace(
        embeddings=FakeEmbeddings(dims), chat=SimpleNamespace(completions=FakeCompletions())
    )


def test_embedder_orders_vectors_and_reports_usage() -> None:
    embedder = OpenAICompatibleEmbedder(fake_client(), "embed", 4)
    result = embedder.embed(["a", "b"])
    assert len(result.vectors) == 2 and all(len(v) == 4 for v in result.vectors)
    assert (result.usage.kind, result.usage.model, result.usage.tokens_in) == (
        "embedding",
        "embed",
        9,
    )
    assert embedder.embed([]).usage.tokens_in == 0


def test_embedder_rejects_wrong_dimension() -> None:
    with pytest.raises(ProviderError, match="dimensions"):
        OpenAICompatibleEmbedder(fake_client(dims=3), "embed", 4).embed(["a"])


def test_llm_reports_both_token_counts() -> None:
    client = fake_client()
    result = OpenAICompatibleLLM(client, "llm").complete("sys", "usr", max_tokens=50)
    assert result.text == "answer [1]"
    assert (result.usage.tokens_in, result.usage.tokens_out) == (11, 5)
    assert client.chat.completions.kwargs["max_tokens"] == 50
    assert client.chat.completions.kwargs["messages"][0] == {"role": "system", "content": "sys"}
