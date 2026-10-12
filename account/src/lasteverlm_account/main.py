"""App factory. ``create_app()`` with no arguments wires the real settings, PostgreSQL
and SMTP at startup; tests pass their own repository and mailer."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import account, admin, auth
from .config import Settings
from .mail import Mailer, SmtpMailer
from .models import Health
from .repository import Repository
from .repository_postgres import PostgresRepository
from .service import AccountError, AccountService

API_PREFIX = "/api/account"

log = logging.getLogger("lasteverlm_account")


def create_app(
    settings: Settings | None = None,
    repository: Repository | None = None,
    mailer: Mailer | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or Settings.from_env()
        logging.basicConfig(level=resolved.log_level)
        repo = repository
        if repo is None:
            pg = PostgresRepository.from_url(resolved.database_url)
            await pg.open()
            repo = pg
        service = AccountService(resolved, repo, mailer or SmtpMailer())
        await service.startup()
        app.state.service = service
        try:
            yield
        finally:
            await repo.close()

    app = FastAPI(title="lasteverLM account", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(AccountError)
    async def _account_error(_: Request, exc: AccountError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": exc.message})

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
    async def healthz(request: Request) -> Health:
        await request.app.state.service.repo.ping()
        return Health()

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(account.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    return app


app = create_app()
