from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from lasteverlm_core import StorageError
from pydantic import BaseModel

from lasteverlm_ingest.api.deps import worker_deps
from lasteverlm_ingest.auth import AdminReader, AdminUser
from lasteverlm_ingest.repository import AdminStats, DailyStats

log = logging.getLogger(__name__)
router = APIRouter()


class Daily(BaseModel):
    days: list[DailyStats]


@router.get("/admin/stats", response_model=AdminStats)
def admin_stats(request: Request, _: AdminReader) -> AdminStats:
    deps = worker_deps(request)
    return deps.repository.admin_stats(deps.settings.claim_timeout_seconds)


@router.get("/admin/stats/daily", response_model=Daily)
def admin_daily(
    request: Request, _: AdminReader, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> Daily:
    """Library sources created per UTC day, oldest first, every day present."""
    return Daily(days=worker_deps(request).repository.admin_daily(days))


@router.delete("/admin/users/{user_id}", status_code=204)
def delete_user(request: Request, admin: AdminUser, user_id: UUID) -> Response:
    """Everything the user owns in ingest: the stored objects of their
    library (trash included), then its rows, their notebooks with their
    links (rag's rows cascade) and their seed mark. Objects go first, so
    a failure leaves rows a retry finds again; a user with nothing left
    is a 204 as well. Account calls this after rag's purge and before
    deleting the user."""
    deps = worker_deps(request)
    keys = deps.repository.user_object_keys(user_id)
    if keys:
        try:
            deps.storage.delete(*keys)
        except StorageError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"storage: {len(keys)} object(s) of user {user_id} not deleted "
                f"(first {keys[0]}): {exc}",
            ) from exc
    deps.repository.delete_user_data(user_id)
    log.info("admin %s deleted user %s from ingest: %d object(s)", admin, user_id, len(keys))
    return Response(status_code=204)
