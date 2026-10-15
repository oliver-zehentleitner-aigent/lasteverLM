"""Whether a request to read sources is funded at its start.

The rule for every action: it starts only if the balance covers its
estimated maximum plus the estimated maximum of the owner's other funded
reads still waiting; once started it runs to the end, even below zero.
Overdraw is then bounded by how far the estimate misses. A funded read
is marked on its row (`funded_request_at`, holding `funded_cents`), and
the claim takes it whatever the balance is by then. An unfunded one
keeps its estimate too and is claimed once the balance, less what funded
reads hold, covers it (see context/accounting.md).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from lasteverlm_core import ExchangeRateMissingError

from lasteverlm_ingest.api.estimate import estimate_read, pricing_for
from lasteverlm_ingest.repository import LibrarySource
from lasteverlm_ingest.worker import WorkerDeps


def funding_for(
    deps: WorkerDeps, owner: UUID, sources: list[LibrarySource], refetch: bool = False
) -> tuple[dict[UUID, Decimal], bool]:
    """Each source's estimated maximum, and whether the owner can fund them
    all now. Without an exchange rate there is no estimate (and nothing is
    read until there is a rate)."""
    if not sources:
        return {}, False
    repo = deps.repository
    try:
        pricing = pricing_for(deps)
        maxima = {
            lib.id: estimate_read(pricing, lib, refetch, deps.settings.pdf_vision_max_pages)[1]
            for lib in sources
        }
    except ExchangeRateMissingError:
        return {}, False
    needed = sum(maxima.values(), Decimal(0))
    balance = repo.balance_cents(owner)
    funded = balance > 0 and balance >= needed + repo.funded_waiting_cents(owner)
    return maxima, funded
