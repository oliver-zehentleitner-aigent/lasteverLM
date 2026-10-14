"""App factory. ``create_app()`` with no arguments wires the real settings, PostgreSQL,
SMTP and core's rate-limit middleware; tests pass their own repository, mailer and
rate-limit store. Served with ``uvicorn --factory lasteverlm_account.main:create_app``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lasteverlm_core import (
    AsyncPostgresRateLimitStore,
    AuthSettings,
    DependencyProbe,
    Health,
    MemoryRateLimitStore,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitSettings,
    RateLimitStore,
    apostgres_check,
)

from .api import account, admin, auth
from .config import Settings
from .ingress import IngressProbe
from .mail import Mailer, SmtpMailer
from .repository import Repository
from .repository_postgres import PostgresRepository
from .service import AccountError, AccountService
from .services import EstimateClient, ServiceClient
from .system import SystemProbe, kubernetes_api_base

API_PREFIX = "/api/account"

log = logging.getLogger("lasteverlm_account")


def create_app(
    settings: Settings | None = None,
    repository: Repository | None = None,
    mailer: Mailer | None = None,
    rate_limit_store: RateLimitStore | None = None,
    rate_limit_settings: RateLimitSettings | None = None,
    system: SystemProbe | None = None,
    services: ServiceClient | None = None,
    estimates: EstimateClient | None = None,
    ingress: IngressProbe | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    logging.basicConfig(level=resolved.log_level)
    postgres: PostgresRepository | None = None
    repo: Repository
    if repository is None:
        postgres = PostgresRepository.from_url(resolved.database_url)
        repo = postgres
    else:
        repo = repository
    if rate_limit_store is None:
        rate_limit_store = (
            AsyncPostgresRateLimitStore(postgres.connection)
            if postgres is not None
            else MemoryRateLimitStore()
        )

    limits = rate_limit_settings or RateLimitSettings.from_env()

    # What /healthz and /admin/system report as dependency states: core's probe, `select 1`
    # with a 2 s timeout, cached 15 s; a failed check reads "down", the route itself stays up.
    dependencies = DependencyProbe(
        {"postgres": apostgres_check(postgres.connection)} if postgres is not None else {}
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if postgres is not None:
            await postgres.open()
        service = AccountService(
            resolved,
            repo,
            mailer or SmtpMailer(),
            rate_limit=limits,
            system=system or SystemProbe(resolved.system_services, api_base=kubernetes_api_base()),
            services=services,
            estimates=estimates,
            ingress=ingress,
            dependencies=dependencies,
        )
        await service.startup()
        app.state.service = service
        tasks = []
        if service.vultr is not None:
            tasks.append(asyncio.create_task(service.vultr_loop()))
        if resolved.exchange_rate_sync:
            tasks.append(asyncio.create_task(service.exchange_rate_loop()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await repo.close()

    app = FastAPI(title="lasteverLM account", version=resolved.app_version, lifespan=lifespan)

    @app.exception_handler(AccountError)
    async def _account_error(_: Request, exc: AccountError) -> JSONResponse:
        content: dict[str, str] = {"error": exc.message, **exc.details}
        if exc.code:
            content["code"] = exc.code
        return JSONResponse(status_code=exc.status, content=content)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first: dict[str, Any] = next(iter(exc.errors()), {})
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else "invalid request"
        return JSONResponse(status_code=422, content={"error": message})

    # At the root for the Kubernetes probe, under the prefix for the ingress.
    @app.get("/healthz", response_model=Health, tags=["health"])
    @app.get(f"{API_PREFIX}/healthz", response_model=Health, tags=["health"])
    async def healthz() -> Health:
        """Liveness plus the build and the dependency states; "ok" even with postgres down —
        the diagram reads `dependencies`, the probe reads that the process answers."""
        return Health(
            version=resolved.app_version,
            commit=resolved.app_commit,
            dependencies=await dependencies.states(),
        )

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(account.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)

    # Outermost: 429 / 403 before any route runs, one access_log row per request.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(rate_limit_store, limits),
        service="account",
        auth=AuthSettings(jwt_secret=resolved.auth_jwt_secret, demo_token=resolved.demo_token),
        trust_forwarded=resolved.trust_proxy_headers,
    )
    return app
