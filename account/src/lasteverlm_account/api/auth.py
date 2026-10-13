"""Magic-link login: request a link, exchange its token for a session JWT."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from ..models import LoginResponse, RequestLinkBody
from .deps import ClientIp, Service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-link", status_code=202)
async def request_link(
    body: RequestLinkBody, ip: ClientIp, service: Service, background: BackgroundTasks
) -> JSONResponse:
    # 202 for an allowed address, 403 {"code": "not_allowed"} for any other (context/auth.md).
    # The attempt is logged with the client address; the mail goes out after the response.
    pending = await service.request_link(str(body.email), ip)
    background.add_task(service.deliver, pending)
    return JSONResponse(status_code=202, content={"status": "accepted"})


@router.get("/callback", response_model=LoginResponse)
async def callback(
    service: Service, token: str = Query(min_length=1, max_length=512)
) -> LoginResponse:
    jwt_token, user = await service.complete_login(token)
    return LoginResponse(jwt=jwt_token, user=user)
