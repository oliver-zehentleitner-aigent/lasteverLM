from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from lasteverlm_core import Source, StorageError, object_key
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from lasteverlm_ingest.api.deps import owned_notebook, owned_source, repository, worker_deps
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.loaders.image import sniff_image_type
from lasteverlm_ingest.loaders.url import check_url, normalize_url
from lasteverlm_ingest.repository import NewLibrarySource, Repository, StoredSource
from lasteverlm_ingest.worker import CREDIT_EXHAUSTED

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
}
_KIND_BY_MEDIA_TYPE = {
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "text",
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "image/gif": "image",
}
_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
    "url": "text/uri-list",
}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SourceFromJson(BaseModel):
    """`{"url"}` enters a web page, `{"library_id"}` adds a library source."""

    url: str | None = Field(default=None, min_length=1, max_length=2048)
    library_id: UUID | None = None


class LinkedSource(Source):
    """A source in a notebook, with the library source it links."""

    library_id: UUID


def _out(source: StoredSource) -> LinkedSource:
    return LinkedSource.model_validate(source, from_attributes=True)


def detect_kind(filename: str, media_type: str | None) -> str | None:
    kind = _KIND_BY_SUFFIX.get(PurePosixPath(filename).suffix.lower())
    if kind is None and media_type:
        kind = _KIND_BY_MEDIA_TYPE.get(media_type.split(";")[0].strip().lower())
    return kind


def safe_name(filename: str) -> str:
    name = _UNSAFE.sub("_", PurePosixPath(filename).name).strip("._") or "upload"
    return name[:200]


@router.get("/notebooks/{notebook_id}/sources", response_model=list[LinkedSource])
def list_sources(request: Request, user: CurrentUser, notebook_id: UUID) -> list[LinkedSource]:
    repo = repository(request)
    owned_notebook(repo, user, notebook_id)
    return [_out(s) for s in repo.list_sources(notebook_id)]


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

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(status_code=400, detail="multipart field 'file' is required")
        kind = detect_kind(upload.filename, upload.content_type)
        if kind is None or kind not in deps.loaders.kinds:
            raise HTTPException(
                status_code=415, detail="unsupported file type; use PDF, text or an image"
            )
        data = await upload.read(deps.settings.max_upload_bytes + 1)
        if len(data) > deps.settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="file is too large")
        if not data:
            raise HTTPException(status_code=400, detail="file is empty")
        if kind == "image" and sniff_image_type(data) is None:
            raise HTTPException(status_code=415, detail="not a PNG, JPEG, WebP or GIF image")
        name = safe_name(upload.filename)
        url = None
        dedupe_key = "sha256:" + hashlib.sha256(data).hexdigest()
    elif content_type.startswith("application/json"):
        body = SourceFromJson.model_validate(await request.json())
        if (body.url is None) == (body.library_id is None):
            raise HTTPException(status_code=400, detail="send exactly one of 'url', 'library_id'")
        if body.library_id is not None:
            entry = repo.get_library_entry(user, body.library_id)
            if entry is None:
                raise HTTPException(status_code=404, detail="library source not found")
            return _link(repo, response, notebook_id, entry.id)
        assert body.url is not None
        if "url" not in deps.loaders.kinds:
            raise HTTPException(status_code=501, detail="URL sources are not supported yet")
        try:
            url = check_url(body.url)
            dedupe_key = "url:" + normalize_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # Only the URL is stored; the worker fetches it (see loaders/url.py).
        kind, data, name = "url", url.encode(), url[:200]
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
        return _link(repo, response, notebook_id, existing.id)

    # Only a new library source costs anything (its processing).
    if not repo.has_credit(user):
        raise HTTPException(status_code=402, detail=CREDIT_EXHAUSTED)

    library_id = uuid4()
    key = object_key(user, library_id, "url" if kind == "url" else name)
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
        )
    )
    if created.id == library_id:
        try:
            object_type = sniff_image_type(data) if kind == "image" else _CONTENT_TYPE[kind]
            deps.storage.put(key, data, object_type or "application/octet-stream")
        except StorageError as exc:
            repo.set_library_status(library_id, "failed", str(exc)[:500])
    # Nothing else happens here: the library source is in the queue, a
    # worker claims it (see worker.run_worker).
    return _link(repo, response, notebook_id, created.id)


def _link(
    repo: Repository, response: Response, notebook_id: UUID, library_id: UUID
) -> LinkedSource:
    source, new = repo.link_source(notebook_id, library_id)
    if not new:
        response.status_code = 200
    return _out(source)


@router.delete("/sources/{source_id}", status_code=204)
def detach_source(request: Request, user: CurrentUser, source_id: UUID) -> Response:
    """Removes the source from this notebook; it stays in the library."""
    repo = repository(request)
    owned_source(repo, user, source_id)
    repo.detach_source(source_id)
    return Response(status_code=204)
