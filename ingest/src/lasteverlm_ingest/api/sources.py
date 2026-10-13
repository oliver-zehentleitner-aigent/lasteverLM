from __future__ import annotations

import re
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from lasteverlm_core import Source
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from lasteverlm_ingest.api.deps import owned_notebook, owned_source, repository, worker_deps
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.loaders.url import check_url
from lasteverlm_ingest.storage import StorageError, object_key
from lasteverlm_ingest.worker import CREDIT_EXHAUSTED

router = APIRouter()

_KIND_BY_SUFFIX = {".pdf": "pdf", ".txt": "text", ".md": "text", ".markdown": "text"}
_KIND_BY_MEDIA_TYPE = {"application/pdf": "pdf", "text/plain": "text", "text/markdown": "text"}
_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
    "url": "text/uri-list",
}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SourceFromUrl(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


def detect_kind(filename: str, media_type: str | None) -> str | None:
    kind = _KIND_BY_SUFFIX.get(PurePosixPath(filename).suffix.lower())
    if kind is None and media_type:
        kind = _KIND_BY_MEDIA_TYPE.get(media_type.split(";")[0].strip().lower())
    return kind


def safe_name(filename: str) -> str:
    name = _UNSAFE.sub("_", PurePosixPath(filename).name).strip("._") or "upload"
    return name[:200]


@router.get("/notebooks/{notebook_id}/sources", response_model=list[Source])
def list_sources(request: Request, user: CurrentUser, notebook_id: UUID) -> list[Source]:
    repo = repository(request)
    owned_notebook(repo, user, notebook_id)
    return [Source.model_validate(s, from_attributes=True) for s in repo.list_sources(notebook_id)]


@router.post("/notebooks/{notebook_id}/sources", response_model=Source, status_code=202)
async def create_source(request: Request, user: CurrentUser, notebook_id: UUID) -> Source:
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
            raise HTTPException(status_code=415, detail="unsupported file type; use PDF or text")
        data = await upload.read(deps.settings.max_upload_bytes + 1)
        if len(data) > deps.settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="file is too large")
        if not data:
            raise HTTPException(status_code=400, detail="file is empty")
        name = safe_name(upload.filename)
    elif content_type.startswith("application/json"):
        body = SourceFromUrl.model_validate(await request.json())
        if "url" not in deps.loaders.kinds:
            raise HTTPException(status_code=501, detail="URL sources are not supported yet")
        try:
            url = check_url(body.url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # Only the URL is stored; the worker fetches it (see loaders/url.py).
        kind, data, name = "url", url.encode(), url[:200]
    else:
        raise HTTPException(
            status_code=415, detail="send multipart/form-data with 'file' or JSON with 'url'"
        )

    if repo.balance_cents(user) <= 0:
        raise HTTPException(status_code=402, detail=CREDIT_EXHAUSTED)

    source_id = uuid4()
    key = object_key(notebook_id, source_id, "url" if kind == "url" else name)
    source = repo.create_source(notebook_id, source_id, name, kind, key)
    try:
        deps.storage.put(key, data, _CONTENT_TYPE[kind])
    except StorageError as exc:
        repo.set_source_status(source_id, "failed", str(exc)[:500])
        refreshed = repo.get_source(source_id)
        return Source.model_validate(refreshed or source, from_attributes=True)
    # Nothing else happens here: the row is now in the queue, a worker
    # claims it (see worker.run_worker).
    return Source.model_validate(source, from_attributes=True)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(request: Request, user: CurrentUser, source_id: UUID) -> Response:
    deps = worker_deps(request)
    source = owned_source(deps.repository, user, source_id)
    deps.repository.delete_source(source_id)
    if source.storage_path:
        deps.storage.delete([source.storage_path])
    return Response(status_code=204)
