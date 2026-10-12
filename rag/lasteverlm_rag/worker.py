"""Worker entrypoint: claims output jobs from the ``outputs`` table and runs them.

The API process only inserts rows; this loop takes them with
``SELECT ... FOR UPDATE SKIP LOCKED``, so any number of workers can run next
to any number of API pods without a broker. A job whose sources are still
processing is not claimable until they settle (the claim query checks).
A claim older than the stale limit is taken over, which is how a job
survives a worker that died mid-run; a transient failure gives the job
back to the queue, and the service fails it after three attempts.

    lasteverlm-rag-worker            # or: python -m lasteverlm_rag.worker
"""

from __future__ import annotations

import logging
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable

from lasteverlm_core import OpenAICompatibleEmbedder, OpenAICompatibleLLM, make_client

from .config import Settings
from .outputs import registry
from .service import OutputService
from .store import PgVectorRetriever, PostgresStore, Store, make_pool

log = logging.getLogger("lasteverlm_rag.worker")

POLL_INTERVAL_S = 2.0
STALE_CLAIM_S = 10 * 60


class Worker:
    def __init__(
        self,
        store: Store,
        outputs: OutputService,
        worker_id: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._outputs = outputs
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._sleep = sleep
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> int:
        """One pass: claim and handle jobs until the queue has nothing runnable.
        Returns how many jobs finished (ready or failed)."""
        finished = 0
        retried: set[str] = set()
        while True:
            job = self._store.claim_output(self.worker_id, STALE_CLAIM_S)
            if job is None:
                return finished
            if self._outputs.process(job):
                finished += 1
            elif job.id in retried:
                return finished  # the same job failed twice this pass; let it rest until the next
            else:
                retried.add(job.id)

    def run_forever(self) -> None:
        log.info("worker %s started", self.worker_id)
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("worker pass failed")
            self._sleep(POLL_INTERVAL_S)
        log.info("worker %s stopped", self.worker_id)


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    pool = make_pool(settings.database_url)
    store = PostgresStore(pool, settings.model_prices)
    client = make_client(settings.inference)
    outputs = OutputService(
        store,
        PgVectorRetriever(pool),
        OpenAICompatibleEmbedder(
            client, settings.inference.embedding_model, settings.inference.embedding_dimension
        ),
        OpenAICompatibleLLM(
            client, settings.inference.llm_model, max_tokens=settings.inference.llm_max_tokens
        ),
        registry(tts_available=settings.tts_model is not None),
        settings.retrieval_k,
        settings.similarity_floor,
    )
    worker = Worker(store, outputs)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: worker.stop())
    worker.run_forever()


if __name__ == "__main__":
    main()
