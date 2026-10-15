"""Re-split stored reports into their checkable units: reports whose
headings were followed by their paragraph without a blank line had those
paragraphs dropped from ``content.units``, so they were never checked. The
units are made again from the stored markdown and get the word check
against the output's stored passages; no model call. A dry run by default;
it lists the outputs it would change, with their unit counts.

    lasteverlm-rag-repair-reports                # dry run, every ready report
    lasteverlm-rag-repair-reports --output ID    # only these (repeatable)
    lasteverlm-rag-repair-reports --apply        # write the rows

Idempotent: a report whose units already match its markdown is left alone.
A unit whose text is unchanged keeps its judge verdict. Needs DATABASE_URL.
Never run it against production without the maintainer's go.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .outputs.report import Report, ReportGenerator
from .provenance import check_against
from .store import PostgresStore, Store, make_pool


@dataclass(frozen=True)
class Resplit:
    output_id: str
    units_before: int
    units_after: int
    applied: bool


def repair_reports(
    store: Store,
    apply: bool,
    output_ids: list[str] | None = None,
    say: Callable[[str], None] = print,
) -> list[Resplit]:
    """Every ready report (or ``output_ids``) whose stored units differ from
    its markdown's; with ``apply``, its units and check written again."""
    generator = ReportGenerator()
    done = []
    for row in store.report_outputs(output_ids):
        content: dict[str, Any] = dict(row.content or {})
        markdown = content.get("markdown")
        if not isinstance(markdown, str):
            continue
        before = content.get("units") or []
        output = generator.to_output(Report(title=row.title, markdown=markdown))
        if [u.text for u in output.units] == [u.get("text") for u in before]:
            continue
        passages = (row.provenance or {}).get("passages") or []
        check = check_against(output.units, {p["n"]: p["quote"] for p in passages})
        judged = {u.get("text"): u["judge"] for u in before if u.get("judge")}
        for unit in output.units:
            if unit.text in judged:
                unit.target["judge"] = judged[unit.text]
        fix = Resplit(row.id, len(before), len(output.units), apply)
        say(
            f"{row.id}: {'re-split' if apply else 'would re-split'}: "
            f"{fix.units_before} → {fix.units_after} units"
        )
        if apply:
            provenance = {**(row.provenance or {}), "check": check}
            store.update_output(
                row.id,
                content={**content, "units": [u.target for u in output.units]},
                provenance=provenance,
            )
        done.append(fix)
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write; without it, a dry run")
    parser.add_argument("--output", action="append", help="an output id (repeatable)")
    args = parser.parse_args()
    pool = make_pool(os.environ["DATABASE_URL"])
    try:
        found = repair_reports(PostgresStore(pool, {}), args.apply, args.output)
        verb = "re-split" if args.apply else "would be re-split (dry run; --apply to write)"
        print(f"{len(found)} reports {verb}")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
