"""Scores the vision evaluation's answers against each image's known text.

- lines: the share of the image's text lines found in the answer, case-
  and whitespace-insensitive, a separator dot, bullet or dash between
  words counting as one;
- numbers: the share of the image's numbers found as written;
- invented: numbers in the answer that appear nowhere in the image's text
  (a hallucination signal; read by hand, since a description may count
  things such as "six bars");
- wrong language: the description is not in the language of the image's
  text (a stopword count, English images 01, 02, 04, 06, 08–11);
- degenerate: ingest's own loop check; capped: the answer hit the output cap.

    python -m evals.vision.score truth.json results/*.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from lasteverlm_ingest.loaders.degeneration import degenerated

NUMBER = re.compile(r"\d[\d.,:-]*\d|\d")
ENGLISH_IMAGES = ("01", "02", "04", "06", "08", "09", "10", "11")
GERMAN_WORDS = frozenset(
    [
        "das",
        "die",
        "der",
        "und",
        "mit",
        "ist",
        "ein",
        "eine",
        "zeigt",
        "den",
        "bild",
        "auf",
        "von",
        "im",
    ]
)
ENGLISH_WORDS = frozenset(
    ["the", "and", "with", "is", "a", "an", "shows", "of", "image", "in", "this"]
)


def norm(text: str) -> str:
    return re.sub(r" [·•\-–] ", " · ", " ".join(text.split()).lower().replace("€", ""))


def language(text: str) -> str:
    words = re.findall(r"[a-zäöüß]+", text.lower())
    german = sum(w in GERMAN_WORDS for w in words)
    return "de" if german > sum(w in ENGLISH_WORDS for w in words) else "en"


def score(truth: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    known = truth[row["image"]]
    answer = norm(row["text"])
    lines = [norm(x) for x in known["lines"] if norm(x)]
    numbers = known["numbers"]
    text_of_image = " ".join(known["lines"])
    expected = "en" if row["image"][:2] in ENGLISH_IMAGES else "de"
    return {
        "lines": sum(x in answer for x in lines) / len(lines),
        "numbers": sum(n in row["text"] for n in numbers) / len(numbers) if numbers else None,
        "invented": len({n for n in NUMBER.findall(row["text"]) if n not in text_of_image}),
        "wrong_language": row["image"] != "page.jpg" and language(row["text"]) != expected,
        "degenerate": degenerated(row["text"], capped=row["finish"] == "length"),
        "capped": row["finish"] == "length",
        "tokens_out": row["tokens_out"] or 0,
        "seconds": row["seconds"],
    }


def _mean(values: list[float | None]) -> float:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else float("nan")


def main() -> None:
    truth = json.loads(Path(sys.argv[1]).read_text())
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    errors = 0
    for path in sys.argv[2:]:
        for line in Path(path).read_text().splitlines():
            row = json.loads(line)
            if "error" in row:
                errors += 1
                continue
            hard = row["image"][:2] in ("10", "11", "12") or row["image"] == "page.jpg"
            group = "hard" if hard else "ordinary"
            groups[(group, row.get("mode", "full"), row["model"])].append(score(truth, row))
    print(
        f"{'set':9} {'mode':8} {'model':40} {'n':>3} {'lines':>6} {'nums':>5} "
        f"{'inv':>5} {'lang':>5} {'loop':>4} {'cap':>4} {'tok':>5} {'sec':>5}"
    )
    for (group, mode, model), rows in sorted(groups.items()):
        print(
            f"{group:9} {mode:8} {model:40} {len(rows):>3} "
            f"{_mean([r['lines'] for r in rows]):>6.2f} "
            f"{_mean([r['numbers'] for r in rows]):>5.2f} "
            f"{_mean([r['invented'] for r in rows]):>5.1f} "
            f"{sum(r['wrong_language'] for r in rows):>5} {sum(r['degenerate'] for r in rows):>4} "
            f"{sum(r['capped'] for r in rows):>4} {_mean([r['tokens_out'] for r in rows]):>5.0f} "
            f"{_mean([r['seconds'] for r in rows]):>5.1f}"
        )
    if errors:
        print(f"{errors} calls failed and are not scored")


if __name__ == "__main__":
    main()
