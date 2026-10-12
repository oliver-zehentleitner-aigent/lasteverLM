"""The signed-in user's own endpoints, plus the visitor log hook the frontend calls."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..models import RedeemBody, User, VisitBody
from ..privacy import client_ip
from .deps import CurrentUserId, OptionalUserId, Service

router = APIRouter(tags=["account"])


@router.get("/me", response_model=User)
async def me(service: Service, user_id: CurrentUserId) -> User:
    return await service.user_view(user_id)


@router.post("/vouchers/redeem", response_model=User)
async def redeem(body: RedeemBody, service: Service, user_id: CurrentUserId) -> User:
    return await service.redeem(user_id, body.code)


@router.post("/visits", status_code=204)
async def visit(
    body: VisitBody, request: Request, service: Service, user_id: OptionalUserId
) -> Response:
    ip = client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        trust_proxy_headers=service.settings.trust_proxy_headers,
    )
    await service.record_visit(body.path, user_id, ip, request.headers.get("user-agent"))
    return Response(status_code=204)
