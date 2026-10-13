from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import (
    DEMO_USER_ID,
    CompletionResult,
    EmbeddingResult,
    MemoryRateLimitStore,
    Message,
    OutputKind,
    OutputStatus,
    ProviderError,
    Usage,
)
from lasteverlm_core.chunking import Chunk

from lasteverlm_rag.config import Settings
from lasteverlm_rag.main import create_app
from lasteverlm_rag.models import (
    ConversationRow,
    OutputRow,
    RetrievedChunk,
    SourceState,
    SourceSummary,
)
from lasteverlm_rag.outputs import registry
from lasteverlm_rag.service import OutputService
from lasteverlm_rag.worker import Worker

DEMO_TOKEN = "demo-secret"
OWNER = str(DEMO_USER_ID)
NOTEBOOK = str(uuid.uuid4())
OTHER_NOTEBOOK = str(uuid.uuid4())
CONVERSATION = str(uuid.uuid4())
AUTH = {"Authorization": f"Bearer {DEMO_TOKEN}"}
PRICES = '{"test-llm": {"in": 100, "out": 300}, "test-embedding": {"in": 10, "out": 0}}'

BASE_ENV = {
    "DATABASE_URL": "postgresql://test",
    "INFERENCE_BASE_URL": "https://inference.example/v1",
    "INFERENCE_API_KEY": "key",
    "LLM_MODEL": "test-llm",
    "EMBEDDING_MODEL": "test-embedding",
    "MODEL_PRICES": PRICES,
}


_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")


def source_uuid(i: int) -> str:
    return str(uuid.uuid5(_NS, f"source-{i}"))


def chunk_uuid(i: int) -> str:
    return str(uuid.uuid5(_NS, f"chunk-{i}"))


SOURCE_1, CHUNK_1 = source_uuid(1), chunk_uuid(1)


def chunk(
    i: int, text: str, page: int | None = None, similarity: float = 0.9, source_kind: str = "pdf"
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_uuid(i),
        source_id=source_uuid(i),
        source_name=f"doc{i}.pdf",
        source_kind=source_kind,  # type: ignore[arg-type]
        page=page,
        text=text,
        similarity=similarity,
    )


class FakeStore:
    """In-memory stand-in for PostgresStore with the same contract."""

    def __init__(self, balance: int = 100, admins: set[str] | None = None) -> None:
        self.balance = balance
        self.admins = admins or set()
        self.messages: list[dict[str, Any]] = []
        self.usage: list[tuple[str, str | None, Usage]] = []
        self.notebooks = {
            NOTEBOOK: {"id": NOTEBOOK, "owner": OWNER, "title": "My notebook"},
            OTHER_NOTEBOOK: {"id": OTHER_NOTEBOOK, "owner": "someone-else", "title": "Theirs"},
        }
        self.sources: dict[str, dict[str, Any]] = {}
        self.chunks: dict[str, list[tuple[Chunk, list[float]]]] = {}
        self.outputs: dict[str, dict[str, Any]] = {}
        self.conversations: dict[str, dict[str, Any]] = {}
        self._add_conversation(NOTEBOOK, "Chat 1", CONVERSATION)

    def _add_conversation(
        self, notebook_id: str, title: str, conversation_id: str | None = None
    ) -> ConversationRow:
        row = {
            "id": conversation_id or str(uuid.uuid4()),
            "notebook_id": notebook_id,
            "title": title,
            "created_at": f"2026-01-01T00:{len(self.conversations) % 60:02d}:00Z",
        }
        self.conversations[row["id"]] = row
        return self._conversation(row)

    def _conversation(self, row: dict[str, Any]) -> ConversationRow:
        return ConversationRow(owner=self.notebooks[row["notebook_id"]]["owner"], **row)

    # notebooks
    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None:
        return self.notebooks.get(notebook_id)

    # conversations and messages
    def list_conversations(self, notebook_id: str) -> list[ConversationRow]:
        return [
            self._conversation(c)
            for c in self.conversations.values()
            if c["notebook_id"] == notebook_id
        ]

    def get_conversation(self, conversation_id: str) -> ConversationRow | None:
        row = self.conversations.get(conversation_id)
        return self._conversation(row) if row else None

    def create_conversation(self, notebook_id: str, title: str) -> ConversationRow:
        return self._add_conversation(notebook_id, title)

    def delete_conversation(self, conversation_id: str) -> None:
        del self.conversations[conversation_id]
        self.messages = [m for m in self.messages if m["conversation_id"] != conversation_id]

    def list_messages(self, conversation_id: str, last: int | None = None) -> list[Message]:
        rows = [m for m in self.messages if m["conversation_id"] == conversation_id]
        return [self._message(m) for m in (rows[-last:] if last else rows)]

    def insert_message(self, notebook_id, conversation_id, role, content, citations) -> Message:
        row = {
            "id": str(uuid.uuid4()),
            "notebook_id": notebook_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "citations": citations,
            "created_at": f"2026-01-01T00:00:{len(self.messages) % 60:02d}Z",
        }
        self.messages.append(row)
        return self._message(row)

    @staticmethod
    def _message(row: dict[str, Any]) -> Message:
        return Message.model_validate({**row, "citations": row["citations"] or []})

    # outputs
    def create_output(self, notebook_id: str, kind: OutputKind, status: OutputStatus) -> OutputRow:
        row = {
            "id": str(uuid.uuid4()),
            "notebook_id": notebook_id,
            "kind": kind,
            "title": "",
            "content": None,
            "status": status,
            "error": None,
            "share_token": None,
            "source_id": None,
            "attempts": 0,
            "claimed_by": None,
            "created_at": (datetime.now(UTC) + timedelta(seconds=len(self.outputs))).isoformat(),
        }
        self.outputs[row["id"]] = row
        return self._output_row(row)

    def get_output(self, output_id: str) -> OutputRow | None:
        row = self.outputs.get(output_id)
        return self._output_row(row) if row else None

    def get_shared_output(self, share_token: str) -> OutputRow | None:
        for row in self.outputs.values():
            if row["share_token"] == share_token:
                return self._output_row(row)
        return None

    def list_outputs(self, notebook_id: str) -> list[OutputRow]:
        return [
            self._output_row(r) for r in self.outputs.values() if r["notebook_id"] == notebook_id
        ]

    def update_output(self, output_id: str, **fields: Any) -> None:
        self.outputs[output_id].update(fields)

    def delete_output(self, output_id: str) -> None:
        del self.outputs[output_id]

    def claim_output(self, worker_id: str, stale_after_s: int) -> OutputRow | None:
        for row in sorted(self.outputs.values(), key=lambda r: r["created_at"]):
            if row["status"] not in ("waiting", "processing") or row["claimed_by"] is not None:
                continue
            if any(
                s["status"] == "processing" and s["kind"] != "generated"
                for s in self.sources.values()
                if s["notebook_id"] == row["notebook_id"]
            ):
                continue
            row["claimed_by"] = worker_id
            row["attempts"] += 1
            return self._output_row(row)
        return None

    def release_output(self, output_id: str, error: str | None = None) -> None:
        self.outputs[output_id].update(claimed_by=None, error=error)

    def _output_row(self, row: dict[str, Any]) -> OutputRow:
        fields = {k: v for k, v in row.items() if k != "claimed_by"}
        return OutputRow(owner=self.notebooks[row["notebook_id"]]["owner"], **fields)

    # sources and chunks
    def add_source(
        self, notebook_id: str, name: str, status: str = "ready", summary: str = "", kind="pdf"
    ) -> str:
        source_id = str(uuid.uuid4())
        self.sources[source_id] = {
            "id": source_id,
            "notebook_id": notebook_id,
            "name": name,
            "kind": kind,
            "status": status,
            "summary": summary,
            "error": None,
        }
        return source_id

    def source_states(self, notebook_id: str) -> list[SourceState]:
        return [
            SourceState(s["id"], s["kind"], s["status"])
            for s in self.sources.values()
            if s["notebook_id"] == notebook_id
        ]

    def source_summaries(self, notebook_id: str) -> list[SourceSummary]:
        return [
            SourceSummary(s["id"], s["name"], s["kind"], s["summary"])
            for s in self.sources.values()
            if s["notebook_id"] == notebook_id
            and s["status"] == "ready"
            and s["kind"] != "generated"
        ]

    def create_generated_source(self, notebook_id: str, name: str, summary: str) -> str:
        return self.add_source(notebook_id, name, "processing", summary, kind="generated")

    def insert_chunks(self, source_id, notebook_id, chunks, embeddings) -> None:
        assert len(chunks) == len(embeddings)
        self.chunks[source_id] = list(zip(chunks, embeddings, strict=True))

    def set_source_status(self, source_id: str, status: str, error: str | None = None) -> None:
        self.sources[source_id].update(status=status, error=error)

    def delete_source(self, source_id: str) -> None:
        self.sources.pop(source_id)
        self.chunks.pop(source_id, None)

    # credit
    def has_credit(self, user_id: str) -> bool:
        return user_id in self.admins or self.balance > 0

    def is_admin(self, user_id: str) -> bool:
        return user_id in self.admins

    def admin_stats(self, stale_after_s: int) -> dict[str, Any]:
        rows = list(self.outputs.values())
        now = datetime.now(UTC)

        def live(r: dict[str, Any]) -> bool:
            # the fake claims without a timestamp: a claim is live until released
            return r["claimed_by"] is not None

        processing = [r for r in rows if r["status"] == "processing"]
        day_ago = now.timestamp() - 86400
        return {
            "notebooks": {"total": len(self.notebooks)},
            "messages": {
                "total": len(self.messages),
                "last_24h": sum(
                    1
                    for m in self.messages
                    if datetime.fromisoformat(m["created_at"]).timestamp() > day_ago
                ),
            },
            "outputs": [(r["kind"], r["status"], 1) for r in rows],
            "jobs": {
                "pending": sum(1 for r in rows if r["status"] == "waiting")
                + sum(1 for r in processing if not live(r)),
                "running": sum(1 for r in processing if live(r)),
                "failed": sum(1 for r in rows if r["status"] == "failed"),
            },
            "shared": {"outputs": sum(1 for r in rows if r.get("share_token"))},
        }

    def record_usage(self, user_id: str, notebook_id: str | None, usage: Usage) -> None:
        self.usage.append((user_id, notebook_id, usage))


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, Any]] = []

    def search(
        self, notebook_id, embedding, k, floor, source_id=None, include_generated=False
    ) -> list[RetrievedChunk]:
        self.calls.append(
            {
                "notebook_id": notebook_id,
                "k": k,
                "floor": floor,
                "source_id": source_id,
                "include_generated": include_generated,
            }
        )
        hits = [c for c in self.chunks if c.similarity >= floor]
        if source_id is not None:
            hits = [c for c in hits if c.source_id == source_id]
        elif not include_generated:
            hits = [c for c in hits if c.source_kind != "generated"]
        return hits[:k]


class FakeEmbedder:
    model = "test-embedding"
    dimension = 3

    def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors = [[0.1, 0.2, float(len(t))] for t in texts]
        return EmbeddingResult(vectors, Usage("embedding", "test-embedding", 7 * len(texts), 0))


class FakeLLM:
    """Replies with the scripted texts in order; the last one repeats."""

    model = "test-llm"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies) or [""]
        self.calls: list[tuple[str, str]] = []

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        *,
        thinking: bool | None = None,
    ) -> CompletionResult:
        assert thinking is None  # answers and generators never ask for reasoning
        self.calls.append((system, user))
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return CompletionResult(reply, Usage("llm", "test-llm", 50, 20))


class FakeTTS:
    """Returns one fake MP3 frame per segment."""

    model = "test-tts"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.inputs: list[str] = []

    def synthesize(self, text: str) -> bytes:
        if self.fail:
            raise ProviderError("speech request failed: boom")
        self.inputs.append(text)
        return b"\xff\xf3" + text[:4].encode()


class FakeObjects:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key][0]

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.objects.pop(key, None)

    def presigned_get(self, key: str, expires_s: int = 3600) -> str:
        return f"https://objects.test/{key}?expires={expires_s}"


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(
        {**BASE_ENV, "DEMO_TOKEN": DEMO_TOKEN, "RETRIEVAL_K": "3", "SIMILARITY_FLOOR": "0.5"}
    )


def make_client(
    settings: Settings,
    store: FakeStore,
    retriever: FakeRetriever,
    llm: FakeLLM,
    tts: FakeTTS | None = None,
    objects: FakeObjects | None = None,
) -> TestClient:
    generators = registry(tts_available=tts is not None)
    outputs = OutputService(
        store,
        retriever,
        FakeEmbedder(),
        llm,
        generators,
        settings.retrieval_k,
        settings.similarity_floor,
        tts=tts,
        objects=objects,
    )
    app = create_app(
        settings=settings,
        store=store,
        retriever=retriever,
        embedder=FakeEmbedder(),
        llm=llm,
        generators=generators,
        output_service=outputs,
        rate_limit_store=MemoryRateLimitStore(),
    )
    client = TestClient(app, raise_server_exceptions=False)
    client.worker = Worker(store, outputs, worker_id="test-worker")  # type: ignore[attr-defined]
    return client
