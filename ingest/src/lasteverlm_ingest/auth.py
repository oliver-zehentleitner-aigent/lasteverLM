"""Bearer-token dependency: core decides who the caller is, this maps the
answer onto FastAPI (401 with the contract's error shape)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from lasteverlm_core import AuthError
from lasteverlm_core import current_user as resolve_principal


def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> UUID:
    try:
        return resolve_principal(authorization, request.app.state.settings.auth).user_id
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CurrentUser = Annotated[UUID, Depends(current_user)]
