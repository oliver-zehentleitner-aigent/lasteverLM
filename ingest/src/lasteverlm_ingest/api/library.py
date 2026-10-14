"""The user's source library: everything uploaded or entered once, with
the notebooks it is in, and its trash. Generated outputs are never part
of it."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from lasteverlm_ingest.api.deps import (
    CreditView,
    original_url,
    preview_url,
    repository,
    seed_if_new,
    snapshot_url,
    worker_deps,
)
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.repository import LibraryEntry, TrashEntry

router = APIRouter()


def _with_preview[E: (LibraryEntry, TrashEntry)](
    request: Request, entry: E, credit: CreditView | None = None
) -> E:
    storage = worker_deps(request).storage
    if credit is not None:
        entry.error = credit.error(entry.status, entry.error)
        entry.status = credit.status(entry.status)
    entry.preview_url = preview_url(
        storage, entry.kind, entry.storage_path, entry.url, entry.transcribed_path
    )
    entry.snapshot_url = snapshot_url(storage, entry.snapshot_path)
    entry.original_url = original_url(
        storage, entry.name, entry.storage_path, entry.transcribed_path
    )
    return entry


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="library source not found")


@router.get("/library", response_model=list[LibraryEntry])
def list_library(
    request: Request, user: CurrentUser, kind: Literal["generated", "all"] | None = None
) -> list[LibraryEntry]:
    """The uploads, newest first; a new user's first look copies the
    starter notebook. `?kind=generated` lists the user's ready outputs instead
    (rag's, with their origin notebook and output id), `?kind=all` both in
    one list, newest first. Every entry carries `notebooks`, the notebooks
    it is linked into."""
    repo = repository(request)
    generated = repo.list_generated(user) if kind in ("generated", "all") else []
    if kind == "generated":
        return list(generated)
    seed_if_new(request, user)
    credit = CreditView(repo, user)
    uploads = [_with_preview(request, e, credit) for e in repo.list_library(user)]
    if kind is None:
        return uploads
    return sorted([*uploads, *generated], key=lambda e: (e.created_at, e.id), reverse=True)


# Before /library/{library_id}, which would take "trash" for an id.
@router.get("/library/trash", response_model=list[TrashEntry])
def list_trash(request: Request, user: CurrentUser) -> list[TrashEntry]:
    return [_with_preview(request, e) for e in repository(request).list_trash(user)]


@router.get("/library/{library_id}", response_model=LibraryEntry)
def get_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> LibraryEntry:
    entry = repository(request).get_library_entry(user, library_id)
    if entry is None:
        raise _not_found()
    return _with_preview(request, entry, CreditView(repository(request), user))


@router.delete("/library/{library_id}", status_code=204)
def delete_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> Response:
    """To the trash: removed from every notebook, chunks and object kept
    until the owner's retention has elapsed."""
    if not repository(request).trash_library_source(user, library_id):
        raise _not_found()
    return Response(status_code=204)


@router.post("/library/{library_id}/restore", status_code=204)
def restore_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> Response:
    """Back into the library, in no notebook; the user adds it again."""
    if not repository(request).restore_library_source(user, library_id):
        raise _not_found()
    return Response(status_code=204)


@router.delete("/library/{library_id}/purge", status_code=204)
def purge_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> Response:
    """Removes a trashed entry now: its chunks and its stored object go."""
    deps = worker_deps(request)
    found, keys = deps.repository.purge_library_source(user, library_id)
    if not found:
        raise _not_found()
    if keys:
        deps.storage.delete(*keys)
    return Response(status_code=204)
