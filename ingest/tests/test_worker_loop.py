import threading

from lasteverlm_core import TokenWindowChunker

from lasteverlm_ingest.loaders import default_registry
from lasteverlm_ingest.worker import WorkerDeps, run_worker
from tests.conftest import make_settings
from tests.fakes import FakeEmbedder, FakeSummarizer, InMemoryRepository, InMemoryStorage
from tests.test_worker import add_source


def make_deps(repo, storage, **settings) -> WorkerDeps:
    s = make_settings(WORKER_POLL_SECONDS="1", **settings)
    return WorkerDeps(
        settings=s,
        repository=repo,
        storage=storage,
        loaders=default_registry(),
        chunker=TokenWindowChunker(**s.chunker_kwargs()),
        embedder=FakeEmbedder(),
        summarizer=FakeSummarizer(),
    )


def test_worker_drains_the_queue_oldest_first_and_records_the_claimer():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    first = add_source(repo, storage, b"first document", key="k1")
    second = add_source(repo, storage, b"second document", key="k2")
    done = run_worker(make_deps(repo, storage), threading.Event(), worker_id="w1", max_jobs=2)
    assert done == 2
    assert list(repo.claimed) == [first, second]
    assert set(repo.claimed.values()) == {"w1"}
    assert {s.status for s in repo.sources.values()} == {"ready"}


def test_worker_stops_when_asked_while_idle():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    stop = threading.Event()
    timer = threading.Timer(0.2, stop.set)
    timer.start()
    done = run_worker(make_deps(repo, storage), stop, worker_id="w1")
    assert done == 0


def test_two_workers_never_take_the_same_source():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    ids = [add_source(repo, storage, f"doc {i}".encode(), key=f"k{i}") for i in range(6)]
    deps = make_deps(repo, storage)
    stop = threading.Event()
    results: dict[str, int] = {}

    def worker(name: str) -> None:
        results[name] = run_worker(deps, stop, worker_id=name, max_jobs=3)

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sum(results.values()) == 6
    assert sorted(repo.claimed) == sorted(ids)
    assert all(s.status == "ready" for s in repo.sources.values())
