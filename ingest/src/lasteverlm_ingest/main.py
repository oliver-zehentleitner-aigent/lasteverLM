"""Application factory. `uvicorn --factory lasteverlm_ingest.main:create_app`.

Every dependency can be injected, which is how the tests run the whole
API against in-memory fakes; with no arguments, everything is built from
the environment and a missing variable fails the start.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lasteverlm_core import (
    Embedder,
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    PostgresRateLimitStore,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitStore,
    make_client,
)
from pydantic import ValidationError

from lasteverlm_ingest import __version__
from lasteverlm_ingest.api import health, router
from lasteverlm_ingest.chunking import Chunker, TokenWindowChunker
from lasteverlm_ingest.config import ConfigError, Settings
from lasteverlm_ingest.loaders import LoaderRegistry, default_registry
from lasteverlm_ingest.repository import PostgresRepository, Repository
from lasteverlm_ingest.storage import S3Storage, Storage
from lasteverlm_ingest.summarizer import LLMSummarizer, Summarizer
from lasteverlm_ingest.worker import WorkerDeps

log = logging.getLogger(__name__)


def _first_problem(errors: Sequence[Any]) -> str:
    """One line for the `{"error": ...}` shape: `field: what is wrong`."""
    if not errors:
        return "invalid request"
    first = errors[0]
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    message = first.get("msg", "invalid request")
    return f"{where}: {message}" if where else message


def build_worker_deps(
    settings: Settings | None = None,
    *,
    repository: Repository | None = None,
    storage: Storage | None = None,
    embedder: Embedder | None = None,
    summarizer: Summarizer | None = None,
    loaders: LoaderRegistry | None = None,
    chunker: Chunker | None = None,
) -> WorkerDeps:
    """Everything the API and the worker share, built from the environment
    unless injected. The API uses the repository and the storage; the
    worker uses all of it."""
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level.upper())

    repository = repository or PostgresRepository(
        settings.database_url, model_prices=settings.model_prices, service=settings.service_name
    )
    storage = storage or S3Storage(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )
    if embedder is None or summarizer is None:
        client = make_client(settings.inference)
        embedder = embedder or OpenAICompatibleEmbedder(
            client, settings.inference.embedding_model, settings.inference.embedding_dimension
        )
        summarizer = summarizer or LLMSummarizer(
            OpenAICompatibleLLM(client, settings.inference.llm_model, temperature=0.2),
            input_tokens=settings.summary_input_tokens,
            max_output_tokens=settings.summary_max_tokens,
        )
    return WorkerDeps(
        settings=settings,
        repository=repository,
        storage=storage,
        loaders=loaders or default_registry(),
        chunker=chunker or TokenWindowChunker(settings.chunk_tokens, settings.chunk_overlap_tokens),
        embedder=embedder,
        summarizer=summarizer,
    )


def create_app(
    settings: Settings | None = None,
    *,
    rate_limit_store: RateLimitStore | None = None,
    **injected: Any,
) -> FastAPI:
    """`uvicorn --factory lasteverlm_ingest.main:create_app`. Keyword
    arguments are the injectable dependencies of `build_worker_deps`."""
    worker = build_worker_deps(settings, **injected)
    settings = worker.settings

    if rate_limit_store is None:
        connect = getattr(worker.repository, "connection", None)
        if connect is None:
            raise ConfigError("no rate-limit store: the repository offers no connections")
        rate_limit_store = PostgresRateLimitStore(connect)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        close = getattr(app.state.worker.repository, "close", None)
        if close:
            close()

    app = FastAPI(title="lasteverLM ingest", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.worker = worker
    app.include_router(router())
    # The runtime contract probes `/healthz` at the root; the API contract
    # lists it under the prefix. Both answer.
    app.add_api_route("/healthz", health.healthz, methods=["GET"])
    # Outermost, per the family's rate-limit design: 429/403 before the
    # app, one access_log row after it.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(rate_limit_store, settings.rate_limit),
        service=settings.service_name,
        auth=settings.auth,
    )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(
        _: Request, exc: RequestValidationError | ValidationError
    ) -> JSONResponse:
        return JSONResponse({"error": _first_problem(exc.errors())}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse({"error": "internal error"}, status_code=500)

    return app
