"""One summary per source, written at the end of processing.

The output generators in the rag service take the summaries of all
sources of a notebook as their input, so a summary is short — one
paragraph — and in the language of the source. The one implementation
calls an OpenAI-compatible chat completion through the OpenAI SDK.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from openai import APIError, OpenAI

from lasteverlm_ingest.loaders import Passage

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)

SYSTEM_PROMPT = (
    "You summarize documents for a research notebook. Write one paragraph, "
    "at most about 120 words, in the same language as the document. State "
    "what the document is and what it says; no preamble, no bullet points, "
    "no quotation marks around the summary."
)


class SummaryError(Exception):
    pass


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    model: str
    tokens_in: int
    tokens_out: int


class Summarizer(Protocol):
    @property
    def model(self) -> str: ...

    def summarize(self, name: str, passages: list[Passage]) -> SummaryResult: ...


def head_text(passages: list[Passage], max_tokens: int) -> str:
    """The first `max_tokens` tokens of the source, so that a long
    document still fits one request. The cut is on a token boundary."""
    parts: list[str] = []
    remaining = max_tokens
    for passage in passages:
        if remaining <= 0:
            break
        tokens = list(_TOKEN.finditer(passage.text))
        if len(tokens) <= remaining:
            parts.append(passage.text.strip())
            remaining -= len(tokens)
        else:
            parts.append(passage.text[: tokens[remaining - 1].end()].strip())
            remaining = 0
    return "\n\n".join(part for part in parts if part)


class OpenAICompatibleSummarizer:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        input_tokens: int = 6000,
        max_output_tokens: int = 300,
        timeout: float = 120.0,
        client: OpenAI | None = None,
    ) -> None:
        self._model = model
        self._input_tokens = input_tokens
        self._max_output_tokens = max_output_tokens
        self._client = client or OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=2
        )

    @property
    def model(self) -> str:
        return self._model

    def summarize(self, name: str, passages: list[Passage]) -> SummaryResult:
        text = head_text(passages, self._input_tokens)
        if not text:
            raise SummaryError("nothing to summarize")
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_output_tokens,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Document name: {name}\n\n{text}"},
                ],
            )
        except APIError as exc:
            raise SummaryError(f"summary request failed: {exc}") from exc
        content = (response.choices[0].message.content or "").strip() if response.choices else ""
        if not content:
            raise SummaryError("model returned an empty summary")
        usage = response.usage
        return SummaryResult(
            summary=content,
            model=response.model or self._model,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
        )
