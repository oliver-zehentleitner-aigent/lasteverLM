"""Request dependencies: the service, the caller's identity, the admin gate."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from ..contracts import AuthError, resolve_bearer
from ..repository import UserRecord
from ..service import AccountError, AccountService


def get_service(request: Request) -> AccountService:
    service: AccountService = request.app.state.service
    return service


Service = Annotated[AccountService, Depends(get_service)]


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def optional_user_id(
    service: Service, authorization: Annotated[str | None, Header()] = None
) -> uuid.UUID | None:
    token = _bearer(authorization)
    if not token:
        return None
    try:
        return resolve_bearer(token, service.settings.auth_jwt_secret, service.settings.demo_token)
    except AuthError:
        return None


def current_user_id(
    service: Service, authorization: Annotated[str | None, Header()] = None
) -> uuid.UUID:
    try:
        return resolve_bearer(
            _bearer(authorization), service.settings.auth_jwt_secret, service.settings.demo_token
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CurrentUserId = Annotated[uuid.UUID, Depends(current_user_id)]
OptionalUserId = Annotated[uuid.UUID | None, Depends(optional_user_id)]


async def admin_user(service: Service, user_id: CurrentUserId) -> UserRecord:
    try:
        return await service.require_admin(user_id)
    except AccountError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


AdminUserDep = Annotated[UserRecord, Depends(admin_user)]
