"""Embedding provider behind one interface.

The one implementation talks to any OpenAI-compatible `/embeddings`
endpoint through the OpenAI SDK; the deployment points it at Vultr
Serverless Inference. The rag service must embed questions with the same
model, which is why the model is configuration shared across services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openai import APIError, OpenAI


class EmbeddingError(Exception):
    pass


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    tokens: int


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> EmbeddingResult: ...


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        timeout: float = 60.0,
        client: OpenAI | None = None,
    ) -> None:
        self._model = model
        self._dimension = dimension
        self._client = client or OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model, tokens=0)
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except APIError as exc:
            raise EmbeddingError(f"embedding request failed: {exc}") from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in ordered]
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"provider returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        for vector in vectors:
            if len(vector) != self._dimension:
                raise EmbeddingError(
                    f"provider returned dimension {len(vector)}, "
                    f"EMBEDDING_DIMENSION is {self._dimension}"
                )
        tokens = response.usage.prompt_tokens if response.usage else 0
        return EmbeddingResult(vectors=vectors, model=response.model or self._model, tokens=tokens)
