"""FastAPI application. Endpoints follow the rag section of docs/architecture.md in the parent."""

import logging
import uuid
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .contracts import (
    Answer,
    AskRequest,
    AuthError,
    Message,
    Output,
    OutputCreate,
    OutputKind,
    SharedOutput,
    verify_token,
)
from .outputs import OutputGenerator, registry
from .providers import LLM, Embedder, OpenAICompatibleEmbedder, OpenAICompatibleLLM, make_client
from .service import (
    InsufficientCredit,
    NotebookNotFound,
    OutputNotFound,
    OutputNotReady,
    OutputService,
    RagService,
)
from .store import PgVectorRetriever, PostgresStore, Retriever, Store, make_pool

PREFIX = "/api/rag"

log = logging.getLogger("lasteverlm_rag")

NotebookId = Annotated[uuid.UUID, Path()]
OutputId = Annotated[uuid.UUID, Path()]


def create_app(
    settings: Settings | None = None,
    store: Store | None = None,
    retriever: Retriever | None = None,
    embedder: Embedder | None = None,
    llm: LLM | None = None,
    generators: dict[OutputKind, OutputGenerator] | None = None,
    output_service: OutputService | None = None,
) -> FastAPI:
    """Build the app. Dependencies can be injected for tests; otherwise they come from settings."""
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level)

    if store is None or retriever is None:
        pool = make_pool(settings.database_url)
        store = store or PostgresStore(pool, settings.model_prices)
        retriever = retriever or PgVectorRetriever(pool)
    if embedder is None or llm is None:
        client = make_client(settings.inference_base_url, settings.inference_api_key)
        embedder = embedder or OpenAICompatibleEmbedder(
            client, settings.embedding_model, settings.embedding_dimension
        )
        llm = llm or OpenAICompatibleLLM(client, settings.llm_model)
    generators = generators or registry(tts_available=settings.tts_model is not None)

    rag = RagService(
        store, retriever, embedder, llm, settings.retrieval_k, settings.similarity_floor
    )
    outputs = output_service or OutputService(
        store, retriever, embedder, llm, generators, settings.retrieval_k, settings.similarity_floor
    )

    app = FastAPI(title="lasteverLM rag", version=__version__, docs_url=None, redoc_url=None)
    _install_error_handlers(app)

    def current_user(authorization: Annotated[str | None, Header()] = None) -> str:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(401, "missing bearer token")
        try:
            return verify_token(token.strip(), settings.auth_jwt_secret, settings.demo_token)
        except AuthError as exc:
            raise HTTPException(401, str(exc)) from exc

    User = Annotated[str, Depends(current_user)]  # noqa: N806

    @app.get("/healthz")
    @app.get(f"{PREFIX}/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(f"{PREFIX}/notebooks/{{notebook_id}}/ask", response_model=Answer)
    def ask(notebook_id: NotebookId, body: AskRequest, user: User) -> Answer:
        output_id = body.scope.output_id if body.scope else None
        return rag.ask(user, str(notebook_id), body.question, output_id)

    @app.get(f"{PREFIX}/notebooks/{{notebook_id}}/messages", response_model=list[Message])
    def messages(notebook_id: NotebookId, user: User) -> list[Message]:
        return rag.messages(user, str(notebook_id))

    @app.post(f"{PREFIX}/notebooks/{{notebook_id}}/outputs", response_model=Output, status_code=202)
    def create_output(notebook_id: NotebookId, body: OutputCreate, user: User) -> Output:
        """Inserts the job; a worker (``lasteverlm_rag.worker``) picks it up."""
        return outputs.create(user, str(notebook_id), body.kind)

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

    return app


def _install_error_handlers(app: FastAPI) -> None:
    """Every error body is ``{"error": "<message>"}`` as the API contract requires."""

    def error(status: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return error(exc.status_code, str(exc.detail))

    @app.exception_handler(NotebookNotFound)
    async def notebook_not_found(_: Request, exc: NotebookNotFound) -> JSONResponse:
        return error(404, "notebook not found")

    @app.exception_handler(OutputNotFound)
    async def output_not_found(_: Request, exc: OutputNotFound) -> JSONResponse:
        return error(404, "output not found")

    @app.exception_handler(OutputNotReady)
    async def output_not_ready(_: Request, exc: OutputNotReady) -> JSONResponse:
        return error(409, "output is not ready")

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
