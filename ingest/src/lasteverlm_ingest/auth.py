"""Bearer-token dependencies: core decides who the caller is, this maps the
answer onto FastAPI (401 with the contract's error shape; 403 for a
non-admin on admin endpoints)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from lasteverlm_core import AuthError
from lasteverlm_core import current_user as resolve_principal
from lasteverlm_core.web import admin_only


def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> UUID:
    try:
        return resolve_principal(authorization, request.app.state.settings.auth).user_id
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CurrentUser = Annotated[UUID, Depends(current_user)]


def _is_admin(request: Request, user_id: UUID) -> bool:
    return bool(request.app.state.worker.repository.is_admin(user_id))


AdminUser = Annotated[UUID, Depends(admin_only(current_user, _is_admin))]
