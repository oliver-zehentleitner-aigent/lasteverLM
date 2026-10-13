"""The user's source library: everything uploaded or entered once, with
the notebooks it is in. Generated outputs are never part of it."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from lasteverlm_ingest.api.deps import repository, worker_deps
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.repository import LibraryEntry

router = APIRouter()


@router.get("/library", response_model=list[LibraryEntry])
def list_library(request: Request, user: CurrentUser) -> list[LibraryEntry]:
    return repository(request).list_library(user)


@router.get("/library/{library_id}", response_model=LibraryEntry)
def get_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> LibraryEntry:
    entry = repository(request).get_library_entry(user, library_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="library source not found")
    return entry


@router.delete("/library/{library_id}", status_code=204)
def delete_library_entry(request: Request, user: CurrentUser, library_id: UUID) -> Response:
    """Removes it from every notebook; its chunks and stored object go."""
    deps = worker_deps(request)
    if deps.repository.get_library_entry(user, library_id) is None:
        raise HTTPException(status_code=404, detail="library source not found")
    key = deps.repository.delete_library_source(user, library_id)
    if key:
        deps.storage.delete(key)
    return Response(status_code=204)
