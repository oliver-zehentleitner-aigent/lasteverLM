"""Cut the passages of a source into overlapping token windows.

A token here is a word or a single punctuation character, found with a
regular expression. That is an approximation of a model tokenizer, good
to within the "about 800 tokens" the contract asks for, and it needs no
vocabulary file at runtime and no dependency on one provider's tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from lasteverlm_ingest.loaders import Passage

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Chunk:
    idx: int
    page: int | None
    text: str


class Chunker(Protocol):
    def chunk(self, passages: list[Passage]) -> list[Chunk]: ...


@dataclass(frozen=True)
class _Token:
    passage: int
    start: int
    end: int


class TokenWindowChunker:
    """Fixed-size windows of `size` tokens, each starting `size - overlap`
    tokens after the previous one. A window may span passages (pages); it
    carries the page of its first token, and passage boundaries inside it
    are kept as blank lines."""

    def __init__(self, size: int = 800, overlap: int = 100) -> None:
        if size <= 0:
            raise ValueError("chunk size must be positive")
        if not 0 <= overlap < size:
            raise ValueError("overlap must be >= 0 and smaller than the chunk size")
        self.size = size
        self.overlap = overlap

    def chunk(self, passages: list[Passage]) -> list[Chunk]:
        tokens = [
            _Token(i, m.start(), m.end())
            for i, passage in enumerate(passages)
            for m in _TOKEN.finditer(passage.text)
        ]
        if not tokens:
            return []
        step = self.size - self.overlap
        chunks: list[Chunk] = []
        start = 0
        while True:
            window = tokens[start : start + self.size]
            chunks.append(
                Chunk(
                    idx=len(chunks),
                    page=passages[window[0].passage].page,
                    text=self._text(passages, window),
                )
            )
            if start + self.size >= len(tokens):
                return chunks
            start += step

    @staticmethod
    def _text(passages: list[Passage], window: list[_Token]) -> str:
        parts: list[str] = []
        first = window[0]
        current, begin = first.passage, first.start
        last_end = first.end
        for token in window[1:]:
            if token.passage != current:
                parts.append(passages[current].text[begin:last_end])
                current, begin = token.passage, token.start
            last_end = token.end
        parts.append(passages[current].text[begin:last_end])
        return "\n\n".join(part.strip() for part in parts if part.strip())
