"""Bearer-token dependencies: core decides who the caller is, this maps the
answer onto FastAPI (401 with the contract's error shape; 403 on the admin
endpoints for anyone who is neither viewer nor admin)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from lasteverlm_core import AuthError, Role
from lasteverlm_core import current_user as resolve_principal
from lasteverlm_core.web import admin_only, admin_read


def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> UUID:
    try:
        return resolve_principal(authorization, request.app.state.settings.auth).user_id
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CurrentUser = Annotated[UUID, Depends(current_user)]


def _role(request: Request, user_id: UUID) -> Role:
    role: Role = request.app.state.worker.repository.admin_role(user_id)
    return role


def _is_admin(request: Request, user_id: UUID) -> bool:
    return _role(request, user_id) == "admin"


# Admin endpoints that only read: viewers and admins (core's `admin_read`).
AdminReader = Annotated[UUID, Depends(admin_read(current_user, _role))]
# Admin endpoints that change something: admins only (core's `admin_only`).
AdminUser = Annotated[UUID, Depends(admin_only(current_user, _is_admin))]
