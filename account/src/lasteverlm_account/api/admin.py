"""Admin panel backend. Every route requires ``is_admin``; the demo user is never one."""

from __future__ import annotations

from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse

from ..models import (
    AdminAccess,
    AdminBan,
    AdminBlock,
    AdminLogin,
    AdminUser,
    AdminVisit,
    CreateVouchersBody,
    CreateVouchersResponse,
    DomainSettings,
    Smtp,
)
from .deps import AdminUserDep, Service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUser])
async def users(service: Service, _: AdminUserDep) -> list[AdminUser]:
    return await service.admin_users()


@router.get("/logins", response_model=list[AdminLogin])
async def logins(
    service: Service, _: AdminUserDep, limit: int = Query(default=100, ge=1, le=1000)
) -> list[AdminLogin]:
    return await service.admin_logins(limit)


@router.get("/visits", response_model=list[AdminVisit])
async def visits(
    service: Service, _: AdminUserDep, days: int = Query(default=7, ge=1, le=30)
) -> list[AdminVisit]:
    return await service.admin_visits(days)


@router.get("/settings/smtp", response_model=Smtp)
async def get_smtp(service: Service, _: AdminUserDep) -> Smtp:
    """Read-only: the configuration comes from the environment (``SMTP_*``)."""
    return service.smtp_view()


@router.post("/settings/smtp/test", status_code=202)
async def test_smtp(service: Service, admin: AdminUserDep) -> JSONResponse:
    await service.send_test_mail(admin.email)
    return JSONResponse(status_code=202, content={"sent_to": admin.email})


@router.get("/settings/domains", response_model=DomainSettings)
async def get_domains(service: Service, _: AdminUserDep) -> DomainSettings:
    return DomainSettings(allowed_domains=await service.allowed_domains())


@router.put("/settings/domains", response_model=DomainSettings)
async def put_domains(body: DomainSettings, service: Service, _: AdminUserDep) -> DomainSettings:
    return DomainSettings(allowed_domains=await service.set_allowed_domains(body.allowed_domains))


@router.post("/vouchers", response_model=CreateVouchersResponse, status_code=201)
async def create_vouchers(
    body: CreateVouchersBody, service: Service, admin: AdminUserDep
) -> CreateVouchersResponse:
    codes = await service.create_vouchers(admin.id, body.amount_cents, body.count)
    return CreateVouchersResponse(codes=codes)


# --- access control: tables written by core's rate-limit middleware ------------


@router.get("/blocks", response_model=list[AdminBlock])
async def blocks(service: Service, _: AdminUserDep) -> list[AdminBlock]:
    """Addresses currently blocked (blocked_until in the future)."""
    return await service.admin_blocks()


@router.get("/bans", response_model=list[AdminBan])
async def bans(
    service: Service, _: AdminUserDep, include_lifted: bool = Query(default=False)
) -> list[AdminBan]:
    return await service.admin_bans(include_lifted)


@router.delete("/bans/{ip}", status_code=204)
async def lift_ban(
    service: Service, _: AdminUserDep, ip: str = Path(min_length=1, max_length=64)
) -> Response:
    await service.lift_ban(ip)
    return Response(status_code=204)


@router.get("/access", response_model=list[AdminAccess])
async def access(
    service: Service, _: AdminUserDep, limit: int = Query(default=100, ge=1, le=1000)
) -> list[AdminAccess]:
    return await service.admin_access(limit)
