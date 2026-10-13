"""The one implementation: any OpenAI-compatible API through the OpenAI SDK.

Vultr Serverless Inference in production; anything with the same request
shape elsewhere. `make_client` builds the client from `InferenceSettings`
so the services share timeout and retry behaviour.

Two facts of the platform shape this module (context/providers.md):
the embedding model's native width is above pgvector's index limit, so
every embedding call asks for `EMBEDDING_DIMENSION` through the
standard `dimensions` parameter; and the language model reasons by
default, spending `max_tokens` on thinking and returning empty content
when the budget is small, so thinking is off unless a caller asks.
"""

from __future__ import annotations

import math
from typing import Any

from openai import APIError, OpenAI

from ..settings import InferenceSettings
from .base import CompletionResult, EmbeddingResult, ProviderError, Usage

DEFAULT_MAX_TOKENS = 1024


def make_client(settings: InferenceSettings, timeout: float = 60.0, max_retries: int = 2) -> OpenAI:
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


def thinking_body(enabled: bool) -> dict[str, Any]:
    """The request fields that switch the model's reasoning on or off.

    `chat_template_kwargs.enable_thinking` is what vLLM-style servers
    read for the Qwen family and what the platform honours; a top-level
    `enable_thinking` is ignored there.
    """
    return {"chat_template_kwargs": {"enable_thinking": enabled}}


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
            response = self._client.embeddings.create(
                model=self._model, input=texts, dimensions=self._dimension
            )
        except APIError as exc:
            raise ProviderError(f"embedding request failed: {exc}") from exc
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        if len(vectors) != len(texts):
            raise ProviderError(f"provider returned {len(vectors)} vectors for {len(texts)} inputs")
        for i, vector in enumerate(vectors):
            if len(vector) != self._dimension:
                raise ProviderError(
                    f"embedding model {self._model} returned {len(vector)} dimensions "
                    f"although {self._dimension} were requested (EMBEDDING_DIMENSION)"
                )
            # Cosine distance against such a vector is NaN in pgvector: the
            # similarity floor drops the chunk silently and its source stays
            # "ready" while unsearchable. Fail the call instead.
            if not all(math.isfinite(x) for x in vector):
                raise ProviderError(
                    f"embedding model {self._model} returned an unusable vector "
                    f"(non-finite component) for input {i}"
                )
            if sum(x * x for x in vector) == 0.0:
                raise ProviderError(
                    f"embedding model {self._model} returned an unusable vector "
                    f"(zero norm) for input {i}"
                )
        tokens = response.usage.prompt_tokens if response.usage else 0
        return EmbeddingResult(vectors, Usage("embedding", self._model, tokens, 0))


class OpenAICompatibleLLM:
    """Chat completions with reasoning off by default.

    `thinking` on the instance is the default for every call, a call's
    own `thinking=` overrides it. `max_tokens` falls back to the
    instance default. With thinking off, an empty answer is an error,
    never silently returned.
    """

    def __init__(
        self,
        client: OpenAI,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        thinking: bool = False,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._thinking = thinking

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        *,
        thinking: bool | None = None,
    ) -> CompletionResult:
        think = self._thinking if thinking is None else thinking
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens if max_tokens is None else max_tokens,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                extra_body=thinking_body(think),
            )
        except APIError as exc:
            raise ProviderError(f"completion request failed: {exc}") from exc
        if not response.choices:
            raise ProviderError("provider returned no choices")
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        usage = response.usage
        result = CompletionResult(
            text,
            Usage(
                "llm",
                self._model,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason,
        )
        if not text and not think:
            raise ProviderError(
                f"provider returned an empty answer (finish_reason={choice.finish_reason!r})"
            )
        return result


DEFAULT_TTS_VOICE = "ryan"


class OpenAICompatibleTextToSpeech:
    """Speech synthesis over `/audio/speech`; returns the MP3 bytes.

    The platform's voices are not the OpenAI names (`alloy` is rejected with
    a 400); it offers vivian, serena, uncle_fu, dylan, eric, ryan, aiden,
    ono_anna and sohee. `synthesize` takes a voice per call (the
    constructor's otherwise) and a `speed`, sent only when given; the
    platform accepts 0.25 to 4 and answers anything else with a 400.
    Usage is priced per input character, which the caller records as
    `tokens_in=len(text)`, `tokens_out=0`, kind `tts`.
    """

    def __init__(self, client: OpenAI, model: str, voice: str = DEFAULT_TTS_VOICE) -> None:
        self._client = client
        self._model = model
        self._voice = voice

    @property
    def model(self) -> str:
        return self._model

    @property
    def voice(self) -> str:
        return self._voice

    def synthesize(
        self, text: str, *, voice: str | None = None, speed: float | None = None
    ) -> bytes:
        extra: dict[str, Any] = {} if speed is None else {"speed": speed}
        try:
            response = self._client.audio.speech.create(
                model=self._model, voice=voice or self._voice, input=text, **extra
            )
        except APIError as exc:
            raise ProviderError(f"speech request failed: {exc}") from exc
        if not response.content:
            raise ProviderError(f"speech model {self._model} returned no audio")
        return response.content
