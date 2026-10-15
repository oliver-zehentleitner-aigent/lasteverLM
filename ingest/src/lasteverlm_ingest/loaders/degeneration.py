"""Model-made transcripts that degenerated into a repetition loop.

A vision or speech model can fall into a loop: it writes a few words and
then repeats one phrase until the output cap (a screenshot read as
"SPACES Internet-UI" followed by hundreds of "Internet-UI"). Such text is
not the source and must never be indexed. The check is deterministic, on
word tokens, and calibrated so real text with repeated terms passes: a
table of identical labels, a song's chorus, a list of "Yes" answers.

A transcript is degenerate when one of these holds:

- one n-gram (1 to `MAX_N` words) repeats back to back at least
  `LOOP_REPEATS` times, anywhere: no page or recording does that;
- the answer stopped at the output cap and one back-to-back repetition
  fills at least `CAPPED_TAIL_SHARE` of its last `TAIL_TOKENS` words: the
  model ran until it was cut off, still repeating;
- some `WINDOW_TOKENS` consecutive words hold fewer than
  `MIN_DISTINCT_WORDS` distinct words: prose of that length has hundreds.
  A window, not the whole text, because a long text's share of distinct
  words falls with its length.
"""

from __future__ import annotations

import re

REASON = "the model's description degenerated into repetition"

MAX_N = 8
LOOP_REPEATS = 100
TAIL_TOKENS = 200
CAPPED_TAIL_SHARE = 0.9
WINDOW_TOKENS = 500
MIN_DISTINCT_WORDS = 25

_WORD = re.compile(r"\w+")


def degenerated(text: str, *, capped: bool = False) -> bool:
    """Whether `text` is a repetition loop; `capped` when the model stopped
    at its output cap (finish reason `length`)."""
    tokens = [t.lower() for t in _WORD.findall(text)]
    if longest_run(tokens)[0] >= LOOP_REPEATS:
        return True
    tail = tokens[-TAIL_TOKENS:]
    if (
        capped
        and len(tail) == TAIL_TOKENS
        and longest_run(tail)[1] >= CAPPED_TAIL_SHARE * TAIL_TOKENS
    ):
        return True
    # Half-overlapping windows, and the last one, so the end is covered too.
    windows = [
        *range(0, len(tokens) - WINDOW_TOKENS + 1, WINDOW_TOKENS // 2),
        len(tokens) - WINDOW_TOKENS,
    ]
    windows = [w for w in windows if w >= 0]
    return any(len(set(tokens[w : w + WINDOW_TOKENS])) < MIN_DISTINCT_WORDS for w in windows)


def longest_run(tokens: list[str]) -> tuple[int, int]:
    """The back-to-back repetition of one n-gram (1 to `MAX_N` words) with
    the most repeats, and the most words one such repetition covers."""
    repeats, covered = 1, 0
    for n in range(1, MAX_N + 1):
        for offset in range(n):
            run = 1
            for start in range(offset + n, len(tokens) - n + 1, n):
                if tokens[start : start + n] == tokens[start - n : start]:
                    run += 1
                    repeats, covered = max(repeats, run), max(covered, run * n)
                else:
                    run = 1
    return repeats, covered
