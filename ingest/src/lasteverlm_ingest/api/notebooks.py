from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from lasteverlm_ingest.api.deps import owned_notebook, repository, seed_if_new, worker_deps
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.repository import OwnedNotebook
from lasteverlm_ingest.starter import recreate_starter

# One limit for a notebook title, at creation and on rename.
TITLE_MAX = 200


class NotebookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)


class NotebookRename(BaseModel):
    title: str


class Shared(BaseModel):
    share_token: str


router = APIRouter()


@router.get("/notebooks", response_model=list[OwnedNotebook])
def list_notebooks(request: Request, user: CurrentUser) -> list[OwnedNotebook]:
    """The first thing the web loads after sign-in: a new user's starter
    copy is made first, so it is in this very response."""
    seed_if_new(request, user)
    return repository(request).list_notebooks(user)


@router.post("/notebooks", response_model=OwnedNotebook, status_code=201)
def create_notebook(request: Request, user: CurrentUser, body: NotebookCreate) -> OwnedNotebook:
    return repository(request).create_notebook(user, body.title.strip())


@router.patch("/notebooks/{notebook_id}", response_model=OwnedNotebook)
def rename_notebook(
    request: Request, user: CurrentUser, notebook_id: UUID, body: NotebookRename
) -> OwnedNotebook:
    """The title, trimmed, 1 to 200 characters (as at creation)."""
    title = body.title.strip()
    if not 1 <= len(title) <= TITLE_MAX:
        raise HTTPException(status_code=400, detail=f"title must be 1 to {TITLE_MAX} characters")
    notebook = repository(request).rename_notebook(user, notebook_id, title)
    if notebook is None:
        raise HTTPException(status_code=404, detail="notebook not found")
    return notebook


@router.post("/notebooks/{notebook_id}/share", response_model=Shared)
def share_notebook(request: Request, user: CurrentUser, notebook_id: UUID) -> Shared:
    """A read-only link: rag's public view shows the title, the sources'
    names and kinds and the shared outputs, never the source files. The
    same token on every call until it is revoked."""
    token = repository(request).share_notebook(user, notebook_id)
    if token is None:
        raise HTTPException(status_code=404, detail="notebook not found")
    return Shared(share_token=token)


@router.delete("/notebooks/{notebook_id}/share", status_code=204)
def unshare_notebook(request: Request, user: CurrentUser, notebook_id: UUID) -> Response:
    """Revokes the link; sharing again makes a new one."""
    if not repository(request).unshare_notebook(user, notebook_id):
        raise HTTPException(status_code=404, detail="notebook not found")
    return Response(status_code=204)


@router.delete("/notebooks/{notebook_id}", status_code=204)
def delete_notebook(request: Request, user: CurrentUser, notebook_id: UUID) -> Response:
    """Its sources are detached and stay in the library."""
    repo = repository(request)
    owned_notebook(repo, user, notebook_id)
    repo.delete_notebook(user, notebook_id)
    return Response(status_code=204)


@router.post("/starter/copy", response_model=OwnedNotebook, status_code=201)
def copy_starter_again(
    request: Request, user: CurrentUser, force: bool = False
) -> OwnedNotebook | JSONResponse:
    """A fresh copy of the starter notebook for a user who deleted theirs
    (the help page's "Recreate"): free, at most one an hour. Without
    `force`, a user who still has a starter notebook gets 409
    `starter_exists`, so the web can ask before it makes another."""
    deps = worker_deps(request)
    repo = deps.repository
    if repo.starter_ref() is None:
        raise HTTPException(status_code=404, detail="no_starter")
    if not force and repo.has_starter_notebook(user):
        raise HTTPException(status_code=409, detail="starter_exists")
    result = recreate_starter(repo, deps.storage, user)
    if result.refused == "too_soon":
        return JSONResponse(
            {"error": "starter_copy_too_soon", "retry_after": result.retry_after},
            status_code=429,
            headers={"Retry-After": str(result.retry_after)},
        )
    if result.refused == "no_starter":
        raise HTTPException(status_code=404, detail="no_starter")
    if result.refused == "storage" or result.notebook_id is None:
        raise HTTPException(status_code=503, detail="storage unavailable, try again")
    notebook = repo.get_notebook(user, result.notebook_id)
    assert notebook is not None
    return notebook
