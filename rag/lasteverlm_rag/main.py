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
    ExchangeRateMissingError,
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
from lasteverlm_core.health import (
    DEPENDENCY_TIMEOUT_SECONDS,
    Check,
    DependencyProbe,
    inference_check,
    postgres_check,
    storage_check,
)
from lasteverlm_core.models import Dependency
from lasteverlm_core.web import admin_only, admin_read

from . import __version__
from .admin import admin_stats, daily_stats
from .config import Settings
from .estimate import Models, action_calls, estimate, output_calls
from .judge import judge_models
from .models import (
    AdminStats,
    AskRequest,
    ChartPropose,
    Conversation,
    ConversationCreate,
    ConversationRename,
    DailyStats,
    EstimateRequest,
    FeedbackRequest,
    JudgeRequest,
    NotebookSuggestions,
    OutputCreate,
    OutputRename,
    SharedNotebook,
)
from .options import OutputOptions, catalogue, resolve
from .outputs import OutputGenerator, registry
from .outputs.chart import ChartProposals
from .service import (
    ChunkNotFound,
    ConversationNotFound,
    InsufficientCredit,
    InvalidOptions,
    InvalidSources,
    MessageNotFound,
    NotAnAnswer,
    NotebookNotFound,
    NothingToJudge,
    ObjectDeleteFailed,
    OutputNotFound,
    OutputNotInTrash,
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

# how many down-rated answers the admin overview lists
FEEDBACK_LATEST = 20
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
    dependency_probe: DependencyProbe | None = None,
) -> FastAPI:
    """Build the app. Dependencies can be injected for tests; otherwise they come from settings."""
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    # /healthz reports the state of what this app built itself
    checks: dict[Dependency, Check] = {}

    if store is None or retriever is None or rate_limit_store is None:
        pool = make_pool(settings.database_url)
        checks["postgres"] = postgres_check(
            lambda: pool.connection(timeout=DEPENDENCY_TIMEOUT_SECONDS)
        )
        store = store or PostgresStore(pool, settings.model_prices)
        retriever = retriever or PgVectorRetriever(pool)
        rate_limit_store = rate_limit_store or PostgresRateLimitStore(partial(core_connect, pool))
    if embedder is None or llm is None:
        client = make_client(settings.inference)
        checks["inference"] = inference_check(client)
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
    if objects is not None:
        checks["storage"] = storage_check(objects)
    probe = dependency_probe or (DependencyProbe(checks) if checks else None)
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
        # for judging an existing output or answer on request
        judges=judge_models(make_client(settings.inference), settings.inference.judge_models),
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

    build = Health.from_env()  # the build is fixed for the life of the process

    @app.get("/healthz", response_model=Health)
    @app.get(f"{PREFIX}/healthz", response_model=Health)
    async def healthz() -> Health:
        # cached for 15 s, 2 s per check; a dependency that is down is
        # reported, the probe itself stays "ok"
        if probe is None:
            return build
        return build.model_copy(update={"dependencies": await probe.states()})

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

    @app.post(f"{PREFIX}/notebooks/{{notebook_id}}/charts/propose", response_model=ChartProposals)
    def propose_charts(notebook_id: NotebookId, body: ChartPropose, user: User) -> ChartProposals:
        """Candidate charts; nothing is stored until the user creates a chart output."""
        instructions = " ".join((body.instructions or "").split()) or None
        return outputs.propose_charts(user, str(notebook_id), instructions, body.max)

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
        return catalogue(settings.tts_voice, settings.inference.judge_models)

    models = Models(
        llm=settings.inference.llm_model,
        embedding=settings.inference.embedding_model,
        decision=settings.inference.decision_model,
        tts=settings.tts_model,
        judges={str(k): v for k, v in settings.inference.judge_models.items()},
    )

    @app.post(f"{PREFIX}/estimate")
    def estimate_charge(body: EstimateRequest, _: User) -> dict[str, Any]:
        """The charge range of an output or an action, before it runs."""
        if (body.kind is None) == (body.action is None):
            raise InvalidOptions("estimate: give either kind or action")
        try:
            if body.kind is not None:
                options = body.options
                if body.kind != "chart":
                    resolved = OutputOptions.model_validate(options)
                    options = resolve(body.kind, resolved, settings.tts_voice)
                generator = generators[body.kind]
                action = f"output:{body.kind}"
                low, high = (
                    output_calls(body.kind, options, generator, models, case) for case in (0, 1)
                )
            else:
                action = body.action or ""
                low, high = (action_calls(action, body.options, models, case) for case in (0, 1))
        except ValueError as exc:  # a pydantic ValidationError is one too
            raise InvalidOptions(str(exc)) from exc
        return estimate(settings.model_prices, store.pricing_rules(), action, low, high)

    @app.get(f"{PREFIX}/notebooks/{{notebook_id}}/outputs", response_model=list[Output])
    def list_outputs(notebook_id: NotebookId, user: User) -> list[Output]:
        return outputs.list(user, str(notebook_id))

    @app.delete(f"{PREFIX}/notebooks/{{notebook_id}}/outputs", status_code=204)
    def delete_notebook_outputs(notebook_id: NotebookId, user: User) -> Response:
        outputs.delete_notebook_outputs(user, str(notebook_id))
        return Response(status_code=204)

    @app.get(f"{PREFIX}/library/outputs", response_model=list[Output])
    def library_outputs(
        user: User, kind: OutputKind | None = None, trash: bool = False
    ) -> list[Output]:
        return outputs.library(user, kind, trash)

    @app.get(f"{PREFIX}/outputs/{{output_id}}", response_model=Output)
    def get_output(output_id: OutputId, user: User) -> Output:
        return outputs.get(user, str(output_id))

    @app.delete(f"{PREFIX}/outputs/{{output_id}}", status_code=204)
    def delete_output(output_id: OutputId, user: User) -> Response:
        outputs.delete(user, str(output_id))
        return Response(status_code=204)

    @app.post(f"{PREFIX}/outputs/{{output_id}}/restore", status_code=204)
    def restore_output(output_id: OutputId, user: User) -> Response:
        outputs.restore(user, str(output_id))
        return Response(status_code=204)

    @app.delete(f"{PREFIX}/outputs/{{output_id}}/purge", status_code=204)
    def purge_output(output_id: OutputId, user: User) -> Response:
        outputs.purge(user, str(output_id))
        return Response(status_code=204)

    @app.post(f"{PREFIX}/outputs/{{output_id}}/share")
    def share_output(output_id: OutputId, user: User) -> dict[str, str]:
        return {"share_token": outputs.share(user, str(output_id))}

    @app.delete(f"{PREFIX}/outputs/{{output_id}}/share", status_code=204)
    def unshare_output(output_id: OutputId, user: User) -> Response:
        outputs.unshare(user, str(output_id))
        return Response(status_code=204)

    @app.post(f"{PREFIX}/outputs/{{output_id}}/judge", response_model=Output)
    def judge_output(output_id: OutputId, body: JudgeRequest, user: User) -> Output:
        """Judge a ready output's claims with the level's model; annotate only."""
        return outputs.judge_stored_output(user, str(output_id), body.level)

    @app.post(f"{PREFIX}/messages/{{message_id}}/feedback", response_model=Message)
    def rate_message(message_id: uuid.UUID, body: FeedbackRequest, user: User) -> Message:
        """The owner's thumbs up or down on an answer; a new rating replaces the old."""
        return rag.rate(user, str(message_id), body.rating, body.comment)

    @app.get(f"{PREFIX}/notebooks/{{notebook_id}}/suggestions", response_model=NotebookSuggestions)
    def notebook_suggestions(notebook_id: NotebookId, user: User) -> NotebookSuggestions:
        """Starting questions for a notebook, cached until its uploads change."""
        return rag.notebook_suggestions(user, str(notebook_id))

    @app.post(f"{PREFIX}/messages/{{message_id}}/judge", response_model=Message)
    def judge_message(message_id: uuid.UUID, body: JudgeRequest, user: User) -> Message:
        """Judge a chat answer's paragraphs against its citations; annotate only."""
        return outputs.judge_message(user, str(message_id), body.level)

    @app.patch(f"{PREFIX}/outputs/{{output_id}}", response_model=Output)
    def rename_output(output_id: OutputId, body: OutputRename, user: User) -> Output:
        return outputs.rename(user, str(output_id), body.title)

    @app.get(f"{PREFIX}/shared/notebooks/{{token}}", response_model=SharedNotebook)
    def shared_notebook(token: str) -> SharedNotebook:
        """A notebook its owner shared through ingest; no sign-in."""
        return outputs.shared_notebook(token)

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

    @app.get(f"{PREFIX}/admin/feedback")
    def feedback(
        _: AdminReader, days: Annotated[int, Query(ge=1, le=MAX_DAILY_DAYS)] = 30
    ) -> dict[str, Any]:
        """Ratings per day and the latest down-rated answers with their question."""
        assert store is not None
        return store.feedback_overview(days, FEEDBACK_LATEST)

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

    @app.exception_handler(MessageNotFound)
    async def message_not_found(_: Request, exc: MessageNotFound) -> JSONResponse:
        return error(404, "message not found")

    @app.exception_handler(NotAnAnswer)
    async def not_an_answer(_: Request, exc: NotAnAnswer) -> JSONResponse:
        return error(409, "feedback is for answers only")

    @app.exception_handler(NothingToJudge)
    async def nothing_to_judge(_: Request, exc: NothingToJudge) -> JSONResponse:
        return error(409, "nothing to judge: no cited passages")

    @app.exception_handler(OutputNotInTrash)
    async def output_not_in_trash(_: Request, exc: OutputNotInTrash) -> JSONResponse:
        return error(409, "output is not in the trash")

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

    @app.exception_handler(ExchangeRateMissingError)
    async def no_exchange_rate(_: Request, exc: ExchangeRateMissingError) -> JSONResponse:
        # nothing can be booked or estimated: a configuration gap, loud in the log
        log.error("%s", exc)
        return error(503, "pricing has no exchange rate, ask an admin")

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
