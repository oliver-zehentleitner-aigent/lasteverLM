from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request

from lasteverlm_ingest.contracts import Notebook
from lasteverlm_ingest.repository import Repository, StoredSource
from lasteverlm_ingest.worker import WorkerDeps


def worker_deps(request: Request) -> WorkerDeps:
    return request.app.state.worker


def repository(request: Request) -> Repository:
    return request.app.state.worker.repository


def owned_notebook(repo: Repository, user: UUID, notebook_id: UUID) -> Notebook:
    notebook = repo.get_notebook(user, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="notebook not found")
    return notebook


def owned_source(repo: Repository, user: UUID, source_id: UUID) -> StoredSource:
    source = repo.get_source(source_id)
    if source is None or source.owner != user:
        raise HTTPException(status_code=404, detail="source not found")
    return source
