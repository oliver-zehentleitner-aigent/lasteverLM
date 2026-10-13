from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request
from lasteverlm_core import Notebook, Storage

from lasteverlm_ingest.repository import Repository, StoredSource
from lasteverlm_ingest.seeds import ensure_seeded
from lasteverlm_ingest.worker import WorkerDeps


def worker_deps(request: Request) -> WorkerDeps:
    deps: WorkerDeps = request.app.state.worker
    return deps


def repository(request: Request) -> Repository:
    return worker_deps(request).repository


def seed_if_new(request: Request, user: UUID) -> None:
    """The demo library on the owner's first library access or upload."""
    deps = worker_deps(request)
    if deps.settings.seed_demo_library:
        ensure_seeded(deps.repository, deps.storage, user)


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


def preview_url(storage: Storage, kind: str, storage_path: str | None) -> str | None:
    """For an image, a presigned GET of the stored original (valid one hour),
    so the frontend shows it in an `<img>` without a bearer header; None for
    every other kind."""
    if kind != "image" or not storage_path:
        return None
    return storage.presigned_get(storage_path)
