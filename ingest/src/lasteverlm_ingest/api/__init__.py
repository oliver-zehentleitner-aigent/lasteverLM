"""HTTP routers. Thin: validation and status codes here, logic elsewhere."""

from __future__ import annotations

from fastapi import APIRouter

from lasteverlm_ingest.api import admin, estimate, health, library, notebooks, sources

PREFIX = "/api/ingest"


def router() -> APIRouter:
    api = APIRouter(prefix=PREFIX)
    api.include_router(health.router)
    api.include_router(notebooks.router)
    api.include_router(sources.router)
    api.include_router(library.router)
    api.include_router(admin.router)
    api.include_router(estimate.router)
    return api
