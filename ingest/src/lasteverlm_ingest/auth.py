"""Bearer-token dependency. One function decides who the caller is."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request

from lasteverlm_ingest.contracts import AuthError, verify_token


def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[7:].strip()
    settings = request.app.state.settings
    try:
        return verify_token(
            token, jwt_secret=settings.auth_jwt_secret, demo_token=settings.demo_token
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CurrentUser = Annotated[UUID, Depends(current_user)]
