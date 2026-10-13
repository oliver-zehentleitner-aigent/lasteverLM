from __future__ import annotations

from fastapi import APIRouter, Request

from lasteverlm_ingest.api.deps import worker_deps
from lasteverlm_ingest.auth import AdminUser
from lasteverlm_ingest.repository import AdminStats

router = APIRouter()


@router.get("/admin/stats", response_model=AdminStats)
def admin_stats(request: Request, _: AdminUser) -> AdminStats:
    deps = worker_deps(request)
    return deps.repository.admin_stats(deps.settings.claim_timeout_seconds)
