"""Request dependencies: the service, the caller's identity, the admin gate."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from lasteverlm_core import AuthError, Principal, current_user

from ..repository import UserRecord
from ..service import AccountError, AccountService


def get_service(request: Request) -> AccountService:
    service: AccountService = request.app.state.service
    return service


Service = Annotated[AccountService, Depends(get_service)]


def principal(service: Service, authorization: Annotated[str | None, Header()] = None) -> Principal:
    try:
        return current_user(authorization, service.auth)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def optional_user_id(
    service: Service, authorization: Annotated[str | None, Header()] = None
) -> uuid.UUID | None:
    """The caller's user id when a valid token is present; anonymous otherwise."""
    if authorization is None:
        return None
    try:
        return current_user(authorization, service.auth).user_id
    except AuthError:
        return None


def current_user_id(who: Annotated[Principal, Depends(principal)]) -> uuid.UUID:
    return who.user_id


CurrentUserId = Annotated[uuid.UUID, Depends(current_user_id)]
OptionalUserId = Annotated[uuid.UUID | None, Depends(optional_user_id)]


async def admin_user(service: Service, who: Annotated[Principal, Depends(principal)]) -> UserRecord:
    # The shared demo token never reaches the admin panel, whatever the user row says.
    if who.scheme == "demo":
        raise HTTPException(status_code=403, detail="admin only")
    try:
        return await service.require_admin(who.user_id)
    except AccountError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


AdminUserDep = Annotated[UserRecord, Depends(admin_user)]
