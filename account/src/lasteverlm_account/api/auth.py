"""Magic-link login: request a link, exchange its token for a session JWT."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse

from ..models import LoginResponse, RequestLinkBody
from ..privacy import client_ip
from .deps import Service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-link", status_code=202)
async def request_link(
    body: RequestLinkBody, request: Request, service: Service, background: BackgroundTasks
) -> JSONResponse:
    # 202 for an allowed address, 403 {"code": "not_allowed"} for any other (context/auth.md).
    # The attempt is logged with the client address; the mail goes out after the response.
    ip = client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        trust_proxy_headers=service.settings.trust_proxy_headers,
    )
    pending = await service.request_link(str(body.email), ip)
    background.add_task(service.deliver, pending)
    return JSONResponse(status_code=202, content={"status": "accepted"})


@router.get("/callback", response_model=LoginResponse)
async def callback(service: Service, token: str = Query(min_length=1)) -> LoginResponse:
    jwt_token, user = await service.complete_login(token)
    return LoginResponse(jwt=jwt_token, user=user)
