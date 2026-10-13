from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response
from lasteverlm_core import Notebook
from pydantic import BaseModel, Field

from lasteverlm_ingest.api.deps import owned_notebook, repository, worker_deps
from lasteverlm_ingest.auth import CurrentUser


class NotebookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


router = APIRouter()


@router.get("/notebooks", response_model=list[Notebook])
def list_notebooks(request: Request, user: CurrentUser) -> list[Notebook]:
    return repository(request).list_notebooks(user)


@router.post("/notebooks", response_model=Notebook, status_code=201)
def create_notebook(request: Request, user: CurrentUser, body: NotebookCreate) -> Notebook:
    return repository(request).create_notebook(user, body.title.strip())


@router.delete("/notebooks/{notebook_id}", status_code=204)
def delete_notebook(request: Request, user: CurrentUser, notebook_id: UUID) -> Response:
    deps = worker_deps(request)
    owned_notebook(deps.repository, user, notebook_id)
    keys = deps.repository.delete_notebook(user, notebook_id)
    deps.storage.delete(*keys)
    return Response(status_code=204)
