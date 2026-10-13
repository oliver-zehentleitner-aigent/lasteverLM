"""The signed-in user's own endpoints, plus the visitor log hook the frontend calls."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..models import Preferences, PreferencesUpdate, RedeemBody, User, VisitBody
from .deps import ClientIp, CurrentUserId, OptionalUserId, Service

router = APIRouter(tags=["account"])


@router.get("/me", response_model=User)
async def me(service: Service, user_id: CurrentUserId) -> User:
    return await service.user_view(user_id)


@router.get("/me/preferences", response_model=Preferences)
async def preferences(service: Service, user_id: CurrentUserId) -> Preferences:
    return await service.preferences(user_id)


@router.put("/me/preferences", response_model=User)
async def put_preferences(
    body: PreferencesUpdate, service: Service, user_id: CurrentUserId
) -> User:
    """Partial: keys present are applied (null clears), absent keys are kept. Returns the user."""
    return await service.update_preferences(user_id, body)


@router.post("/vouchers/redeem", response_model=User)
async def redeem(body: RedeemBody, service: Service, user_id: CurrentUserId) -> User:
    return await service.redeem(user_id, body.code)


@router.post("/visits", status_code=204)
async def visit(
    body: VisitBody, request: Request, ip: ClientIp, service: Service, user_id: OptionalUserId
) -> Response:
    await service.record_visit(body.path, user_id, ip, request.headers.get("user-agent"))
    return Response(status_code=204)
