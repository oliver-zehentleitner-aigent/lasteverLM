from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from lasteverlm_core import TokenWindowChunker

from lasteverlm_ingest.loaders import default_registry
from lasteverlm_ingest.worker import WorkerDeps, process_source
from tests.conftest import make_settings
from tests.fakes import FakeEmbedder, FakeSummarizer, InMemoryRepository, InMemoryStorage

USER = UUID("00000000-0000-4000-8000-000000000001")


def deps(repo, storage, embedder, summarizer=None, **settings) -> WorkerDeps:
    s = make_settings(**settings)
    return WorkerDeps(
        settings=s,
        repository=repo,
        storage=storage,
        loaders=default_registry(),
        chunker=TokenWindowChunker(**s.chunker_kwargs()),
        embedder=embedder,
        summarizer=summarizer or FakeSummarizer(),
    )


def add_source(repo, storage, text: bytes, kind="text", key="k") -> UUID:
    nb = repo.create_notebook(USER, "nb")
    sid = repo.add_source(nb.id, "a.txt", kind, key).library_id
    storage.put(key, text, "text/plain")
    return sid


def test_happy_path_writes_chunks_usage_and_ready():
    repo, storage, embedder = InMemoryRepository(), InMemoryStorage(), FakeEmbedder(8)
    sid = add_source(repo, storage, (" ".join(f"w{i}" for i in range(130))).encode())
    process_source(sid, deps(repo, storage, embedder, EMBED_BATCH_SIZE="2"))
    source = repo.library[sid]
    assert source.status == "ready" and source.error is None
    chunks = repo.chunks[sid]
    assert len(chunks) == 3  # 130 tokens, window 50, step 40
    assert all(len(v) == 8 for _, v in chunks)
    assert len(embedder.calls) == 2  # batches of 2
    assert [u.kind for u in repo.usage] == ["embedding", "llm"]
    embedding, llm = repo.usage
    assert embedding.service == "ingest" and embedding.model == "fake-embed"
    assert embedding.tokens_in > 0 and embedding.cost_cents > 0
    assert llm.model == "fake-llm" and llm.tokens_out == 5 and llm.cost_cents > 0
    # One action: processing this text source; its id is the library id.
    assert {(u.action, u.action_id) for u in repo.usage} == {("source:text", sid)}
    assert source.summary.startswith("a.txt: w0 w1")


def test_summary_failure_fails_the_source_but_keeps_chunks_and_usage():
    class Broken(FakeSummarizer):
        def summarize(self, name, passages):
            from lasteverlm_core import ProviderError

            raise ProviderError("summary request failed: 503")

    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = add_source(repo, storage, b"some text here")
    repo.library[sid] = repo.library[sid].model_copy(update={"attempts": 3})
    process_source(sid, deps(repo, storage, FakeEmbedder(), Broken()))
    source = repo.library[sid]
    assert source.status == "failed" and "summary" in source.error
    assert source.summary is None
    assert sid in repo.chunks and [u.kind for u in repo.usage] == ["embedding"]


def test_a_started_read_finishes_when_the_balance_goes_below_zero():
    """Oliver's rule: never spend 90 % and then stop. Credit is checked once,
    before the read; the read books every call and may end below zero."""
    # Less than the embedding costs (exact cents, no rounding up).
    repo = InMemoryRepository(balance=Decimal("0.001"))
    storage, summarizer = InMemoryStorage(), FakeSummarizer()
    sid = add_source(repo, storage, b"some text here")
    assert repo.claim_library_source("w", 600) == sid
    process_source(sid, deps(repo, storage, FakeEmbedder(), summarizer))
    assert repo.library[sid].status == "ready" and summarizer.calls
    assert [u.kind for u in repo.usage] == ["embedding", "llm"]
    owner = repo.library[sid].owner
    assert repo.balance_cents(owner) < 0
    # The owner's next read waits until the balance is positive again.
    nxt = add_source(repo, storage, b"another text", key="k2")
    assert repo.claim_library_source("w", 600) is None
    process_source(nxt, deps(repo, storage, FakeEmbedder(), summarizer))
    assert repo.library[nxt].status == "processing" and repo.library[nxt].error is None


def test_loader_error_marks_failed_with_message():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = add_source(repo, storage, b"not a pdf", kind="pdf")
    process_source(sid, deps(repo, storage, FakeEmbedder()))
    source = repo.library[sid]
    assert source.status == "failed"
    assert "PDF" in source.error
    assert sid not in repo.chunks and repo.usage == []


def test_no_credit_waits_before_embedding():
    repo, storage, embedder = InMemoryRepository(balance=0), InMemoryStorage(), FakeEmbedder()
    sid = add_source(repo, storage, b"some text")
    process_source(sid, deps(repo, storage, embedder))
    assert repo.library[sid].status == "processing" and repo.library[sid].error is None
    assert embedder.calls == []


def test_unexpected_exception_is_hidden_and_retried_until_the_third_attempt():
    class Boom(FakeEmbedder):
        def embed(self, texts):
            raise RuntimeError("secret internals")

    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = add_source(repo, storage, b"some text")
    d = deps(repo, storage, Boom())
    for attempt, delay in ((1, 5), (2, 15)):
        assert repo.claim_library_source("w", 600) == sid
        process_source(sid, d)
        source = repo.library[sid]
        assert source.status == "processing" and source.attempts == attempt
        assert source.error == "internal error while processing the source"
        # The claim is released with a backoff, not held until the stale timeout.
        assert sid not in repo.claimed
        wait = (repo.retry_at[sid] - datetime.now(UTC)).total_seconds()
        assert delay - 1 < wait <= delay
        assert repo.claim_library_source("w", 600) is None  # not before the backoff
        repo.retry_at[sid] = datetime.now(UTC)  # the backoff elapsed
    assert repo.claim_library_source("w", 600) == sid
    process_source(sid, d)
    source = repo.library[sid]
    assert source.status == "failed" and source.attempts == 3
    assert "secret" not in source.error


def test_transient_provider_error_keeps_processing_for_a_retry():
    class Flaky(FakeEmbedder):
        def embed(self, texts):
            from lasteverlm_core import ProviderError

            raise ProviderError("embedding request failed: 503")

    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = add_source(repo, storage, b"some text")
    repo.claim_library_source("w", 600)
    process_source(sid, deps(repo, storage, Flaky()))
    source = repo.library[sid]
    assert source.status == "processing" and "503" in source.error and source.attempts == 1


def test_vanished_source_is_a_noop():
    process_source(uuid4(), deps(InMemoryRepository(), InMemoryStorage(), FakeEmbedder()))


def test_without_an_exchange_rate_nothing_is_called_and_the_source_waits():
    from lasteverlm_core import PricingRules

    repo, storage, embedder = InMemoryRepository(), InMemoryStorage(), FakeEmbedder()
    sid = add_source(repo, storage, b"some text")
    assert repo.claim_library_source("w", 600) == sid
    rules, repo.rules = repo.rules, PricingRules()  # reset to defaults: no usd_per_eur
    process_source(sid, deps(repo, storage, embedder))
    source = repo.library[sid]
    # Back in the queue, the attempt not counted; nothing paid upstream.
    assert source.status == "processing" and source.attempts == 0 and source.error is None
    assert embedder.calls == [] and repo.usage == []
    # The admin sets the rate: it runs, no re-upload needed.
    repo.rules = rules
    assert repo.claim_library_source("w", 600) == sid
    process_source(sid, deps(repo, storage, embedder))
    assert repo.library[sid].status == "ready"


def test_the_worker_claims_nothing_without_an_exchange_rate():
    import threading

    from lasteverlm_core import PricingRules

    from lasteverlm_ingest.worker import run_worker

    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = add_source(repo, storage, b"some text")
    repo.rules = PricingRules()
    stop = threading.Event()
    d = deps(repo, storage, FakeEmbedder(), WORKER_POLL_SECONDS="1")
    timer = threading.Timer(0.2, stop.set)
    timer.start()
    assert run_worker(d, stop, worker_id="w") == 0
    assert repo.library[sid].attempts == 0 and sid not in repo.claimed
