"""The worker: claims sources from the database and runs the pipeline
for each — load from storage, parse, chunk, embed, write chunks,
summarize, record usage, set the status.

The queue is the `sources` table itself: a `processing` row that no
worker holds. `run_worker` claims one at a time with
`FOR UPDATE SKIP LOCKED`, so any number of worker pods share the work
without a broker, and the API pods never process anything. Entrypoint:
`lasteverlm-ingest-worker` (same image as the API).
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
from dataclasses import dataclass
from uuid import UUID

from lasteverlm_core import Chunker, Embedder, ProviderError

from lasteverlm_ingest.config import Settings
from lasteverlm_ingest.loaders import LoaderError, LoaderRegistry, TransientLoaderError
from lasteverlm_ingest.repository import Repository, StoredSource
from lasteverlm_ingest.storage import Storage, StorageError
from lasteverlm_ingest.summarizer import Summarizer

log = logging.getLogger(__name__)

_ERROR_MAX = 500
CREDIT_EXHAUSTED = "credit exhausted"
# Family rule: after three attempts a job is failed with its last error.
MAX_ATTEMPTS = 3


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


def process_source(source_id: UUID, deps: WorkerDeps) -> None:
    repo = deps.repository
    source = repo.get_source(source_id)
    if source is None:
        log.info("source %s vanished before processing", source_id)
        return
    try:
        _run(source_id, deps)
    except (LoaderError, ProcessingError) as exc:
        # Will not change on a retry: the source is failed at once.
        log.warning("source %s failed: %s", source_id, exc)
        repo.set_source_status(source_id, "failed", str(exc)[:_ERROR_MAX])
    except (StorageError, ProviderError, TransientLoaderError) as exc:
        # May pass next time (a provider hiccup, the bucket, a web server).
        _retry_or_fail(source, str(exc)[:_ERROR_MAX], repo, exc)
    except Exception as exc:
        _retry_or_fail(source, "internal error while processing the source", repo, exc)


def _retry_or_fail(source: StoredSource, message: str, repo: Repository, exc: Exception) -> None:
    """A transient failure keeps the row `processing` with the error, so
    the stale-claim timeout hands it to the next worker; the third failed
    attempt fails it for good."""
    if source.attempts >= MAX_ATTEMPTS:
        log.warning("source %s failed after %d attempts: %s", source.id, source.attempts, exc)
        repo.set_source_status(source.id, "failed", message)
    else:
        log.warning(
            "source %s attempt %d/%d failed, will be retried: %s",
            source.id,
            source.attempts,
            MAX_ATTEMPTS,
            exc,
        )
        repo.set_source_status(source.id, "processing", message)


def _run(source_id: UUID, deps: WorkerDeps) -> None:
    repo = deps.repository
    source = repo.get_source(source_id)
    assert source is not None
    if source.storage_path is None:
        raise ProcessingError(f"source kind {source.kind!r} has nothing to load yet")
    data = deps.storage.get(source.storage_path)
    passages = deps.loaders.get(source.kind).load(data)
    chunks = deps.chunker.chunk(passages)
    if not chunks:
        raise ProcessingError("no text to index")
    if repo.balance_cents(source.owner) <= 0:
        raise ProcessingError(CREDIT_EXHAUSTED)

    vectors: list[list[float]] = []
    tokens = 0
    batch_size = max(1, deps.settings.embed_batch_size)
    for start in range(0, len(chunks), batch_size):
        result = deps.embedder.embed([c.text for c in chunks[start : start + batch_size]])
        vectors.extend(result.vectors)
        tokens += result.usage.tokens_in

    repo.replace_chunks(source_id, source.notebook_id, chunks, vectors)
    repo.record_usage(
        user_id=source.owner,
        notebook_id=source.notebook_id,
        kind="embedding",
        model=deps.embedder.model,
        tokens_in=tokens,
        tokens_out=0,
    )

    # The summary is its own model call, so it gets its own credit check
    # and its own usage row. Without a summary the source is not usable by
    # the output generators, so a failure here fails the source.
    if repo.balance_cents(source.owner) <= 0:
        raise ProcessingError(CREDIT_EXHAUSTED)
    summary = deps.summarizer.summarize(source.name, passages)
    repo.record_usage(
        user_id=source.owner,
        notebook_id=source.notebook_id,
        kind=summary.usage.kind,
        model=summary.usage.model,
        tokens_in=summary.usage.tokens_in,
        tokens_out=summary.usage.tokens_out,
    )
    repo.set_source_summary(source_id, summary.text)
    repo.set_source_status(source_id, "ready", None)
    log.info(
        "source %s ready: %d chunks, %d embedding tokens, %d+%d summary tokens",
        source_id,
        len(chunks),
        tokens,
        summary.usage.tokens_in,
        summary.usage.tokens_out,
    )


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_worker(
    deps: WorkerDeps,
    stop: threading.Event,
    *,
    worker_id: str | None = None,
    max_jobs: int | None = None,
) -> int:
    """Claim and process sources until `stop` is set (or `max_jobs` were
    done). Returns the number of processed sources. A job in flight is
    finished before the loop looks at `stop` again."""
    worker_id = worker_id or default_worker_id()
    settings = deps.settings
    done = 0
    log.info("worker %s started", worker_id)
    while not stop.is_set() and (max_jobs is None or done < max_jobs):
        source_id = deps.repository.claim_source(worker_id, settings.claim_timeout_seconds)
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
