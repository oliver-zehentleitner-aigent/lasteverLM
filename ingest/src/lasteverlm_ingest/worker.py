"""The worker: claims library sources from the database and runs the
pipeline for each — load from storage, parse, chunk, embed, write chunks,
summarize, record usage, set the status. A library source is processed
once, whatever number of notebooks it is linked into.

The queue is the `library_sources` table itself: a `processing` row that
no worker holds. `run_worker` claims one at a time with
`FOR UPDATE SKIP LOCKED`, so any number of worker pods share the work
without a broker, and the API pods never process anything. Entrypoint:
`lasteverlm-ingest-worker` (same image as the API).
"""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import socket
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from lasteverlm_core import (
    Chunker,
    Embedder,
    ProviderError,
    Storage,
    StorageError,
    Usage,
    object_key,
)

from lasteverlm_ingest.config import Settings
from lasteverlm_ingest.loaders import (
    LoaderError,
    LoaderRegistry,
    ModelLoader,
    Passage,
    TransientLoaderError,
    loader_key,
)
from lasteverlm_ingest.loaders.audio import AudioLoader
from lasteverlm_ingest.loaders.convert import convert_to_mp3, sniff_container
from lasteverlm_ingest.loaders.image import ImageLoader
from lasteverlm_ingest.loaders.pdf import VisionPdfLoader
from lasteverlm_ingest.loaders.snapshot import html_snapshot, text_snapshot
from lasteverlm_ingest.loaders.url import Fetched, UrlLoader
from lasteverlm_ingest.repository import MAX_ATTEMPTS, LibrarySource, Repository
from lasteverlm_ingest.summarizer import Summarizer

log = logging.getLogger(__name__)

_ERROR_MAX = 500
# How the API shows a `processing` source whose owner has no credit: it
# is not claimed until the owner has credit again (see the claim query).
WAITING_FOR_CREDIT = "waiting_for_credit"
# The web matches this exact sentence (shown on waiting sources): changing
# it is a contract change, tell web.
NO_EXCHANGE_RATE = "pricing has no exchange rate, ask an admin"
# Backoff after a transient failure: 5 s after the first, 15 s after the second.
RETRY_BASE_SECONDS = 5.0
RETRY_FACTOR = 3.0
# The trash is purged at worker start and then once an hour.
PURGE_EVERY_SECONDS = 3600.0


@dataclass(frozen=True)
class WorkerDeps:
    settings: Settings
    repository: Repository
    storage: Storage
    loaders: LoaderRegistry
    chunker: Chunker
    embedder: Embedder
    summarizer: Summarizer


class ProcessingError(Exception):
    """A failure whose message is safe to show to the user."""


class WaitForRate(Exception):
    """The pricing rules have no exchange rate: a model call could be paid
    upstream but not booked. The source goes back to the queue without
    counting the attempt; workers claim nothing until the rate is back."""


class WaitForCredit(Exception):
    """The owner's credit ran out: the source goes back to the queue
    without counting the attempt and is claimed again once there is
    credit."""


def process_source(library_id: UUID, deps: WorkerDeps) -> None:
    repo = deps.repository
    source = repo.get_library_source(library_id)
    if source is None:
        log.info("library source %s vanished before processing", library_id)
        return
    try:
        _run(source, deps)
    except WaitForCredit:
        log.info("library source %s waits for its owner's credit", library_id)
        repo.release_waiting(library_id)
    except WaitForRate:
        log.warning("library source %s waits: %s", library_id, NO_EXCHANGE_RATE)
        repo.release_waiting(library_id)
    except (LoaderError, ProcessingError) as exc:
        # Will not change on a retry: the source is failed at once.
        log.warning("library source %s failed: %s", library_id, exc)
        repo.set_library_status(library_id, "failed", str(exc)[:_ERROR_MAX])
    except ProviderError as exc:
        if exc.permanent:
            # The platform refused the request with a 4xx a retry will not
            # change: failing now saves the attempts.
            log.warning("library source %s refused by the provider: %s", library_id, exc)
            repo.set_library_status(library_id, "failed", str(exc)[:_ERROR_MAX])
        else:
            _retry_or_fail(source, str(exc)[:_ERROR_MAX], repo, exc)
    except (StorageError, TransientLoaderError) as exc:
        # May pass next time (the bucket, a web server).
        _retry_or_fail(source, str(exc)[:_ERROR_MAX], repo, exc)
    except Exception as exc:
        _retry_or_fail(source, "internal error while processing the source", repo, exc)


def retry_delay(attempt: int) -> float:
    """Seconds before the next attempt after `attempt` failed: 5, 15, 45 …"""
    return RETRY_BASE_SECONDS * RETRY_FACTOR ** max(0, attempt - 1)


def _retry_or_fail(source: LibrarySource, message: str, repo: Repository, exc: Exception) -> None:
    """A transient failure keeps the row `processing` with the error and
    releases the claim with a short backoff, so the next attempt follows
    within seconds instead of waiting for the stale-claim timeout; the third
    failed attempt fails it for good."""
    if source.attempts >= MAX_ATTEMPTS:
        log.warning("source %s failed after %d attempts: %s", source.id, source.attempts, exc)
        repo.set_library_status(source.id, "failed", message)
    else:
        delay = retry_delay(source.attempts)
        log.warning(
            "source %s attempt %d/%d failed, retried in %.0f s: %s",
            source.id,
            source.attempts,
            MAX_ATTEMPTS,
            delay,
            exc,
        )
        repo.release_for_retry(source.id, message, delay)


def _run(source: LibrarySource, deps: WorkerDeps) -> None:
    repo = deps.repository
    source_id = source.id
    # Usage rows name the notebook the source was first added to.
    notebook_id = repo.first_notebook(source_id)
    if source.storage_path is None:
        raise ProcessingError(f"source kind {source.kind!r} has nothing to load yet")
    _may_start(repo, source)
    data = deps.storage.get(source.storage_path)
    if source.kind == "audio":
        data = _transcribable(source, data, deps)
    key = loader_key(source.kind, source.capture)
    if key not in deps.loaders.kinds and key != source.kind:
        raise ProcessingError(f"capture mode {source.capture} needs a vision model")
    loader = deps.loaders.get(key)
    fetched: Fetched | None = None
    if isinstance(loader, ModelLoader):
        # Reading this source takes model calls of its own (images, PDF
        # pages): each one is recorded as it returns.
        _may_call(repo, source)

        def bill(usage: Usage) -> None:
            _record(repo, source, notebook_id, usage)
            # A vision PDF can take longer than the claim timeout; each
            # answered call shows the job is alive (see refresh_claim).
            repo.refresh_claim(source_id)
            _may_call(repo, source)

        passages = loader.load_billed(data, bill)
        repo.set_read_by(source_id, *_read_by(loader, data))
    elif isinstance(loader, UrlLoader):
        fetched, passages = loader.load_page(data)
    else:
        fetched, passages = None, loader.load(data)
    if source.kind == "url":
        # A web page is compared before any model call: fetched again and
        # unchanged, it costs nothing; changed, it becomes a new version.
        digest = content_digest(passages)
        if source.refetch_requested_at is not None:
            if digest == source.content_hash:
                # A version read before snapshots existed gets one now: the
                # same text, so still a snapshot of what was read.
                backfill = None
                if source.snapshot_path is None and fetched is not None:
                    backfill = _store_snapshot(source, fetched, passages, deps)
                repo.refetch_unchanged(
                    source_id, backfill, fetched.url if backfill and fetched else None
                )
                log.info("web page %s fetched again: unchanged", source_id)
            else:
                new_id = repo.new_version(source_id)
                log.info("web page %s changed: version %s queued", source_id, new_id)
            return
        snapshot = _store_snapshot(source, fetched, passages, deps) if fetched else None
        repo.set_fetched(source_id, digest, fetched.url if fetched else None, snapshot)
    chunks = deps.chunker.chunk(passages)
    if not chunks:
        raise ProcessingError("no text to index")
    _may_call(repo, source)

    vectors: list[list[float]] = []
    tokens = 0
    batch_size = max(1, deps.settings.embed_batch_size)
    for start in range(0, len(chunks), batch_size):
        result = deps.embedder.embed([c.text for c in chunks[start : start + batch_size]])
        vectors.extend(result.vectors)
        tokens += result.usage.tokens_in
        repo.refresh_claim(source_id)

    repo.replace_chunks(source_id, chunks, vectors)
    _record(repo, source, notebook_id, Usage("embedding", deps.embedder.model, tokens, 0))

    # The summary is its own model call with its own usage row. Without a
    # summary the source is not usable by the output generators, so a
    # failure here fails the source.
    _may_call(repo, source)
    summary = deps.summarizer.summarize(source.name, passages)
    _record(repo, source, notebook_id, summary.usage)
    repo.set_library_summary(source_id, summary.text)
    repo.set_library_status(source_id, "ready", None)
    log.info(
        "library source %s ready: %d chunks, %d embedding tokens, %d+%d summary tokens",
        source_id,
        len(chunks),
        tokens,
        summary.usage.tokens_in,
        summary.usage.tokens_out,
    )


def _read_by(
    loader: ModelLoader, data: bytes
) -> tuple[dict[str, str | None] | None, list[int] | None]:
    """Which model made the source's text, and the PDF pages the vision
    model read (None for an image: all of it, it has no pages)."""
    if isinstance(loader, ImageLoader):
        return {"vision": loader.model, "stt": None}, None
    if isinstance(loader, AudioLoader):
        return {"vision": None, "stt": loader.model}, None
    if isinstance(loader, VisionPdfLoader):
        pages = loader.vision_pages(data)
        return ({"vision": loader.model, "stt": None} if pages else None), pages or None
    return None, None


# The converted recording's object name; safe_name never yields a leading
# underscore, so it cannot collide with an uploaded original's name.
TRANSCRIBED_NAME = "_transcribed.mp3"


def _transcribable(source: LibrarySource, data: bytes, deps: WorkerDeps) -> bytes:
    """The bytes to transcribe: MP3 and WAV as uploaded; anything else
    converted to MP3 once and stored beside the original, so the user can
    hear what was transcribed and a retry does not convert again."""
    container = sniff_container(data)
    if container is None:
        return data
    if source.transcribed_path:
        try:
            return deps.storage.get(source.transcribed_path)
        except StorageError:
            log.info("converted audio of %s missing, converting again", source.id)
    mp3 = convert_to_mp3(data, container)
    key = object_key(source.owner, source.id, TRANSCRIBED_NAME)
    deps.storage.put(key, mp3, "audio/mpeg")
    deps.repository.set_transcribed_path(source.id, key)
    deps.repository.refresh_claim(source.id)
    return mp3


# The snapshot's object name; safe_name never yields a leading underscore.
SNAPSHOT_NAME = "_snapshot.html"


def _store_snapshot(
    source: LibrarySource, fetched: Fetched, passages: list[Passage], deps: WorkerDeps
) -> str | None:
    """Keep what was read as an inert HTML file beside the source (see
    loaders/snapshot.py); None for a PDF behind a URL, whose own file is
    what was read. Text and structured data show the text that was read
    (structured data as its rendering, not its raw body)."""
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if fetched.media_type in ("text/html", "application/xhtml+xml"):
        try:
            html = fetched.body.decode(fetched.charset or "utf-8", errors="replace")
        except LookupError:  # a charset Python does not know
            html = fetched.body.decode("utf-8", errors="replace")
        page = html_snapshot(html, fetched.url, when)
    elif fetched.media_type != "application/pdf":
        page = text_snapshot("\n\n".join(p.text for p in passages), fetched.url, when)
    else:
        return None
    key = object_key(source.owner, source.id, SNAPSHOT_NAME)
    deps.storage.put(key, page.encode("utf-8"), "text/html; charset=utf-8")
    return key


def content_digest(passages: list[Passage]) -> str:
    """The hash a web page's versions are compared by: its extracted text,
    whitespace-normalized, so markup or spacing alone is no new version."""
    text = "\n".join(" ".join(p.text.split()) for p in passages)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _payer(source: LibrarySource) -> UUID:
    """Who pays for processing: the owner."""
    return source.owner


def _may_call(repo: Repository, source: LibrarySource) -> None:
    """Checked before every model call: without an exchange rate in the
    pricing rules a call could be paid upstream but not booked, so the
    source waits. Credit is not checked here: a read that has started runs
    to the end (see `_may_start`)."""
    if not repo.has_exchange_rate():
        raise WaitForRate


def _may_start(repo: Repository, source: LibrarySource) -> None:
    """Checked once, before a read starts: without credit the source waits,
    unless its read was funded when it was asked for (see api/funding.py).
    Once started, a read finishes and books every call even if the balance
    goes below zero on the way; the owner's next read waits until it is
    positive again."""
    if source.funded_request_at is None and not _has_credit(repo, source):
        raise WaitForCredit


def _has_credit(repo: Repository, source: LibrarySource) -> bool:
    return repo.has_credit(source.owner)


def _action(source: LibrarySource) -> str:
    """What the usage rows of processing this source are booked as."""
    return f"source:{source.kind}"


def _record(
    repo: Repository, source: LibrarySource, notebook_id: UUID | None, usage: Usage
) -> None:
    """Book one model call. Every call of processing one source (vision
    pages, the transcription, the embeddings, the summary) is one action:
    its `action_id` is the library source's id, retries included."""
    repo.record_usage(_payer(source), notebook_id, _action(source), source.id, usage)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def purge_trash(deps: WorkerDeps) -> int:
    """Delete the trashed library sources whose owner's retention has
    elapsed, then their stored objects. Several workers may run it at once:
    a row is deleted by exactly one of them."""
    keys = deps.repository.purge_expired()
    if keys:
        try:
            deps.storage.delete(*keys)
        except StorageError as exc:
            # The rows are gone; an object left behind is only storage.
            log.warning("purged %d library source(s), objects not removed: %s", len(keys), exc)
        log.info("purged %d library source(s) from the trash", len(keys))
    return len(keys)


def _purge(deps: WorkerDeps, every_seconds: float) -> float:
    """Purge the trash; a failure is logged and waits for the next round.
    Returns when the next purge is due."""
    try:
        purge_trash(deps)
    except Exception:
        log.exception("trash purge failed, next try in %.0f s", every_seconds)
    return time.monotonic() + every_seconds


def run_worker(
    deps: WorkerDeps,
    stop: threading.Event,
    *,
    worker_id: str | None = None,
    max_jobs: int | None = None,
    purge_every_seconds: float = PURGE_EVERY_SECONDS,
) -> int:
    """Claim and process sources until `stop` is set (or `max_jobs` were
    done), purging the trash at start and every `purge_every_seconds`.
    Returns the number of processed sources. A job in flight is finished
    before the loop looks at `stop` again."""
    worker_id = worker_id or default_worker_id()
    settings = deps.settings
    done = 0
    rate_missing = False
    log.info("worker %s started", worker_id)
    next_purge = _purge(deps, purge_every_seconds)
    while not stop.is_set() and (max_jobs is None or done < max_jobs):
        if time.monotonic() >= next_purge:
            next_purge = _purge(deps, purge_every_seconds)
        if not deps.repository.has_exchange_rate():
            # Nothing can be booked: claim nothing until an admin sets the
            # rate (the sources show why they wait).
            if not rate_missing:
                log.warning("worker %s pauses: %s", worker_id, NO_EXCHANGE_RATE)
                rate_missing = True
            stop.wait(settings.worker_poll_seconds)
            continue
        rate_missing = False
        source_id = deps.repository.claim_library_source(worker_id, settings.claim_timeout_seconds)
        if source_id is None:
            stop.wait(settings.worker_poll_seconds)
            continue
        log.info("worker %s claimed source %s", worker_id, source_id)
        process_source(source_id, deps)
        done += 1
    log.info("worker %s stopping after %d source(s)", worker_id, done)
    return done


def main() -> None:
    """Console entrypoint: build everything from the environment and run
    until SIGTERM or SIGINT, finishing the current source first."""
    from lasteverlm_ingest.main import build_worker_deps

    deps = build_worker_deps()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        run_worker(deps, stop)
    finally:
        close = getattr(deps.repository, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
