"""Cut text into overlapping token windows before embedding.

The one chunker of the family: ingest cuts parsed sources with it, rag
cuts generated documents with it, so a question embedded against either
meets chunks of the same shape. A token is a word or a single
punctuation character, found with a regular expression. That is a
coarse approximation of a model tokenizer: measured on German text, the
embedding model counts about 1.9 model tokens per regex token, so the
default window of 420 regex tokens lands near the "about 800 tokens"
the contract asks for (about 550 for English). It needs no vocabulary
file at runtime and no dependency on one provider's tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Passage:
    """A run of text from a source and, when the source has pages, its 1-based page."""

    text: str
    page: int | None = None


@dataclass(frozen=True)
class Chunk:
    """One window: its position in the source, the page of its first token, its text."""

    idx: int
    page: int | None
    text: str


class Chunker(Protocol):
    """Splits parsed passages into the chunks that get embedded."""

    def chunk(self, passages: list[Passage]) -> list[Chunk]: ...


@dataclass(frozen=True)
class _Token:
    passage: int
    start: int
    end: int


class TokenWindowChunker:
    """Fixed windows of `size` tokens, each starting `size - overlap` tokens after the last.

    A window may span passages (pages); it carries the page of its first
    token, and passage boundaries inside it are kept as blank lines. The
    text of a window is the original text between its first and last
    token, so spacing inside a passage is preserved.
    """

    def __init__(self, size: int = 420, overlap: int = 50) -> None:
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
            for m in TOKEN.finditer(passage.text)
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

    def chunk_text(self, text: str) -> list[Chunk]:
        """A single passage without pages: what a generated document is."""
        return self.chunk([Passage(text)])

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
