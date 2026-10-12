"""The one implementation: any OpenAI-compatible API through the OpenAI SDK.

Vultr Serverless Inference in production; anything with the same request
shape elsewhere. `make_client` builds the client from `InferenceSettings`
so the services share timeout and retry behaviour.
"""

from __future__ import annotations

from openai import APIError, OpenAI

from ..settings import InferenceSettings
from .base import CompletionResult, EmbeddingResult, ProviderError, Usage


def make_client(settings: InferenceSettings, timeout: float = 60.0, max_retries: int = 2) -> OpenAI:
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


class OpenAICompatibleEmbedder:
    def __init__(self, client: OpenAI, model: str, dimension: int) -> None:
        self._client = client
        self._model = model
        self._dimension = dimension

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult([], Usage("embedding", self._model, 0, 0))
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except APIError as exc:
            raise ProviderError(f"embedding request failed: {exc}") from exc
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        if len(vectors) != len(texts):
            raise ProviderError(f"provider returned {len(vectors)} vectors for {len(texts)} inputs")
        for vector in vectors:
            if len(vector) != self._dimension:
                raise ProviderError(
                    f"embedding model {self._model} returned {len(vector)} dimensions, "
                    f"EMBEDDING_DIMENSION is {self._dimension}"
                )
        tokens = response.usage.prompt_tokens if response.usage else 0
        return EmbeddingResult(vectors, Usage("embedding", self._model, tokens, 0))


class OpenAICompatibleLLM:
    def __init__(self, client: OpenAI, model: str, temperature: float = 0.0) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system: str, user: str, max_tokens: int) -> CompletionResult:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except APIError as exc:
            raise ProviderError(f"completion request failed: {exc}") from exc
        if not response.choices:
            raise ProviderError("provider returned no choices")
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

    def __init__(self, client: OpenAI, model: str, voice: str = "alloy") -> None:
        self._client = client
        self._model = model
        self._voice = voice

    @property
    def model(self) -> str:
        return self._model

    def synthesize(self, text: str) -> bytes:
        try:
            response = self._client.audio.speech.create(
                model=self._model, voice=self._voice, input=text
            )
        except APIError as exc:
            raise ProviderError(f"speech request failed: {exc}") from exc
        return response.content
