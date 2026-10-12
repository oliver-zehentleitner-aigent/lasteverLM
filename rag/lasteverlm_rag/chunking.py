"""Cut a generated document into overlapping token windows before embedding.

Same approximation as the ingest service: a token is a word or a single
punctuation character; windows of 800 tokens, 100 overlap, per the contract.
Generated documents have no pages, so a chunk is just an index and its text.
"""

from __future__ import annotations

import re

from .models import Chunk

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class TokenWindowChunker:
    def __init__(self, size: int = 800, overlap: int = 100) -> None:
        if size <= 0:
            raise ValueError("chunk size must be positive")
        if not 0 <= overlap < size:
            raise ValueError("overlap must be >= 0 and smaller than the chunk size")
        self.size = size
        self.overlap = overlap

    def chunk(self, text: str) -> list[Chunk]:
        tokens = [(m.start(), m.end()) for m in _TOKEN.finditer(text)]
        if not tokens:
            return []
        step = self.size - self.overlap
        chunks: list[Chunk] = []
        start = 0
        while True:
            window = tokens[start : start + self.size]
            chunks.append(Chunk(idx=len(chunks), text=text[window[0][0] : window[-1][1]].strip()))
            if start + self.size >= len(tokens):
                return chunks
            start += step
