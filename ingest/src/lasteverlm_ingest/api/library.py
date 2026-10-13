"""The user's source library: everything uploaded or entered once, with
the notebooks it is in, and its trash. Generated outputs are never part
of it."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from lasteverlm_ingest.api.deps import preview_url, repository, seed_if_new, worker_deps
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.repository import LibraryEntry, TrashEntry

router = APIRouter()


def _with_preview[E: (LibraryEntry, TrashEntry)](request: Request, entry: E) -> E:
    entry.preview_url = preview_url(
        worker_deps(request).storage, entry.kind, entry.storage_path, entry.url
    )
    return entry


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="library source not found")


@router.get("/library", response_model=list[LibraryEntry])
def list_library(request: Request, user: CurrentUser) -> list[LibraryEntry]:
    """A new user's first look at the library seeds the demo sources."""
    seed_if_new(request, user)
    return [_with_preview(request, e) for e in repository(request).list_library(user)]


# Before /library/{library_id}, which would take "trash" for an id.
@router.get("/library/trash", response_model=list[TrashEntry])
def list_trash(request: Request, user: CurrentUser) -> list[TrashEntry]:
    return [_with_preview(request, e) for e in repository(request).list_trash(user)]


@router.get("/library/{library_id}", response_model=LibraryEntry)
def get_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> LibraryEntry:
    entry = repository(request).get_library_entry(user, library_id)
    if entry is None:
        raise _not_found()
    return _with_preview(request, entry)


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
    found, key = deps.repository.purge_library_source(user, library_id)
    if not found:
        raise _not_found()
    if key:
        deps.storage.delete(key)
    return Response(status_code=204)
