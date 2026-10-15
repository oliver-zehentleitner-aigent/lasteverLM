from __future__ import annotations

from decimal import Decimal
from typing import overload
from uuid import UUID

from fastapi import HTTPException, Request
from lasteverlm_core import Notebook, SourceStatus, Storage

from lasteverlm_ingest.repository import Repository, StoredSource
from lasteverlm_ingest.starter import ensure_starter
from lasteverlm_ingest.worker import NO_EXCHANGE_RATE, WAITING_FOR_CREDIT, WorkerDeps


def worker_deps(request: Request) -> WorkerDeps:
    deps: WorkerDeps = request.app.state.worker
    return deps


def repository(request: Request) -> Repository:
    return worker_deps(request).repository


def seed_if_new(request: Request, user: UUID) -> None:
    """The starter notebook on the owner's first notebook list, library
    listing or upload; once considered, one indexed exists query."""
    deps = worker_deps(request)
    ensure_starter(deps.repository, deps.storage, user)


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


def snapshot_url(storage: Storage, snapshot_path: str | None) -> str | None:
    """A web page version's snapshot (the inert HTML of what was read),
    presigned for one hour, shown inline as `text/html`; None before the
    first fetch and for every other kind."""
    return storage.presigned_get(snapshot_path) if snapshot_path else None


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
    has credit, `waiting_for_credit`
    otherwise; without an exchange rate in the pricing rules every queued
    source waits and `error` says why. The worker claims none of these
    (see the claim query and `run_worker`). The owner's credit and the
    rate are read at most once per request; nothing here is stored."""

    def __init__(self, repo: Repository, owner: UUID) -> None:
        self._repo = repo
        self._owner = owner
        self._free: Decimal | None = None
        self._read_free = False
        self._rate: bool | None = None

    @overload
    def status(
        self, status: SourceStatus, funded: bool = False, estimate: Decimal | None = None
    ) -> SourceStatus: ...

    @overload
    def status(self, status: str, funded: bool = False, estimate: Decimal | None = None) -> str: ...

    def status(self, status: str, funded: bool = False, estimate: Decimal | None = None) -> str:
        # A read funded when it was asked for does not wait for credit; any
        # other waits until the balance, less what funded reads hold, covers
        # its estimated maximum (the claim query's rule).
        if status != "processing" or funded:
            return status
        if not self._read_free:
            self._read_free = True
            balance = self._repo.balance_cents(self._owner)
            held = self._repo.funded_waiting_cents(self._owner)
            # None: no positive balance, nothing can start.
            self._free = balance - held if balance > 0 else None
        if self._free is not None and self._free >= (estimate or 0):
            return status
        return WAITING_FOR_CREDIT

    def error(self, status: str, error: str | None) -> str | None:
        """The reason a queued source waits for the admin, else its error."""
        if status != "processing":
            return error
        if self._rate is None:
            self._rate = self._repo.has_exchange_rate()
        return error if self._rate else NO_EXCHANGE_RATE
