"""LLM and embedding calls behind one interface each, implemented once over an
OpenAI-compatible API (Vultr Serverless Inference in production, anything with
the same request shape elsewhere). Both report token usage so every call can be
accounted for.
"""

from __future__ import annotations

from typing import Protocol

from openai import OpenAI

from .models import CompletionResult, EmbeddingResult, Usage


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> EmbeddingResult: ...


class LLM(Protocol):
    def complete(self, system: str, user: str, max_tokens: int) -> CompletionResult: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class OpenAICompatibleEmbedder:
    def __init__(self, client: OpenAI, model: str, dimension: int) -> None:
        self._client = client
        self._model = model
        self._dimension = dimension

    def embed(self, texts: list[str]) -> EmbeddingResult:
        response = self._client.embeddings.create(model=self._model, input=texts)
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        for vector in vectors:
            if len(vector) != self._dimension:
                raise RuntimeError(
                    f"embedding model {self._model} returned {len(vector)} dimensions, "
                    f"EMBEDDING_DIMENSION is {self._dimension}"
                )
        tokens = response.usage.prompt_tokens if response.usage else 0
        return EmbeddingResult(vectors, Usage("embedding", self._model, tokens, 0))


class OpenAICompatibleLLM:
    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, system: str, user: str, max_tokens: int) -> CompletionResult:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = response.choices[0].message.content or ""
        usage = response.usage
        return CompletionResult(
            text,
            Usage(
                "llm",
                self._model,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            ),
        )


class OpenAICompatibleTextToSpeech:
    """Prepared for the day the inference platform offers a speech endpoint."""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def synthesize(self, text: str) -> bytes:
        response = self._client.audio.speech.create(model=self._model, voice="alloy", input=text)
        return response.content


def make_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)
