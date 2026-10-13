"""The admin overview: counts across all users, read only."""

from __future__ import annotations

from typing import get_args

from lasteverlm_core import OutputKind, OutputStatus

from .models import AdminStats
from .store import Store
from .worker import STALE_CLAIM_S


def admin_stats(store: Store) -> AdminStats:
    """Notebooks, messages (total, last 24 h), outputs by kind and by status,
    jobs and shared outputs. Jobs: ``pending`` is a waiting row or a processing
    row without a live claim, ``running`` a processing row claimed less than
    ten minutes ago (the worker's stale-claim limit, after which another worker
    takes it over), ``failed`` a failed row."""
    raw = store.admin_stats(STALE_CLAIM_S)
    by_kind = dict.fromkeys(get_args(OutputKind), 0)
    by_status = dict.fromkeys(get_args(OutputStatus), 0)
    for kind, status, n in raw["outputs"]:
        by_kind[kind] = by_kind.get(kind, 0) + n
        by_status[status] = by_status.get(status, 0) + n
    return AdminStats.model_validate(
        {
            "notebooks": raw["notebooks"],
            "messages": raw["messages"],
            "outputs": {"by_kind": by_kind, "by_status": by_status},
            "jobs": raw["jobs"],
            "shared": raw["shared"],
        }
    )
