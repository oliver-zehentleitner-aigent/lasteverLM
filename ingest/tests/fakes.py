"""In-memory stand-ins for the external systems. Tests never touch a
database, a bucket or an inference API."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

from lasteverlm_core import (
    Chunk,
    CompletionResult,
    EmbeddingResult,
    ModelPrices,
    Notebook,
    Passage,
    Usage,
    UsageRecord,
    cost_cents,
    parse_model_prices,
)

from lasteverlm_ingest.repository import StoredSource


class InMemoryRepository:
    def __init__(self, balance: int = 1000, prices: ModelPrices | None = None) -> None:
        self.prices = (
            prices
            if prices is not None
            else parse_model_prices(
                '{"fake-embed": {"in": 2000, "out": 0}, "fake-llm": {"in": 30, "out": 150}}'
            )
        )
        self.notebooks: dict[UUID, tuple[UUID, Notebook]] = {}
        self.sources: dict[UUID, StoredSource] = {}
        self.chunks: dict[UUID, list[tuple[Chunk, list[float]]]] = {}
        self.usage: list[UsageRecord] = []
        self.credits: dict[UUID, int] = {}
        self.claimed: dict[UUID, str] = {}
        self.default_balance = balance

    def list_notebooks(self, owner: UUID) -> list[Notebook]:
        return [nb for o, nb in self.notebooks.values() if o == owner]

    def create_notebook(self, owner: UUID, title: str) -> Notebook:
        nb = Notebook(id=uuid4(), title=title, created_at=datetime.now(UTC))
        self.notebooks[nb.id] = (owner, nb)
        return nb

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> Notebook | None:
        entry = self.notebooks.get(notebook_id)
        return entry[1] if entry and entry[0] == owner else None

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> list[str]:
        if self.get_notebook(owner, notebook_id) is None:
            return []
        keys = [
            s.storage_path
            for s in self.sources.values()
            if s.notebook_id == notebook_id and s.storage_path
        ]
        for sid in [s.id for s in self.sources.values() if s.notebook_id == notebook_id]:
            self.delete_source(sid)
        del self.notebooks[notebook_id]
        return keys

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]:
        return [s for s in self.sources.values() if s.notebook_id == notebook_id]

    def create_source(
        self, notebook_id: UUID, source_id: UUID, name: str, kind: str, storage_path: str | None
    ) -> StoredSource:
        owner = self.notebooks[notebook_id][0]
        source = StoredSource(
            id=source_id,
            notebook_id=notebook_id,
            name=name,
            kind=kind,
            status="processing",
            error=None,
            created_at=datetime.now(UTC),
            owner=owner,
            storage_path=storage_path,
        )
        self.sources[source_id] = source
        return source

    def get_source(self, source_id: UUID) -> StoredSource | None:
        return self.sources.get(source_id)

    def delete_source(self, source_id: UUID) -> None:
        self.sources.pop(source_id, None)
        self.chunks.pop(source_id, None)

    def set_source_status(self, source_id: UUID, status: str, error: str | None = None) -> None:
        self.sources[source_id] = self.sources[source_id].model_copy(
            update={"status": status, "error": error}
        )

    def claim_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        for source in sorted(self.sources.values(), key=lambda s: s.created_at):
            if source.status == "processing" and source.id not in self.claimed:
                self.claimed[source.id] = worker_id
                self.sources[source.id] = source.model_copy(
                    update={"attempts": source.attempts + 1}
                )
                return source.id
        return None

    def set_source_summary(self, source_id: UUID, summary: str) -> None:
        self.sources[source_id] = self.sources[source_id].model_copy(update={"summary": summary})

    def replace_chunks(
        self, source_id: UUID, notebook_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        self.chunks[source_id] = list(zip(chunks, vectors, strict=True))

    def record_usage(self, user_id, notebook_id, kind, model, tokens_in, tokens_out) -> UsageRecord:
        usage = UsageRecord(
            user_id=user_id,
            notebook_id=notebook_id,
            service="ingest",
            kind=kind,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_cents=cost_cents(self.prices, model, tokens_in, tokens_out),
        )
        self.usage.append(usage)
        return usage

    def balance_cents(self, user_id: UUID) -> int:
        credits = self.credits.get(user_id, self.default_balance)
        return credits - sum(u.cost_cents for u in self.usage if u.user_id == user_id)


class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, keys: list[str]) -> None:
        for key in keys:
            self.objects.pop(key, None)


class FakeEmbedder:
    """Deterministic unit vectors from a hash of the text; one token per
    four characters, which is what the pricing math is tested against."""

    def __init__(self, dimension: int = 8, model: str = "fake-embed") -> None:
        self._dimension = dimension
        self._model = model
        self.calls: list[list[str]] = []

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> EmbeddingResult:
        self.calls.append(texts)
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [digest[i % len(digest)] - 128 for i in range(self._dimension)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            vectors.append([x / norm for x in raw])
        tokens = sum(math.ceil(len(t) / 4) for t in texts)
        return EmbeddingResult(vectors, Usage("embedding", self._model, tokens, 0))


class FakeSummarizer:
    def __init__(self, model: str = "fake-llm") -> None:
        self._model = model
        self.calls: list[tuple[str, list[Passage]]] = []

    @property
    def model(self) -> str:
        return self._model

    def summarize(self, name: str, passages: list[Passage]) -> CompletionResult:
        self.calls.append((name, passages))
        words = " ".join(p.text for p in passages).split()
        return CompletionResult(
            f"{name}: {' '.join(words[:5])}", Usage("llm", self._model, len(words), 5)
        )
