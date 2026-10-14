"""The signed-in user's own endpoints, plus the visitor log hook the frontend calls."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..models import (
    MyCredit,
    Preferences,
    PreferencesUpdate,
    PublicPrices,
    RedeemBody,
    User,
    VisitBody,
)
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


@router.get("/prices", response_model=PublicPrices)
async def prices(service: Service, response: Response) -> PublicPrices:
    """The public price list, no login: what each action costs today, from the last 30
    days' measured costs through the current rules. End prices only (context/finance.md)."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return await service.public_prices()


@router.get("/me/credit", response_model=MyCredit, response_model_by_alias=True)
async def my_credit(
    service: Service,
    user_id: CurrentUserId,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MyCredit:
    """The caller's own credit: balance, credits and charged actions (one per action, fee
    included, with notebook, output or source), per action and per day. From/to are UTC
    days, inclusive, default the last 30; entries newest first, paged."""
    until = to or service.now().date()
    since = from_ or until - timedelta(days=29)
    if since > until or (until - since).days > 731:
        raise HTTPException(status_code=422, detail="from must not be after to, two years at most")
    return await service.my_credit(user_id, since, until, limit, offset)
