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

import json
import math
from collections.abc import Mapping
from typing import Any

from openai import APIError, APIStatusError, OpenAI

from ..audio import AudioError, billed_seconds, measure_audio, probe_audio
from ..settings import InferenceSettings
from .base import (
    CompletionResult,
    DecisionResult,
    EmbeddingResult,
    ProviderError,
    SpeechResult,
    ToolCall,
    ToolCompletion,
    TranscriptionResult,
    Usage,
)

DEFAULT_MAX_TOKENS = 1024


def make_client(
    settings: InferenceSettings, timeout: float | None = None, max_retries: int = 2
) -> OpenAI:
    """The SDK client every provider shares: one timeout and retry policy for the family.

    `timeout` (seconds per request) defaults to `settings.llm_timeout_seconds`
    (`LLM_TIMEOUT_SECONDS`, 60); a worker with long generations passes more.
    """
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.llm_timeout_seconds if timeout is None else timeout,
        max_retries=max_retries,
    )


# 4xx answers that may change on a retry: timeout, conflict, rate limit.
_TRANSIENT_CLIENT_ERRORS = frozenset({408, 409, 429})


def _request_failed(what: str, exc: APIError) -> ProviderError:
    """The `ProviderError` for a failed request: `permanent` when the
    platform refused it with a 4xx a retry will not change (a file over its
    limits, an unknown voice, a malformed request)."""
    status = exc.status_code if isinstance(exc, APIStatusError) else None
    permanent = (
        status is not None and 400 <= status < 500 and status not in _TRANSIENT_CLIENT_ERRORS
    )
    reason = f"HTTP {status}" if status is not None else type(exc).__name__
    return ProviderError(
        f"{what} request failed: {exc}",
        permanent=permanent,
        status=status,
        summary=f"{what} request failed: {reason}",
    )


def thinking_body(enabled: bool) -> dict[str, Any]:
    """The request fields that switch the model's reasoning on or off.

    `chat_template_kwargs.enable_thinking` is what vLLM-style servers
    read for the Qwen family and what the platform honours; a top-level
    `enable_thinking` is ignored there.
    """
    return {"chat_template_kwargs": {"enable_thinking": enabled}}


class OpenAICompatibleEmbedder:
    """Embeddings over `/embeddings`, always asking for `dimension`; bad vectors are errors."""

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
            raise _request_failed("embedding", exc) from exc
        if response.usage is None:
            raise ProviderError(f"embedding model {self._model} reported no usage")
        usage = Usage("embedding", self._model, response.usage.prompt_tokens, 0)
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        if len(vectors) != len(texts):
            raise ProviderError(
                f"provider returned {len(vectors)} vectors for {len(texts)} inputs", usage
            )
        for i, vector in enumerate(vectors):
            if len(vector) != self._dimension:
                raise ProviderError(
                    f"embedding model {self._model} returned {len(vector)} dimensions "
                    f"although {self._dimension} were requested (EMBEDDING_DIMENSION)",
                    usage,
                )
            # Cosine distance against such a vector is NaN in pgvector: the
            # similarity floor drops the chunk silently and its source stays
            # "ready" while unsearchable. Fail the call instead.
            if not all(math.isfinite(x) for x in vector):
                raise ProviderError(
                    f"embedding model {self._model} returned an unusable vector "
                    f"(non-finite component) for input {i}",
                    usage,
                )
            if sum(x * x for x in vector) == 0.0:
                raise ProviderError(
                    f"embedding model {self._model} returned an unusable vector "
                    f"(zero norm) for input {i}",
                    usage,
                )
        return EmbeddingResult(vectors, usage)


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

    def _chat(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None,
        think: bool,
        **extra: Any,
    ) -> tuple[Any, Usage]:
        """One chat completion: the first choice and the usage to record."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens if max_tokens is None else max_tokens,
                temperature=self._temperature,
                messages=messages,  # type: ignore[arg-type]  # plain dicts, as the API takes them
                extra_body=thinking_body(think),
                **extra,
            )
        except APIError as exc:
            raise _request_failed("completion", exc) from exc
        if response.usage is None:
            raise ProviderError(f"language model {self._model} reported no usage")
        usage = Usage(
            "llm", self._model, response.usage.prompt_tokens, response.usage.completion_tokens
        )
        if not response.choices:
            raise ProviderError("provider returned no choices", usage)
        return response.choices[0], usage

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        *,
        thinking: bool | None = None,
    ) -> CompletionResult:
        think = self._thinking if thinking is None else thinking
        choice, usage = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens,
            think,
        )
        text = (choice.message.content or "").strip()
        if not text and not think:
            # billed all the same: the caller records `usage` before re-raising
            raise ProviderError(
                f"provider returned an empty answer (finish_reason={choice.finish_reason!r})",
                usage,
            )
        return CompletionResult(text, usage, finish_reason=choice.finish_reason)

    def complete_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int | None = None,
        *,
        thinking: bool | None = None,
        tool_choice: str = "auto",
    ) -> ToolCompletion:
        """A chat turn with tools on offer.

        `messages` is the history after the system prompt (user, assistant
        and tool turns, as the API takes them); `tools` is the API's
        `[{"type": "function", "function": {name, description,
        parameters}}]`. The calls come back with their arguments parsed; an
        argument string that is not a JSON object is a `ProviderError`
        carrying the usage, as is, with thinking off, a reply with neither
        text nor calls. Timeout, retries and errors are those of `complete`.
        """
        think = self._thinking if thinking is None else thinking
        choice, usage = self._chat(
            [{"role": "system", "content": system}, *messages],
            max_tokens,
            think,
            tools=tools,
            tool_choice=tool_choice,
        )
        calls = [_tool_call(call, usage) for call in choice.message.tool_calls or []]
        text = (choice.message.content or "").strip()
        if not text and not calls and not think:
            raise ProviderError(
                f"provider returned an empty answer (finish_reason={choice.finish_reason!r})",
                usage,
            )
        return ToolCompletion(text, calls, usage, finish_reason=choice.finish_reason)


def _tool_call(call: Any, usage: Usage) -> ToolCall:
    function = getattr(call, "function", None)
    if function is None:
        raise ProviderError(f"provider returned a tool call of type {call.type!r}", usage)
    raw = function.arguments or "{}"  # a call without parameters may send ""
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"tool call {function.name!r} has arguments that are not JSON: {exc}", usage
        ) from exc
    if not isinstance(arguments, dict):
        raise ProviderError(
            f"tool call {function.name!r} has arguments that are not an object", usage
        )
    return ToolCall(call.id, function.name, arguments)


DEFAULT_TTS_VOICE = "ryan"


class OpenAICompatibleTextToSpeech:
    """Speech synthesis over `/audio/speech`; returns the MP3 bytes and their usage.

    The platform's voices are not the OpenAI names (`alloy` is rejected with
    a 400); it offers vivian, serena, uncle_fu, dylan, eric, ryan, aiden,
    ono_anna and sohee. `synthesize` takes a voice per call (the
    constructor's otherwise) and a `speed`, sent only when given; the
    platform accepts 0.25 to 4 and answers anything else with a 400.

    The platform bills seconds of generated speech and reports them only in
    the `x-usage-seconds` response header (whole seconds, rounded up; no
    usage body). That number is the usage, kind `tts`, in `tokens_in`. A
    response without a readable header is a `ProviderError` carrying the
    duration measured from the MP3, so the caller still records the call;
    empty audio is one too, with the reported usage.
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
    ) -> SpeechResult:
        extra: dict[str, Any] = {} if speed is None else {"speed": speed}
        try:
            response = self._client.audio.speech.with_raw_response.create(
                model=self._model, voice=voice or self._voice, input=text, **extra
            )
        except APIError as exc:
            raise _request_failed("speech", exc) from exc
        audio = response.content
        reported = _whole_seconds(response.headers.get("x-usage-seconds"))
        if reported is None:
            raise ProviderError(
                f"speech model {self._model} reported no x-usage-seconds",
                self._measured(audio),
            )
        usage = Usage("tts", self._model, reported, 0)
        if not audio:
            raise ProviderError(f"speech model {self._model} returned no audio", usage)
        return SpeechResult(audio, usage)

    def _measured(self, audio: bytes) -> Usage | None:
        """The usage measured from the MP3, or `None` when it cannot be read."""
        try:
            return Usage("tts", self._model, billed_seconds(measure_audio(audio).seconds), 0)
        except AudioError:
            return None


def _whole_seconds(header: str | None) -> int | None:
    """A non-negative usage header as whole seconds rounded up, else `None`."""
    try:
        value = float(header) if header is not None else math.nan
    except ValueError:
        return None
    return math.ceil(value) if math.isfinite(value) and value >= 0 else None


class OpenAICompatibleSpeechToText:
    """Transcription over `/audio/transcriptions`, multipart, `response_format=json`.

    The upload is checked by `probe_audio` first (WAV or MP3, 25 MiB,
    four hours), so `AudioError` is raised before any call. The platform
    answers `usage: {"type": "duration", "seconds": n}`; that number is
    what it bills and what is recorded. A response without it is a
    `ProviderError` carrying the measured duration as usage, so the
    caller still records the call; an empty transcript is one too, with
    the reported usage. No timestamps: `verbose_json` is a 400 there.
    """

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        info = probe_audio(audio)
        try:
            response = self._client.audio.transcriptions.create(
                model=self._model,
                file=(filename, audio, info.mime),
                response_format="json",
            )
        except APIError as exc:
            raise _request_failed("transcription", exc) from exc
        reported = response.usage
        if reported is None or reported.type != "duration":
            measured = Usage("stt", self._model, billed_seconds(info.seconds), 0)
            raise ProviderError(
                f"speech-to-text model {self._model} reported no duration usage", measured
            )
        usage = Usage("stt", self._model, billed_seconds(reported.seconds), 0)
        text = response.text.strip()
        if not text:
            raise ProviderError(f"speech-to-text model {self._model} recognised no speech", usage)
        return TranscriptionResult(text, usage, info.seconds)


# The platform's limits for `/systemone` (its OpenAPI, 2026-10-14).
MAX_DECISION_QUESTIONS = 64
MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10
DECISION_TYPES = ("noul", "choice", "score")
_QUESTION_KEYS = frozenset({"type", "instructions", "criteria"})
# What every answer of a type must carry.
_ANSWER_KEYS = {
    "noul": ("noul",),
    "choice": ("choice", "probabilities", "confidence"),
    "score": ("score", "legend", "probabilities", "confidence"),
}


def validate_decision_questions(questions: Mapping[str, Mapping[str, Any]]) -> None:
    """`ValueError` for questions the platform would refuse with a 422, so a
    malformed request never reaches it: 1 to 64 questions with non-empty
    ids; `type` noul, choice or score; no keys besides `type`,
    `instructions`, `criteria`; noul criteria at most `{"true", "false"}`,
    choice criteria a mapping of 1 to 255 options, score criteria a list
    of 1 to 10 levels, lowest first."""
    if not 1 <= len(questions) <= MAX_DECISION_QUESTIONS:
        raise ValueError(f"1 to {MAX_DECISION_QUESTIONS} questions, got {len(questions)}")
    for qid, question in questions.items():
        if not isinstance(qid, str) or not qid:
            raise ValueError("question ids must be non-empty strings")
        unknown = set(question) - _QUESTION_KEYS
        if unknown:
            raise ValueError(f"{qid}: unknown keys {sorted(unknown)}")
        kind = question.get("type")
        criteria = question.get("criteria")
        if kind == "noul":
            if criteria is not None and (
                not isinstance(criteria, Mapping) or not set(criteria) <= {"true", "false"}
            ):
                raise ValueError(f'{qid}: noul criteria may only describe "true" and "false"')
        elif kind == "choice":
            if not isinstance(criteria, Mapping) or not 1 <= len(criteria) <= MAX_CHOICE_OPTIONS:
                raise ValueError(
                    f"{qid}: choice criteria must map 1 to {MAX_CHOICE_OPTIONS} options "
                    "to a description or None"
                )
        elif kind == "score":
            if not isinstance(criteria, list) or not 1 <= len(criteria) <= MAX_SCORE_LEVELS:
                raise ValueError(
                    f"{qid}: score criteria must list 1 to {MAX_SCORE_LEVELS} levels, lowest first"
                )
        else:
            raise ValueError(f"{qid}: type must be one of {', '.join(DECISION_TYPES)}")


class OpenAICompatibleDecision:
    """Typed questions about a state over the platform's `/systemone`.

    The OpenAI SDK has no such call; its generic `post` sends it, so the
    request shares the client's key, base URL, timeout and retries, and an
    HTTP error maps like every other call (a 422, an input over the
    model's length or a malformed question, is `permanent`). The questions
    are checked by `validate_decision_questions` first. Usage is the
    response's `usage.input_tokens`, kind `decision`; a response without
    it is a `ProviderError`. So is a response that misses a question or
    answers it with another type, carrying the usage.
    """

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def decide(self, state: Any, questions: Mapping[str, Mapping[str, Any]]) -> DecisionResult:
        validate_decision_questions(questions)
        body = {
            "model": self._model,
            "state": state,
            "questions": {qid: dict(q) for qid, q in questions.items()},
        }
        try:
            response = self._client.post("/systemone", body=body, cast_to=object)
        except APIError as exc:
            raise _request_failed("decision", exc) from exc
        if not isinstance(response, dict):
            raise ProviderError(f"decision model {self._model} returned no JSON object")
        tokens = (response.get("usage") or {}).get("input_tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            raise ProviderError(f"decision model {self._model} reported no usage")
        usage = Usage("decision", self._model, tokens, 0)
        answers = response.get("answers")
        if not isinstance(answers, dict):
            raise ProviderError(f"decision model {self._model} returned no answers", usage)
        for qid, question in questions.items():
            answer = answers.get(qid)
            kind = question["type"]
            if not isinstance(answer, dict) or answer.get("type") != kind:
                raise ProviderError(
                    f"decision model {self._model} did not answer {qid!r} as {kind}", usage
                )
            missing = [key for key in _ANSWER_KEYS[kind] if key not in answer]
            if missing:
                raise ProviderError(
                    f"decision model {self._model} answered {qid!r} without {missing}", usage
                )
        return DecisionResult({qid: answers[qid] for qid in questions}, usage)
