"""Text-to-speech in segments.

A speech request is slow (about ten seconds per thousand characters on
the platform) and its input limit is not documented, so a script is read
in segments that end at sentence boundaries. The platform returns MP3
frames; MP3 streams concatenate frame by frame, so the segments join
into one file without re-encoding.
"""

from __future__ import annotations

import re

SEGMENT_MAX_CHARS = 1500

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_for_speech(text: str, max_chars: int = SEGMENT_MAX_CHARS) -> list[str]:
    """Segments of at most ``max_chars``, cut after a sentence end where possible,
    else after a space, else hard."""
    segments: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(" ".join(text.split())):
        for piece in _fit(sentence, max_chars):
            if current and len(current) + 1 + len(piece) > max_chars:
                segments.append(current)
                current = piece
            else:
                current = f"{current} {piece}" if current else piece
    if current:
        segments.append(current)
    return segments


def _fit(sentence: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    while len(sentence) > max_chars:
        cut = sentence.rfind(" ", 0, max_chars + 1)
        if cut <= 0:
            cut = max_chars
        pieces.append(sentence[:cut].strip())
        sentence = sentence[cut:].strip()
    if sentence:
        pieces.append(sentence)
    return pieces
