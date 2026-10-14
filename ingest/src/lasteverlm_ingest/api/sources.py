from __future__ import annotations

import contextlib
import re
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from lasteverlm_core import (
    AudioError,
    Source,
    Storage,
    StorageError,
    object_key,
    probe_audio,
)
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from lasteverlm_ingest.api.deps import (
    CreditView,
    original_url,
    owned_notebook,
    owned_source,
    preview_url,
    repository,
    seed_if_new,
    worker_deps,
)
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.dedupe import file_key, url_key
from lasteverlm_ingest.loaders.convert import MEDIA_TYPES, sniff_container
from lasteverlm_ingest.loaders.image import sniff_image_type
from lasteverlm_ingest.loaders.pdf import CAPTURE_MODES, DEFAULT_CAPTURE, Capture
from lasteverlm_ingest.loaders.url import check_url
from lasteverlm_ingest.repository import ChunkText, NewLibrarySource, StoredSource
from lasteverlm_ingest.worker import WorkerDeps

router = APIRouter()

_KIND_BY_SUFFIX = {
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
    ".markdown": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".mp4": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".oga": "audio",
    ".opus": "audio",
    ".flac": "audio",
    ".webm": "audio",
}
_KIND_BY_MEDIA_TYPE = {
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "text",
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "image/gif": "image",
    "audio/mpeg": "audio",
    "audio/mp3": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/mp4": "audio",
    "audio/m4a": "audio",
    "audio/x-m4a": "audio",
    "audio/aac": "audio",
    "audio/ogg": "audio",
    "audio/opus": "audio",
    "audio/flac": "audio",
    "audio/x-flac": "audio",
    "audio/webm": "audio",
    "video/mp4": "audio",
    "video/webm": "audio",
}
AUDIO_FORMATS = "MP3, WAV, M4A/MP4, AAC, Ogg/Opus, FLAC or WebM"
_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
    "url": "text/uri-list",
}
# Most chunks one "As read" page returns.
MAX_CHUNKS_PAGE = 200
# Most library entries one bulk request links.
MAX_BULK = 200
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SourceFromJson(BaseModel):
    """`{"url"}` enters a web page, `{"library_id"}` adds a library source."""

    url: str | None = Field(default=None, min_length=1, max_length=2048)
    library_id: UUID | None = None
    # Accepted for symmetry with uploads; a URL or a library source has no
    # capture choice (a PDF behind a URL is read by its text layer).
    capture: str | None = None


class LinkedSource(Source):
    """A source in a notebook, with the library source it links. `status`
    is `waiting_for_credit` for a queued source whose owner has no credit
    (shown, never stored)."""

    library_id: UUID
    capture: str | None = None
    starter: bool = False
    preview_url: str | None = None
    original_url: str | None = None


def _capture(value: object) -> Capture:
    """The upload's capture mode; absent means `auto` (web sends the
    user's preference explicitly)."""
    if value is None or value == "":
        return DEFAULT_CAPTURE
    if value not in CAPTURE_MODES:
        raise HTTPException(
            status_code=400, detail=f"capture must be one of {', '.join(CAPTURE_MODES)}"
        )
    return value


def _out(source: StoredSource, storage: Storage, credit: CreditView) -> LinkedSource:
    out = LinkedSource.model_validate(source, from_attributes=True)
    out.error = credit.error(source.status, source.error)
    out.status = credit.status(source.status)
    out.preview_url = preview_url(
        storage, source.kind, source.storage_path, source.url, source.transcribed_path
    )
    out.original_url = original_url(
        storage, source.name, source.storage_path, source.transcribed_path
    )
    return out


def detect_kind(filename: str, media_type: str | None) -> str | None:
    kind = _KIND_BY_SUFFIX.get(PurePosixPath(filename).suffix.lower())
    if kind is None and media_type:
        kind = _KIND_BY_MEDIA_TYPE.get(media_type.split(";")[0].strip().lower())
    return kind


def _audio_type(data: bytes) -> str:
    """The stored media type of a recording, from its bytes: a container the
    worker converts (see loaders/convert.py), else WAV or MP3 as core's
    probe reads them; 415 with the reason otherwise."""
    container = sniff_container(data)
    if container is not None:
        # Size and duration are checked on the converted file.
        return MEDIA_TYPES[container]
    try:
        return probe_audio(data).mime
    except AudioError as exc:
        # Not a recording we can read, or an MP3 over core's limits.
        raise HTTPException(status_code=415, detail=f"{exc} (accepted: {AUDIO_FORMATS})") from None


def safe_name(filename: str) -> str:
    name = _UNSAFE.sub("_", PurePosixPath(filename).name).strip("._") or "upload"
    return name[:200]


@router.get("/notebooks/{notebook_id}/sources", response_model=list[LinkedSource])
def list_sources(request: Request, user: CurrentUser, notebook_id: UUID) -> list[LinkedSource]:
    deps = worker_deps(request)
    owned_notebook(deps.repository, user, notebook_id)
    credit = CreditView(deps.repository, user)
    return [_out(s, deps.storage, credit) for s in deps.repository.list_sources(notebook_id)]


@router.post("/notebooks/{notebook_id}/sources", response_model=LinkedSource, status_code=202)
async def create_source(
    request: Request, response: Response, user: CurrentUser, notebook_id: UUID
) -> LinkedSource:
    """202 with a new link; 200 with the existing link when the library
    source (the same bytes, the same URL, or the given library id) is
    already in this notebook. Bytes or a URL the user already has in the
    library are linked, never stored or processed again."""
    deps = worker_deps(request)
    repo = deps.repository
    owned_notebook(repo, user, notebook_id)
    seed_if_new(request, user)

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        # One file and at most the capture field; anything more is a 400
        # before the parser spools it.
        form = await request.form(max_files=1, max_fields=1)
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(status_code=400, detail="multipart field 'file' is required")
        kind = detect_kind(upload.filename, upload.content_type)
        if kind is None or kind not in deps.loaders.kinds:
            raise HTTPException(
                status_code=415,
                detail="unsupported file type; use PDF, text, an image or audio",
            )
        limit = (
            deps.settings.max_audio_upload_bytes
            if kind == "audio"
            else deps.settings.max_upload_bytes
        )
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail="file is too large")
        if not data:
            raise HTTPException(status_code=400, detail="file is empty")
        if kind == "image" and sniff_image_type(data) is None:
            raise HTTPException(status_code=415, detail="not a PNG, JPEG, WebP or GIF image")
        audio_type = _audio_type(data) if kind == "audio" else None
        name = safe_name(upload.filename)
        url = None
        capture: Capture | None = _capture(form.get("capture")) if kind == "pdf" else None
        dedupe_key = file_key(data, capture)
    elif content_type.startswith("application/json"):
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="body is not valid JSON") from None
        body = SourceFromJson.model_validate(payload)
        if (body.url is None) == (body.library_id is None):
            raise HTTPException(status_code=400, detail="send exactly one of 'url', 'library_id'")
        if body.library_id is not None:
            # Uploads in the library and ready outputs (kind generated):
            # their chunks are reused, nothing is processed or billed.
            if not repo.linkable(user, body.library_id):
                raise HTTPException(status_code=404, detail="library source not found")
            return _link(deps, response, user, notebook_id, body.library_id)
        assert body.url is not None
        if "url" not in deps.loaders.kinds:
            raise HTTPException(status_code=501, detail="URL sources are not supported yet")
        try:
            url = check_url(body.url)
            dedupe_key = url_key(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # Only the URL is stored; the worker fetches it (see loaders/url.py).
        kind, data, name, capture = "url", url.encode(), url[:200], None
    else:
        raise HTTPException(
            status_code=415,
            detail="send multipart/form-data with 'file' or JSON with 'url' or 'library_id'",
        )

    existing = repo.find_library_source(user, dedupe_key)
    if existing is not None:
        if existing.deleted_at is not None:
            # The same bytes again bring the trashed entry back.
            repo.restore_library_source(user, existing.id)
        if existing.status == "failed":
            # Uploading again is the user's way to retry.
            repo.retry_library_source(existing.id)
        return _link(deps, response, user, notebook_id, existing.id)

    # Adding is always allowed; processing needs credit. Without it the
    # source is stored and queued, and waits (see the claim query).
    library_id = uuid4()
    key = object_key(user, library_id, "url" if kind == "url" else name)
    # The object first, the row after: a `processing` row is claimable the
    # moment it exists, so a worker must never find one without its object.
    try:
        if kind == "image":
            object_type = sniff_image_type(data)
        elif kind == "audio":
            object_type = audio_type
        else:
            object_type = _CONTENT_TYPE[kind]
        deps.storage.put(key, data, object_type or "application/octet-stream")
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=f"storage unavailable: {exc}") from exc
    created = repo.create_library_source(
        NewLibrarySource(
            id=library_id,
            owner=user,
            name=name,
            kind=kind,
            dedupe_key=dedupe_key,
            url=url,
            size_bytes=None if kind == "url" else len(data),
            storage_path=key,
            capture=capture,
        )
    )
    if created.id != library_id:
        # A concurrent upload of the same bytes inserted its row first:
        # link that one, our object is not needed.
        with contextlib.suppress(StorageError):
            deps.storage.delete(key)
    # Nothing else happens here: the library source is in the queue, a
    # worker claims it (see worker.run_worker).
    return _link(deps, response, user, notebook_id, created.id)


def _link(
    deps: WorkerDeps, response: Response, user: UUID, notebook_id: UUID, library_id: UUID
) -> LinkedSource:
    source, new = deps.repository.link_source(notebook_id, library_id)
    if not new:
        response.status_code = 200
    return _out(source, deps.storage, CreditView(deps.repository, user))


@router.delete("/sources/{source_id}", status_code=204)
def detach_source(request: Request, user: CurrentUser, source_id: UUID) -> Response:
    """Removes the source from this notebook; it stays in the library."""
    repo = repository(request)
    owned_source(repo, user, source_id)
    repo.detach_source(source_id)
    return Response(status_code=204)


class BulkLink(BaseModel):
    """`POST /notebooks/{id}/sources/bulk`: library entries to add at once."""

    library_ids: list[UUID] = Field(min_length=1, max_length=MAX_BULK)


class BulkLinked(BaseModel):
    added: list[UUID]
    already: list[UUID]


@router.post("/notebooks/{notebook_id}/sources/bulk", response_model=BulkLinked)
def link_sources(
    request: Request, user: CurrentUser, notebook_id: UUID, body: BulkLink
) -> BulkLinked:
    """Link several of the caller's library entries into their notebook:
    uploads (whatever their status, not trashed) and ready outputs alike.
    Nothing is processed or billed; the chunks are reused. A link that
    exists is reported in `already`, never doubled. One transaction: if
    any id is not the caller's or cannot be linked, nothing is added (404
    naming the ids)."""
    repo = repository(request)
    owned_notebook(repo, user, notebook_id)
    ids = list(dict.fromkeys(body.library_ids))  # in order, each once
    result = repo.link_many(user, notebook_id, ids)
    if result.missing:
        missing = ", ".join(str(i) for i in result.missing)
        raise HTTPException(status_code=404, detail=f"library sources not found: {missing}")
    return BulkLinked(added=result.added, already=result.already)


class SourceChunks(BaseModel):
    """`GET /sources/{id}/chunks`: what the system read from the source, in
    order. `chunk_count` is the total; `chunks` the requested page."""

    source_id: UUID
    library_id: UUID
    kind: str
    capture: str | None
    chunk_count: int
    offset: int
    chunks: list[ChunkText]


@router.get("/sources/{source_id}/chunks", response_model=SourceChunks)
def source_chunks(
    request: Request,
    user: CurrentUser,
    source_id: UUID,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_CHUNKS_PAGE)] = 50,
) -> SourceChunks:
    """The "As read" view: the source's chunks with their index (a
    citation's `chunk_index`), id (its `chunk_id`), page and text. An audio
    source's chunks carry no position: the platform returns no
    timestamps."""
    repo = repository(request)
    source = owned_source(repo, user, source_id)
    count, chunks = repo.list_chunks(source.library_id, offset, limit)
    return SourceChunks(
        source_id=source.id,
        library_id=source.library_id,
        kind=source.kind,
        capture=source.capture,
        chunk_count=count,
        offset=offset,
        chunks=chunks,
    )
