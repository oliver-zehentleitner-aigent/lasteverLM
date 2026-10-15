"""Count the orphaned generated sources: generated library rows no output
points at, older than an hour (``ORPHAN_AGE_S``). Read only: it prints a
count per notebook id, never a name or any content.

    lasteverlm-rag-orphans

The worker deletes them when ORPHAN_SWEEP=true. Needs DATABASE_URL.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter

from .service import ORPHAN_AGE_S
from .store import PostgresStore, Store, make_pool

UNLINKED = "(in no notebook)"


def orphan_counts(store: Store) -> Counter[str]:
    """How many orphaned generated sources each notebook has; one linked
    nowhere counts under ``UNLINKED``."""
    counts: Counter[str] = Counter()
    for row in store.orphaned_generated(ORPHAN_AGE_S):
        for notebook_id in row["notebook_ids"] or [UNLINKED]:
            counts[notebook_id] += 1
    return counts


def main() -> None:
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args()
    pool = make_pool(os.environ["DATABASE_URL"])
    try:
        counts = orphan_counts(PostgresStore(pool, {}))
        for notebook_id, n in sorted(counts.items()):
            print(f"{notebook_id}\t{n}")
        print(f"{sum(counts.values())} orphaned generated sources (read only; nothing changed)")
    finally:
        pool.close()


if __name__ == "__main__":
    main()
