"""One summary per source, written at the end of processing.

The output generators in the rag service take the summaries of all
sources of a notebook as their input, so a summary is short — one
paragraph — and in the language of the source. The implementation is a
prompt on top of core's `LLM` interface; the provider is whatever core's
`make_client` points at.
"""

from __future__ import annotations

from typing import Protocol

from lasteverlm_core import LLM, TOKEN, CompletionResult, Passage, ProviderError

SYSTEM_PROMPT = (
    "You summarize documents for a research notebook. Write one paragraph, "
    "at most about 120 words, in the same language as the document. State "
    "what the document is and what it says; no preamble, no bullet points, "
    "no quotation marks around the summary."
)


class Summarizer(Protocol):
    @property
    def model(self) -> str: ...

    def summarize(self, name: str, passages: list[Passage]) -> CompletionResult: ...


def head_text(passages: list[Passage], max_tokens: int) -> str:
    """The first `max_tokens` tokens of the source, so that a long
    document still fits one request. The cut is on a token boundary."""
    parts: list[str] = []
    remaining = max_tokens
    for passage in passages:
        if remaining <= 0:
            break
        tokens = list(TOKEN.finditer(passage.text))
        if len(tokens) <= remaining:
            parts.append(passage.text.strip())
            remaining -= len(tokens)
        else:
            parts.append(passage.text[: tokens[remaining - 1].end()].strip())
            remaining = 0
    return "\n\n".join(part for part in parts if part)


class LLMSummarizer:
    def __init__(self, llm: LLM, *, input_tokens: int = 6000, max_output_tokens: int = 300) -> None:
        self._llm = llm
        self._input_tokens = input_tokens
        self._max_output_tokens = max_output_tokens

    @property
    def model(self) -> str:
        return self._llm.model

    def summarize(self, name: str, passages: list[Passage]) -> CompletionResult:
        text = head_text(passages, self._input_tokens)
        if not text:
            raise ProviderError("nothing to summarize")
        result = self._llm.complete(
            SYSTEM_PROMPT, f"Document name: {name}\n\n{text}", self._max_output_tokens
        )
        summary = result.text.strip()
        if not summary:
            raise ProviderError("model returned an empty summary")
        return CompletionResult(summary, result.usage)
