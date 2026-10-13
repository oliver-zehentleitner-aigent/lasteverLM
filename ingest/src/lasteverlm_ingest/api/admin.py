from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from lasteverlm_ingest.api.deps import worker_deps
from lasteverlm_ingest.auth import AdminUser
from lasteverlm_ingest.repository import AdminStats, DailyStats

router = APIRouter()


class Daily(BaseModel):
    days: list[DailyStats]


@router.get("/admin/stats", response_model=AdminStats)
def admin_stats(request: Request, _: AdminUser) -> AdminStats:
    deps = worker_deps(request)
    return deps.repository.admin_stats(deps.settings.claim_timeout_seconds)


@router.get("/admin/stats/daily", response_model=Daily)
def admin_daily(
    request: Request, _: AdminUser, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> Daily:
    """Library sources created per UTC day, oldest first, every day present."""
    return Daily(days=worker_deps(request).repository.admin_daily(days))
