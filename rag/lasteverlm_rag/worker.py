"""Worker entrypoint: claims output jobs from the ``outputs`` table and runs them.

The API process only inserts rows; this loop takes them with
``SELECT ... FOR UPDATE SKIP LOCKED``, so any number of workers can run next
to any number of API pods without a broker. A job whose sources are still
processing is not claimable until they settle (the claim query checks).
A claim older than the stale limit is taken over, which is how a job
survives a worker that died mid-run; a transient failure gives the job
back to the queue, and the service fails it after three attempts.
At start and then hourly it also purges trashed outputs past their
owner's retention.

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

from lasteverlm_core import (
    OpenAICompatibleDecision,
    OpenAICompatibleEmbedder,
    OpenAICompatibleLLM,
    OpenAICompatibleTextToSpeech,
    S3Storage,
    make_client,
)

from .agent_service import AgentService
from .config import Settings
from .judge import judge_models
from .options import SECOND_JUDGE
from .outputs import registry
from .service import OutputService, RagService
from .store import PgVectorRetriever, PostgresStore, Store, make_pool

log = logging.getLogger("lasteverlm_rag.worker")

POLL_INTERVAL_S = 2.0
STALE_CLAIM_S = 10 * 60
# Seconds per model request in the worker; a 4000-token document can take
# longer than the 60 s the API keeps for a chat answer.
WORKER_LLM_TIMEOUT_S = 180
PURGE_INTERVAL_S = 60 * 60


class Worker:
    def __init__(
        self,
        store: Store,
        outputs: OutputService,
        worker_id: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        agent: AgentService | None = None,
        orphan_sweep: bool = False,
    ) -> None:
        self._store = store
        self._outputs = outputs
        # agent plans whose steps wait for an output or for the timeout
        self._agent = agent
        self.worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._sleep = sleep
        self._clock = clock
        self._next_purge: float | None = None
        self._orphan_sweep = orphan_sweep
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> int:
        """One pass: claim and handle jobs until the queue has nothing runnable.
        Returns how many jobs finished (ready or failed)."""
        # starter copies first: no model call, so they need no exchange rate
        while (
            copy_job := self._store.claim_output_copy(self.worker_id, STALE_CLAIM_S)
        ) is not None:
            if not self._outputs.copy_starter(copy_job):
                break  # given back for a retry; the next pass takes it again
        if self._store.pricing_rules().usd_per_eur is None:
            # no job is claimed: a run would pay the platform and book nothing,
            # and the jobs keep their attempts for when the rate is set
            log.error("pricing has no exchange rate (usd_per_eur): no output job runs")
            return 0
        # an output waiting too long for its sources fails, naming one (uncharged)
        self._outputs.expire_waiting()
        finished = 0
        retried: set[str] = set()
        while True:
            job = self._store.claim_output(self.worker_id, STALE_CLAIM_S)
            if job is None:
                break
            if self._outputs.process(job, self.worker_id):
                finished += 1
            elif job.id in retried:
                break  # the same job failed twice this pass; let it rest until the next
            else:
                retried.add(job.id)
        # judgements on request, after the output jobs
        while (judgement := self._store.claim_judge_job(self.worker_id, STALE_CLAIM_S)) is not None:
            if self._outputs.process_judge_job(judgement):
                finished += 1
            else:
                break  # given back for a retry; the next pass takes it again
        if self._agent is not None:
            # after the jobs, so a plan sees the outputs this pass finished
            self._agent.advance()
        return finished

    def purge_if_due(self) -> int:
        """Purge expired trash at the first call and then once per interval.
        Returns how many outputs went."""
        now = self._clock()
        if self._next_purge is not None and now < self._next_purge:
            return 0
        self._next_purge = now + PURGE_INTERVAL_S
        purged = self._outputs.purge_expired()
        if purged:
            log.info("purged %d trashed outputs", purged)
        if self._orphan_sweep:
            self._outputs.sweep_orphans(apply=True)
        return purged

    def run_forever(self) -> None:
        log.info("worker %s started", self.worker_id)
        while not self._stop.is_set():
            try:
                self.purge_if_due()
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
    # a document is one long completion: give it more than the API's default,
    # unless LLM_TIMEOUT_SECONDS already asks for more
    client = make_client(
        settings.inference,
        timeout=max(settings.inference.llm_timeout_seconds, WORKER_LLM_TIMEOUT_S),
    )
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
        tts=(
            OpenAICompatibleTextToSpeech(client, settings.tts_model, voice=settings.tts_voice)
            if settings.tts_model
            else None
        ),
        objects=S3Storage(settings.s3) if settings.s3 else None,
        default_voice=settings.tts_voice,
        # the worker's client timeout also covers a long state (26 s at 112k tokens)
        decision=OpenAICompatibleDecision(client, settings.inference.decision_model),
        judges=judge_models(
            client, {**settings.inference.judge_models, SECOND_JUDGE: settings.second_judge_model}
        ),
    )
    llm = OpenAICompatibleLLM(
        client, settings.inference.llm_model, max_tokens=settings.inference.llm_max_tokens
    )
    embedder = OpenAICompatibleEmbedder(
        client, settings.inference.embedding_model, settings.inference.embedding_dimension
    )
    rag = RagService(
        store,
        PgVectorRetriever(pool),
        embedder,
        llm,
        settings.retrieval_k,
        settings.similarity_floor,
        generated_slots=settings.retrieval_generated_slots,
    )
    # the worker only moves confirmed plans on: no planning, no ingest calls
    agent = AgentService(store, rag, outputs, llm, None, lambda *_: {}, settings.tts_voice)
    worker = Worker(store, outputs, agent=agent, orphan_sweep=settings.orphan_sweep)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: worker.stop())
    try:
        worker.run_forever()
    finally:
        pool.close()  # otherwise the pool's threads hold the process for 20s on SIGTERM


if __name__ == "__main__":
    main()
