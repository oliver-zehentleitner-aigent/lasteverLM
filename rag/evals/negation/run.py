"""The negation check against its synthetic fixture: hits on the real
contradictions, false positives on the traps, per language and category.

    python -m evals.negation.run            # prints the table
    python -m evals.negation.run --write     # also writes results/<date>.md

No model call and no network: spaCy's small models run locally.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lasteverlm_rag.negation import contradicts

HERE = Path(__file__).parent


def run(name: str = "fixture") -> tuple[list[dict[str, Any]], float]:
    cases = json.loads((HERE / f"{name}.json").read_text())["cases"]
    started = time.monotonic()
    results = [
        {**c, "flagged": contradicts(c["unit"], [c["passage"]], c["language"])}
        for c in cases
    ]
    return results, time.monotonic() - started


def report(results: list[dict[str, Any]], seconds: float) -> str:
    lines = []
    for language in ("en", "de", None):
        rows = [r for r in results if language is None or r["language"] == language]
        real = [r for r in rows if r["expected"] == "contradiction"]
        traps = [r for r in rows if r["expected"] == "consistent"]
        hits = sum(r["flagged"] for r in real)
        false = sum(r["flagged"] for r in traps)
        lines.append(
            f"| {language or 'all'} | {hits}/{len(real)} ({hits / len(real):.0%}) "
            f"| {false}/{len(traps)} ({false / len(traps):.0%}) |"
        )
    out = ["| language | contradictions flagged | traps flagged (false positives) |", "|---|---|---|"]
    out += lines
    by_category: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in results:
        ok = r["flagged"] == (r["expected"] == "contradiction")
        by_category[(r["expected"], r["category"])].append(ok)
    out += ["", "| expected | category | right |", "|---|---|---|"]
    for (expected, category), oks in sorted(by_category.items()):
        out.append(f"| {expected} | {category} | {sum(oks)}/{len(oks)} |")
    wrong = [r for r in results if r["flagged"] != (r["expected"] == "contradiction")]
    out += ["", "Wrong:"]
    out += [
        f"- {r['id']} ({r['category']}, expected {r['expected']}): {r['unit']} / {r['passage']}"
        for r in wrong
    ] or ["- none"]
    out += ["", f"{len(results)} cases in {seconds:.2f} s (models loaded once)."]
    return "\n".join(out)


def main() -> None:
    results, seconds = run()
    text = report(results, seconds)
    print(text)
    if "--write" in sys.argv:
        path = HERE / "results" / f"{datetime.now(UTC):%Y-%m-%d}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"# Negation check, {datetime.now(UTC):%Y-%m-%d}\n\n{text}\n")


if __name__ == "__main__":
    main()
