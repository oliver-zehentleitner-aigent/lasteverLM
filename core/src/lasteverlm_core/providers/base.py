"""The provider interfaces every service codes against.

Each call reports its token usage so the caller can write the `usage`
row; a provider that does not report usage is accounted at zero tokens
and the caller sees that in the result. Another provider is one more
module implementing these protocols, selected by configuration; callers
do not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import UsageKind


class ProviderError(Exception):
    """The provider request failed or returned something unusable."""


@dataclass(frozen=True)
class Usage:
    """Token counts of one call, ready for `record_usage`."""

    kind: UsageKind
    model: str
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class EmbeddingResult:
    """One vector per input, in input order, and the usage to record."""

    vectors: list[list[float]]
    usage: Usage


@dataclass(frozen=True)
class CompletionResult:
    """The answer text, the usage to record and why the model stopped."""

    text: str
    usage: Usage
    # "stop" when the model finished, "length" when max_tokens cut it off.
    finish_reason: str | None = None


class Embedder(Protocol):
    """Turns texts into vectors of `dimension` floats; services are typed against this."""

    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> EmbeddingResult: ...


class LLM(Protocol):
    """One system plus one user message in, one completion out."""

    @property
    def model(self) -> str: ...

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        *,
        thinking: bool | None = None,
    ) -> CompletionResult: ...


class TextToSpeech(Protocol):
    """Text in, MP3 bytes out; usage is the caller's to record (per character)."""

    @property
    def model(self) -> str: ...

    def synthesize(
        self, text: str, *, voice: str | None = None, speed: float | None = None
    ) -> bytes: ...
