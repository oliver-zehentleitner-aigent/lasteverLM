"""Application factory. `uvicorn --factory lasteverlm_ingest.main:create_app`.

Every dependency can be injected, which is how the tests run the whole
API against in-memory fakes; with no arguments, everything is built from
the environment and a missing variable fails the start.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lasteverlm_core import (
    Chunker,
    Dependency,
    Embedder,
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    OpenAICompatibleSpeechToText,
    PostgresRateLimitStore,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitStore,
    S3Storage,
    Storage,
    TokenWindowChunker,
    make_client,
)
from lasteverlm_core.health import (
    Check,
    DependencyProbe,
    inference_check,
    postgres_check,
    storage_check,
)
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from lasteverlm_ingest import __version__
from lasteverlm_ingest.api import health, router
from lasteverlm_ingest.config import ConfigError, Settings
from lasteverlm_ingest.loaders import LoaderRegistry, default_registry
from lasteverlm_ingest.loaders.image import VisionReader
from lasteverlm_ingest.repository import PostgresRepository, Repository
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
    storage = storage or S3Storage(settings.s3)
    client = None
    if embedder is None or summarizer is None or loaders is None:
        client = make_client(settings.inference)
    if embedder is None or summarizer is None:
        assert client is not None
        embedder = embedder or OpenAICompatibleEmbedder(
            client, settings.inference.embedding_model, settings.inference.embedding_dimension
        )
        summarizer = summarizer or LLMSummarizer(
            OpenAICompatibleLLM(
                client,
                settings.inference.llm_model,
                temperature=0.2,
                max_tokens=settings.inference.llm_max_tokens,
            ),
            input_tokens=settings.summary_input_tokens,
            max_output_tokens=settings.summary_max_tokens,
        )
    return WorkerDeps(
        settings=settings,
        repository=repository,
        storage=storage,
        loaders=loaders
        or default_registry(
            max_url_bytes=settings.max_upload_bytes,
            vision=VisionReader(
                client, settings.inference.llm_model, max_tokens=settings.image_max_tokens
            ),
            pdf_vision_max_pages=settings.pdf_vision_max_pages,
            # A transcription can run for minutes: its own client, one
            # attempt bounded by STT_TIMEOUT_SECONDS, which stays below the
            # claim timeout so no other worker takes the job over mid-call.
            transcriber=OpenAICompatibleSpeechToText(
                make_client(
                    settings.inference, timeout=settings.stt_timeout_seconds, max_retries=0
                ),
                settings.inference.stt_model,
            ),
        ),
        chunker=chunker or TokenWindowChunker(**settings.chunker_kwargs()),
        embedder=embedder,
        summarizer=summarizer,
    )


def dependency_probe(worker: WorkerDeps) -> DependencyProbe:
    """What `/healthz` reports: the database (a pooled connection with a
    2 s wait), the bucket (a HEAD) and the inference API (`GET /models`).
    Only a test double is left out: the real repository and storage, which
    `build_worker_deps` builds, are always probed, so a missing key in the
    body never hides a dependency production uses."""
    checks: dict[Dependency, Check] = {}
    repository = worker.repository
    if isinstance(repository, PostgresRepository):
        checks["postgres"] = postgres_check(lambda: repository.connection(timeout=2))
    if isinstance(worker.storage, S3Storage):
        checks["storage"] = storage_check(worker.storage)
    checks["inference"] = inference_check(make_client(worker.settings.inference))
    return DependencyProbe(checks)


def create_app(
    settings: Settings | None = None,
    *,
    rate_limit_store: RateLimitStore | None = None,
    probe: DependencyProbe | None = None,
    **injected: Any,
) -> FastAPI:
    """`uvicorn --factory lasteverlm_ingest.main:create_app`. Keyword
    arguments are the injectable dependencies of `build_worker_deps`, and
    the `/healthz` dependency probe."""
    worker = build_worker_deps(settings, **injected)
    settings = worker.settings

    if rate_limit_store is None:
        connect = getattr(worker.repository, "connection", None)
        if connect is None:
            raise ConfigError("no rate-limit store: the repository offers no connections")
        rate_limit_store = PostgresRateLimitStore(connect)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(app.state.worker.repository, "close", None)
        if close:
            close()

    app = FastAPI(title="lasteverLM ingest", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.worker = worker
    app.state.dependency_probe = probe or dependency_probe(worker)
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

    # Starlette's class, so routing errors (404, 405) and the form parser's
    # 400 get the same shape as the app's own.
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers
        )

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
