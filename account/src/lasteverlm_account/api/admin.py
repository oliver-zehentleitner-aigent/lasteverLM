"""Admin panel backend. Every route requires ``is_admin``; the demo user is never one."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse

from ..models import (
    AddressAdd,
    AdminAccess,
    AdminBan,
    AdminBlock,
    AdminLogin,
    AdminLoginAttempt,
    AdminStats,
    AdminUserView,
    AdminVisit,
    AdminVoucher,
    Allowlist,
    CreateVouchersBody,
    CreateVouchersResponse,
    DailyStats,
    DomainAdd,
    RateLimitRulesUpdate,
    RateLimitRulesView,
    Smtp,
    UsageStats,
)
from .deps import AdminUserDep, Service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserView])
async def users(service: Service, _: AdminUserDep) -> list[AdminUserView]:
    return await service.admin_users()


@router.get("/stats", response_model=AdminStats)
async def stats(service: Service, _: AdminUserDep) -> AdminStats:
    """One overview: users, logins and usage cost of the last 24 h, vouchers, blocks, bans."""
    return await service.admin_stats()


@router.get("/stats/daily", response_model=DailyStats)
async def stats_daily(
    service: Service, _: AdminUserDep, days: int = Query(default=30, ge=1, le=365)
) -> DailyStats:
    """Per UTC day: logins, visits, usage cost, credits granted; every day, oldest first."""
    return await service.admin_daily_stats(days)


@router.get("/stats/usage", response_model=UsageStats)
async def stats_usage(service: Service, _: AdminUserDep) -> UsageStats:
    """Usage by model and kind, and the ten users with the highest usage."""
    return await service.admin_usage_stats()


@router.get("/logins", response_model=list[AdminLogin])
async def logins(
    service: Service, _: AdminUserDep, limit: int = Query(default=100, ge=1, le=1000)
) -> list[AdminLogin]:
    return await service.admin_logins(limit)


@router.get("/login-attempts", response_model=list[AdminLoginAttempt])
async def login_attempts(
    service: Service, _: AdminUserDep, limit: int = Query(default=100, ge=1, le=1000)
) -> list[AdminLoginAttempt]:
    """Requests for a sign-in link, newest first, allowed and refused, with the client IP."""
    return await service.admin_login_attempts(limit)


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


@router.get("/settings/ratelimit", response_model=RateLimitRulesView)
async def get_ratelimit(service: Service, _: AdminUserDep) -> RateLimitRulesView:
    """The rule in force; the last two fields are environment-only."""
    return await service.ratelimit_view()


@router.put("/settings/ratelimit", response_model=RateLimitRulesView)
async def put_ratelimit(
    body: RateLimitRulesUpdate, service: Service, _: AdminUserDep
) -> RateLimitRulesView:
    """Override the four runtime fields for every service; core's bounds apply (422)."""
    return await service.update_ratelimit(body)


@router.delete("/settings/ratelimit", status_code=204)
async def reset_ratelimit(service: Service, _: AdminUserDep) -> Response:
    """Drop the override, back to the environment defaults."""
    await service.reset_ratelimit()
    return Response(status_code=204)


# The allowlist: who may sign in besides ADMIN_EMAILS. One GET for both lists, one
# POST/DELETE per entry (0.3.0; the whole-list PUT is gone).
@router.get("/settings/allowlist", response_model=Allowlist)
@router.get("/settings/domains", response_model=Allowlist)
@router.get("/settings/addresses", response_model=Allowlist)
async def allowlist(service: Service, _: AdminUserDep) -> Allowlist:
    return await service.allowlist()


@router.post("/settings/domains", response_model=Allowlist, status_code=201)
async def add_domain(body: DomainAdd, service: Service, _: AdminUserDep) -> Allowlist:
    return await service.add_allow_entry("domain", body.domain)


@router.delete("/settings/domains/{domain}", status_code=204)
async def remove_domain(domain: str, service: Service, _: AdminUserDep) -> Response:
    await service.remove_allow_entry("domain", domain)
    return Response(status_code=204)


@router.post("/settings/addresses", response_model=Allowlist, status_code=201)
async def add_address(body: AddressAdd, service: Service, _: AdminUserDep) -> Allowlist:
    return await service.add_allow_entry("address", body.address)


@router.delete("/settings/addresses/{address}", status_code=204)
async def remove_address(address: str, service: Service, _: AdminUserDep) -> Response:
    await service.remove_allow_entry("address", address)
    return Response(status_code=204)


@router.get("/vouchers", response_model=list[AdminVoucher])
async def vouchers(
    service: Service, _: AdminUserDep, limit: int = Query(default=100, ge=1, le=1000)
) -> list[AdminVoucher]:
    """Newest first. The code is never listed: only its hash is stored."""
    return await service.admin_vouchers(limit)


@router.post("/vouchers", response_model=CreateVouchersResponse, status_code=201)
async def create_vouchers(
    body: CreateVouchersBody, service: Service, admin: AdminUserDep
) -> CreateVouchersResponse:
    codes = await service.create_vouchers(admin.id, body.amount_cents, body.count)
    return CreateVouchersResponse(codes=codes)


@router.delete("/vouchers/{voucher_id}", status_code=204)
async def delete_voucher(voucher_id: uuid.UUID, service: Service, _: AdminUserDep) -> Response:
    """Remove an open voucher; a redeemed one stays (409), it backs a ledger row."""
    await service.delete_voucher(voucher_id)
    return Response(status_code=204)


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
