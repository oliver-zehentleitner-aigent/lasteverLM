"""FastAPI application. Endpoints follow the rag section of docs/architecture.md in the parent."""

import logging
import uuid
from functools import partial
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lasteverlm_core import (
    LLM,
    Answer,
    AuthError,
    ChunkView,
    Embedder,
    Health,
    Message,
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    OpenAICompatibleTextToSpeech,
    Output,
    OutputKind,
    PostgresRateLimitStore,
    ProviderError,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitStore,
    Role,
    S3Storage,
    SharedOutput,
    current_user,
    make_client,
)
from lasteverlm_core.web import admin_only, admin_read

from . import __version__
from .admin import admin_stats, daily_stats
from .config import Settings
from .models import (
    AdminStats,
    AskRequest,
    Conversation,
    ConversationCreate,
    ConversationRename,
    DailyStats,
    OutputCreate,
)
from .options import catalogue
from .outputs import OutputGenerator, registry
from .service import (
    ChunkNotFound,
    ConversationNotFound,
    InsufficientCredit,
    InvalidOptions,
    InvalidSources,
    NotebookNotFound,
    ObjectDeleteFailed,
    OutputNotFound,
    OutputNotReady,
    OutputService,
    RagService,
)
from .store import (
    PgVectorRetriever,
    PostgresStore,
    Retriever,
    Store,
    core_connect,
    make_pool,
)
from .voice_samples import SpeechUnavailable, VoiceSampleRequest, VoiceSamples

PREFIX = "/api/rag"

log = logging.getLogger("lasteverlm_rag")

NotebookId = Annotated[uuid.UUID, Path()]
OutputId = Annotated[uuid.UUID, Path()]
ConversationId = Annotated[uuid.UUID, Path()]
ChunkId = Annotated[uuid.UUID, Path()]
MAX_DAILY_DAYS = 365


def create_app(
    settings: Settings | None = None,
    store: Store | None = None,
    retriever: Retriever | None = None,
    embedder: Embedder | None = None,
    llm: LLM | None = None,
    generators: dict[OutputKind, OutputGenerator] | None = None,
    output_service: OutputService | None = None,
    rate_limit_store: RateLimitStore | None = None,
    voice_samples: VoiceSamples | None = None,
) -> FastAPI:
    """Build the app. Dependencies can be injected for tests; otherwise they come from settings."""
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level)

    if store is None or retriever is None or rate_limit_store is None:
        pool = make_pool(settings.database_url)
        store = store or PostgresStore(pool, settings.model_prices)
        retriever = retriever or PgVectorRetriever(pool)
        rate_limit_store = rate_limit_store or PostgresRateLimitStore(partial(core_connect, pool))
    if embedder is None or llm is None:
        client = make_client(settings.inference)
        embedder = embedder or OpenAICompatibleEmbedder(
            client, settings.inference.embedding_model, settings.inference.embedding_dimension
        )
        llm = llm or OpenAICompatibleLLM(
            client, settings.inference.llm_model, max_tokens=settings.inference.llm_max_tokens
        )
    generators = generators or registry(tts_available=settings.tts_model is not None)

    rag = RagService(
        store,
        retriever,
        embedder,
        llm,
        settings.retrieval_k,
        settings.similarity_floor,
        generated_slots=settings.retrieval_generated_slots,
    )
    objects = S3Storage(settings.s3) if settings.s3 else None
    # outputs are synthesized by the worker; the API presigns and deletes their files
    outputs = output_service or OutputService(
        store,
        retriever,
        embedder,
        llm,
        generators,
        settings.retrieval_k,
        settings.similarity_floor,
        objects=objects,
        default_voice=settings.tts_voice,
    )
    # the one synthesis the API does itself: short, cached voice previews
    samples = voice_samples or VoiceSamples(
        store,
        (
            OpenAICompatibleTextToSpeech(
                make_client(settings.inference), settings.tts_model, voice=settings.tts_voice
            )
            if settings.tts_model
            else None
        ),
        objects,
    )

    app = FastAPI(title="lasteverLM rag", version=__version__, docs_url=None, redoc_url=None)
    _install_error_handlers(app)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(rate_limit_store, settings.rate_limit),
        service="rag",
        auth=settings.auth,
    )

    def user_id(authorization: Annotated[str | None, Header()] = None) -> str:
        """The caller's user id as a string; ids stay strings inside this service
        and are cast to UUID at the store boundary."""
        try:
            return str(current_user(authorization, settings.auth).user_id)
        except AuthError as exc:
            raise HTTPException(401, str(exc)) from exc

    User = Annotated[str, Depends(user_id)]  # noqa: N806

    def principal(authorization: Annotated[str | None, Header()] = None) -> uuid.UUID:
        return uuid.UUID(user_id(authorization))

    def role_lookup(_: Request, uid: uuid.UUID) -> Role:
        assert store is not None
        return store.admin_role(str(uid))

    # rag's admin endpoints only read: viewers and admins pass, 401 from the
    # principal, 403 "admin only" from core for a plain user
    AdminReader = Annotated[uuid.UUID, Depends(admin_read(principal, role_lookup))]  # noqa: N806
    # ... and the one that changes something is for admins only
    AdminWriter = Annotated[  # noqa: N806
        uuid.UUID,
        Depends(admin_only(principal, lambda r, uid: role_lookup(r, uid) == "admin")),
    ]

    health = Health.from_env()  # the build is fixed for the life of the process

    @app.get("/healthz", response_model=Health)
    @app.get(f"{PREFIX}/healthz", response_model=Health)
    def healthz() -> Health:
        return health

    @app.post(f"{PREFIX}/notebooks/{{notebook_id}}/ask", response_model=Answer)
    def ask(notebook_id: NotebookId, body: AskRequest, user: User) -> Answer:
        output_id = body.scope.output_id if body.scope else None
        return rag.ask(
            user,
            str(notebook_id),
            body.question,
            str(body.conversation_id),
            output_id,
            [str(s) for s in body.source_ids or []],
        )

    @app.get(f"{PREFIX}/notebooks/{{notebook_id}}/conversations", response_model=list[Conversation])
    def list_conversations(notebook_id: NotebookId, user: User) -> list[Conversation]:
        return rag.conversations(user, str(notebook_id))

    @app.post(
        f"{PREFIX}/notebooks/{{notebook_id}}/conversations",
        response_model=Conversation,
        status_code=201,
    )
    def create_conversation(
        notebook_id: NotebookId, user: User, body: ConversationCreate | None = None
    ) -> Conversation:
        return rag.create_conversation(user, str(notebook_id), body.title if body else None)

    @app.patch(f"{PREFIX}/conversations/{{conversation_id}}", response_model=Conversation)
    def rename_conversation(
        conversation_id: ConversationId, body: ConversationRename, user: User
    ) -> Conversation:
        """Renaming a chat tab."""
        return rag.rename_conversation(user, str(conversation_id), body.title)

    @app.delete(f"{PREFIX}/conversations/{{conversation_id}}", status_code=204)
    def delete_conversation(conversation_id: ConversationId, user: User) -> Response:
        """Closing a chat tab: the conversation and its messages are gone."""
        rag.delete_conversation(user, str(conversation_id))
        return Response(status_code=204)

    @app.get(f"{PREFIX}/chunks/{{chunk_id}}", response_model=ChunkView)
    def get_chunk(chunk_id: ChunkId, user: User) -> ChunkView:
        """The exact passage behind a citation, for its owner."""
        return rag.chunk(user, str(chunk_id))

    @app.get(f"{PREFIX}/conversations/{{conversation_id}}/messages", response_model=list[Message])
    def messages(conversation_id: ConversationId, user: User) -> list[Message]:
        return rag.messages(user, str(conversation_id))

    @app.post(f"{PREFIX}/notebooks/{{notebook_id}}/outputs", response_model=Output, status_code=202)
    def create_output(notebook_id: NotebookId, body: OutputCreate, user: User) -> Output:
        """Inserts the job; a worker (``lasteverlm_rag.worker``) picks it up."""
        return outputs.create(
            user, str(notebook_id), body.kind, body.options, [str(s) for s in body.source_ids or []]
        )

    @app.post(f"{PREFIX}/outputs/voice-sample")
    def voice_sample(body: VoiceSampleRequest, user: User) -> dict[str, Any]:
        """A short preview of a voice; synthesized once per voice, speed and
        language, then served from storage."""
        try:
            return samples.sample(user, body)
        except ValueError as exc:
            raise InvalidOptions(str(exc)) from exc

    @app.get(f"{PREFIX}/outputs/options")
    def output_options(_: User) -> dict[str, Any]:
        """The options catalogue per kind: languages, voices, speeds."""
        return catalogue(settings.tts_voice)

    @app.get(f"{PREFIX}/notebooks/{{notebook_id}}/outputs", response_model=list[Output])
    def list_outputs(notebook_id: NotebookId, user: User) -> list[Output]:
        return outputs.list(user, str(notebook_id))

    @app.get(f"{PREFIX}/outputs/{{output_id}}", response_model=Output)
    def get_output(output_id: OutputId, user: User) -> Output:
        return outputs.get(user, str(output_id))

    @app.delete(f"{PREFIX}/outputs/{{output_id}}", status_code=204)
    def delete_output(output_id: OutputId, user: User) -> Response:
        outputs.delete(user, str(output_id))
        return Response(status_code=204)

    @app.post(f"{PREFIX}/outputs/{{output_id}}/share")
    def share_output(output_id: OutputId, user: User) -> dict[str, str]:
        return {"share_token": outputs.share(user, str(output_id))}

    @app.delete(f"{PREFIX}/outputs/{{output_id}}/share", status_code=204)
    def unshare_output(output_id: OutputId, user: User) -> Response:
        outputs.unshare(user, str(output_id))
        return Response(status_code=204)

    @app.get(f"{PREFIX}/shared/{{token}}", response_model=SharedOutput)
    def shared_output(token: str) -> SharedOutput:
        return outputs.shared(token)

    @app.get(f"{PREFIX}/admin/stats", response_model=AdminStats)
    def stats(_: AdminReader) -> AdminStats:
        assert store is not None
        return admin_stats(store)

    @app.get(f"{PREFIX}/admin/stats/daily", response_model=DailyStats)
    def stats_daily(
        _: AdminReader, days: Annotated[int, Query(ge=1, le=MAX_DAILY_DAYS)] = 30
    ) -> DailyStats:
        assert store is not None
        return daily_stats(store, days)

    @app.delete(f"{PREFIX}/admin/users/{{target}}", status_code=204)
    def delete_user_data(target: uuid.UUID, _: AdminWriter) -> Response:
        """Account's user deletion, before ingest deletes the notebooks."""
        outputs.delete_user_data(str(target))
        return Response(status_code=204)

    return app


def _install_error_handlers(app: FastAPI) -> None:
    """Every error body is ``{"error": "<message>"}`` as the API contract requires."""

    def error(status: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return error(exc.status_code, str(exc.detail))

    @app.exception_handler(SpeechUnavailable)
    async def speech_unavailable(_: Request, exc: SpeechUnavailable) -> JSONResponse:
        return error(503, "text-to-speech is not available")

    @app.exception_handler(InvalidOptions)
    async def invalid_options(_: Request, exc: InvalidOptions) -> JSONResponse:
        return error(422, f"options: {exc}")

    @app.exception_handler(InvalidSources)
    async def invalid_sources(_: Request, exc: InvalidSources) -> JSONResponse:
        return error(422, f"source_ids: {exc} is not a source of this notebook")

    @app.exception_handler(ChunkNotFound)
    async def chunk_not_found(_: Request, exc: ChunkNotFound) -> JSONResponse:
        return error(404, "chunk not found")

    @app.exception_handler(ConversationNotFound)
    async def conversation_not_found(_: Request, exc: ConversationNotFound) -> JSONResponse:
        return error(404, "conversation not found")

    @app.exception_handler(NotebookNotFound)
    async def notebook_not_found(_: Request, exc: NotebookNotFound) -> JSONResponse:
        return error(404, "notebook not found")

    @app.exception_handler(OutputNotFound)
    async def output_not_found(_: Request, exc: OutputNotFound) -> JSONResponse:
        return error(404, "output not found")

    @app.exception_handler(OutputNotReady)
    async def output_not_ready(_: Request, exc: OutputNotReady) -> JSONResponse:
        return error(409, "output is not ready")

    @app.exception_handler(ObjectDeleteFailed)
    async def object_delete_failed(_: Request, exc: ObjectDeleteFailed) -> JSONResponse:
        log.error("deleting a stored object failed: %s", exc)
        return error(502, f"could not delete stored object {exc.key}")

    @app.exception_handler(ProviderError)
    async def provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        log.warning("provider failure: %s", exc)
        return error(502, "the model did not answer; please try again")

    @app.exception_handler(InsufficientCredit)
    async def credit_exhausted(_: Request, exc: InsufficientCredit) -> JSONResponse:
        return error(402, "credit exhausted")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else "invalid request"
        return error(422, message)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return error(500, "internal error")


def app() -> FastAPI:
    """Factory for ``uvicorn lasteverlm_rag.main:app --factory``."""
    return create_app()
