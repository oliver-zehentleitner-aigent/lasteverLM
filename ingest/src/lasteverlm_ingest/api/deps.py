from __future__ import annotations

from typing import overload
from uuid import UUID

from fastapi import HTTPException, Request
from lasteverlm_core import Notebook, SourceStatus, Storage

from lasteverlm_ingest.repository import Repository, StoredSource
from lasteverlm_ingest.seeds import ensure_seeded
from lasteverlm_ingest.worker import NO_EXCHANGE_RATE, WAITING_FOR_CREDIT, WorkerDeps


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


# Kinds whose stored object the browser can open itself: the object carries
# its content type (image/*, application/pdf, text/plain; charset=utf-8,
# audio/*), so an image shows in an <img>, a PDF in the browser's viewer,
# text as text, a recording in an <audio>.
_STORED_PREVIEW = frozenset({"image", "pdf", "text", "audio"})


def preview_url(
    storage: Storage,
    kind: str,
    storage_path: str | None,
    url: str | None = None,
    transcribed_path: str | None = None,
) -> str | None:
    """Where the frontend opens a library source without a bearer header:
    for an image, PDF, text or audio a presigned GET (valid one hour,
    inline) of the stored object, for a converted recording the MP3 that
    was transcribed; for a URL source the URL itself; None for generated
    rows."""
    if kind == "url":
        return url
    if kind not in _STORED_PREVIEW or not storage_path:
        return None
    return storage.presigned_get(transcribed_path or storage_path)


def original_url(
    storage: Storage, name: str, storage_path: str | None, transcribed_path: str | None
) -> str | None:
    """The uploaded original of a converted recording, presigned as a
    download under its file name (a cross-origin link cannot set that
    itself); None where the original is what `preview_url` opens."""
    if not transcribed_path or not storage_path:
        return None
    return storage.presigned_get(storage_path, download_name=name)


class CreditView:
    """How a listing shows a queued source. `processing` while its owner
    has credit (or it is a sponsored demo seed), `waiting_for_credit`
    otherwise; without an exchange rate in the pricing rules every queued
    source waits and `error` says why. The worker claims none of these
    (see the claim query and `run_worker`). The owner's credit and the
    rate are read at most once per request; nothing here is stored."""

    def __init__(self, repo: Repository, owner: UUID) -> None:
        self._repo = repo
        self._owner = owner
        self._credit: bool | None = None
        self._rate: bool | None = None

    @overload
    def status(self, status: SourceStatus, demo: bool) -> SourceStatus: ...

    @overload
    def status(self, status: str, demo: bool) -> str: ...

    def status(self, status: str, demo: bool) -> str:
        if status != "processing" or demo:
            return status
        if self._credit is None:
            self._credit = self._repo.has_credit(self._owner)
        return status if self._credit else WAITING_FOR_CREDIT

    def error(self, status: str, error: str | None) -> str | None:
        """The reason a queued source waits for the admin, else its error."""
        if status != "processing":
            return error
        if self._rate is None:
            self._rate = self._repo.has_exchange_rate()
        return error if self._rate else NO_EXCHANGE_RATE
