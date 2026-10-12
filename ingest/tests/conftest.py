from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lasteverlm_ingest.config import Settings
from lasteverlm_ingest.main import create_app
from tests.fakes import FakeEmbedder, FakeSummarizer, InMemoryRepository, InMemoryStorage

DEMO_TOKEN = "test-demo-token"


def make_settings(**overrides) -> Settings:
    env = {
        "DATABASE_URL": "postgresql://unused",
        "S3_ENDPOINT": "https://s3.invalid",
        "S3_BUCKET": "bucket",
        "S3_ACCESS_KEY": "ak",
        "S3_SECRET_KEY": "sk",
        "INFERENCE_BASE_URL": "https://inference.invalid/v1",
        "INFERENCE_API_KEY": "key",
        "EMBEDDING_MODEL": "fake-embed",
        "LLM_MODEL": "fake-llm",
        "EMBEDDING_DIMENSION": "8",
        "MODEL_PRICES": (
            '{"fake-embed": {"in": 2000, "out": 0}, "fake-llm": {"in": 30, "out": 150}}'
        ),
        "DEMO_TOKEN": DEMO_TOKEN,
        "CHUNK_TOKENS": "50",
        "CHUNK_OVERLAP_TOKENS": "10",
        "MAX_UPLOAD_BYTES": "4096",
    }
    env.update(overrides)
    return Settings.from_env(env)


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(dimension=8)


@pytest.fixture
def summarizer() -> FakeSummarizer:
    return FakeSummarizer()


@pytest.fixture
def client(repo, storage, embedder, summarizer) -> TestClient:
    app = create_app(
        make_settings(),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
    )
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        yield c


@pytest.fixture
def run_queue(repo, storage, embedder, summarizer):
    """Process everything currently queued, the way a worker pod would."""
    import threading

    from lasteverlm_ingest.main import build_worker_deps
    from lasteverlm_ingest.worker import run_worker

    deps = build_worker_deps(
        make_settings(WORKER_POLL_SECONDS="1"),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
    )

    def run() -> int:
        pending = sum(
            1
            for s in repo.sources.values()
            if s.status == "processing" and s.id not in repo.claimed
        )
        return run_worker(deps, threading.Event(), worker_id="test", max_jobs=pending)

    return run
