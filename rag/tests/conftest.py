from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import (
    DEMO_USER_ID,
    CompletionResult,
    DecisionResult,
    EmbeddingResult,
    MemoryRateLimitStore,
    Message,
    OutputKind,
    OutputStatus,
    PricingRules,
    ProviderError,
    Role,
    SpeechResult,
    StorageError,
    Usage,
)
from lasteverlm_core.chunking import Chunk

from lasteverlm_rag.config import Settings
from lasteverlm_rag.estimate import Models, output_estimator
from lasteverlm_rag.main import create_app
from lasteverlm_rag.models import (
    Booking,
    ConversationRow,
    NotebookDocument,
    OutputRow,
    RetrievedChunk,
    SourceState,
    SourceSummary,
)
from lasteverlm_rag.outputs import registry
from lasteverlm_rag.service import OutputService
from lasteverlm_rag.starter import OutputCopy
from lasteverlm_rag.voice_samples import VoiceSamples
from lasteverlm_rag.worker import Worker

DEMO_TOKEN = "demo-secret"
OWNER = str(DEMO_USER_ID)
# what a report is stored with when the client sends no style or length
REPORT_DEFAULTS = {"report_style": "briefing", "length": "medium"}
NOTEBOOK = str(uuid.uuid4())
OTHER_NOTEBOOK = str(uuid.uuid4())
CONVERSATION = str(uuid.uuid4())
AUTH = {"Authorization": f"Bearer {DEMO_TOKEN}"}
PRICES = (
    '{"test-llm": {"in": 100, "out": 300}, "test-embedding": {"in": 10, "out": 0}, '
    '"test-decision": {"in": 10, "out": 0}, "test-judge-low": {"in": 10, "out": 30}, '
    '"test-judge-medium": {"in": 20, "out": 60}, "test-judge-high": {"in": 80, "out": 300}}'
)
JUDGE_MODELS = '{"low": "test-judge-low", "medium": "test-judge-medium", "high": "test-judge-high"}'

BASE_ENV = {
    "DATABASE_URL": "postgresql://test",
    "INFERENCE_BASE_URL": "https://inference.example/v1",
    "INFERENCE_API_KEY": "key",
    "LLM_MODEL": "test-llm",
    "EMBEDDING_MODEL": "test-embedding",
    "DECISION_MODEL": "test-decision",
    "MODEL_PRICES": PRICES,
    "JUDGE_MODELS": JUDGE_MODELS,
    # tests do not wait for sources being read: the waiting is tested with a clock
    "ANSWER_READ_WAIT_SECONDS": "0",
}


_NS = uuid.UUID("12345678-1234-5678-1234-567812345678")


def source_uuid(i: int) -> str:
    return str(uuid.uuid5(_NS, f"source-{i}"))


def chunk_uuid(i: int) -> str:
    return str(uuid.uuid5(_NS, f"chunk-{i}"))


SOURCE_1, CHUNK_1 = source_uuid(1), chunk_uuid(1)


def chunk(
    i: int,
    text: str,
    page: int | None = None,
    similarity: float = 0.9,
    source_kind: str = "pdf",
    chunk_index: int | None = None,
    chunk_count: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_uuid(i),
        source_id=source_uuid(i),
        source_name=f"doc{i}.pdf",
        source_kind=source_kind,  # type: ignore[arg-type]
        page=page,
        text=text,
        similarity=similarity,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
    )


class FakeStore:
    """In-memory stand-in for PostgresStore with the same contract."""

    def __init__(
        self,
        balance: int = 100,
        admins: set[str] | None = None,
        viewers: set[str] | None = None,
    ) -> None:
        self.balance = balance
        self.ingest_held = 0  # ingest's funded reads not finished, in cents
        self.reserved: dict[str, float] = {}  # outputs.reserved_cents by id
        self.emails: dict[str, str] = {}  # account's users.email by id
        self.admins = admins or set()
        self.viewers = viewers or set()
        self.messages: list[dict[str, Any]] = []
        self.bookings: list[tuple[str, uuid.UUID]] = []
        self.copies: dict[str, dict[str, Any]] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self.preferences: dict[str, dict[str, Any]] = {}
        self.touches: list[str] = []
        self.phases: dict[str, list[dict[str, Any]]] = {}
        self.beats: list[str] = []
        self.suggestions: dict[str, tuple[str, list[str]]] = {}
        # a rate of 1: charges equal costs unless a test sets margins or a rate
        self.rules = PricingRules.parse({"usd_per_eur": 1})
        self.usage: list[tuple[str, str | None, Usage]] = []
        self.notebooks = {
            NOTEBOOK: {"id": NOTEBOOK, "owner": OWNER, "title": "My notebook"},
            OTHER_NOTEBOOK: {"id": OTHER_NOTEBOOK, "owner": "someone-else", "title": "Theirs"},
        }
        self.sources: dict[str, dict[str, Any]] = {}
        # generated sources out of every notebook (their output is trashed, or
        # its notebook was deleted): kept with their chunks, never searched
        self.trashed_sources: dict[str, dict[str, Any]] = {}
        self.trash_days = 14
        self.chunks: dict[str, list[tuple[Chunk, list[float]]]] = {}
        self.outputs: dict[str, dict[str, Any]] = {}
        self.conversations: dict[str, dict[str, Any]] = {}
        self.daily: dict[str, tuple[int, dict[str, int]]] = {}
        self.chunk_rows: dict[str, tuple[str, dict[str, Any]]] = {}
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

    def rename_conversation(self, conversation_id: str, title: str) -> ConversationRow:
        self.conversations[conversation_id]["title"] = title
        return self._conversation(self.conversations[conversation_id])

    def delete_conversation(self, conversation_id: str) -> None:
        del self.conversations[conversation_id]
        self.messages = [m for m in self.messages if m["conversation_id"] != conversation_id]

    def list_messages(self, conversation_id: str, last: int | None = None) -> list[Message]:
        rows = [m for m in self.messages if m["conversation_id"] == conversation_id]
        return [self._message(m) for m in (rows[-last:] if last else rows)]

    def insert_message(
        self,
        notebook_id,
        conversation_id,
        role,
        content,
        citations,
        support=None,
        suggestions=None,
        plan=None,
    ) -> Message:
        row = {
            "id": str(uuid.uuid4()),
            "notebook_id": notebook_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "citations": citations,
            "support": support,
            "suggestions": suggestions or [],
            "plan": plan,
            "feedback": None,
            "created_at": f"2026-01-01T00:00:{len(self.messages) % 60:02d}Z",
        }
        self.messages.append(row)
        return self._message(row)

    def get_message(self, message_id: str) -> tuple[str, Message] | None:
        for row in self.messages:
            if row["id"] == message_id:
                return row["notebook_id"], self._message(row)
        return None

    def update_message_support(self, message_id: str, support: dict[str, Any]) -> None:
        next(m for m in self.messages if m["id"] == message_id)["support"] = support

    def set_message_feedback(self, message_id: str, feedback: dict[str, Any]) -> None:
        next(m for m in self.messages if m["id"] == message_id)["feedback"] = feedback

    def feedback_overview(self, days: int, latest: int) -> dict[str, Any]:
        down = [m for m in self.messages if (m.get("feedback") or {}).get("rating") == "down"]
        return {"days": [], "latest_down": [{"message_id": m["id"]} for m in down][:latest]}

    def notebook_suggestions(self, notebook_id: str) -> tuple[str, list[str]] | None:
        return self.suggestions.get(notebook_id)

    def save_notebook_suggestions(
        self, notebook_id: str, sources_key: str, suggestions: list[str]
    ) -> None:
        self.suggestions[notebook_id] = (sources_key, suggestions)

    @staticmethod
    def _message(row: dict[str, Any]) -> Message:
        support = row.get("support") or {}
        fields = {k: v for k, v in row.items() if k != "support"}
        return Message.model_validate(
            {
                **fields,
                "citations": row["citations"] or [],
                "units": support.get("units"),
                "check": support.get("check"),
                "web_pages": support.get("web_pages") or [],
            }
        )

    # outputs
    def create_output(
        self,
        notebook_id: str,
        kind: OutputKind,
        status: OutputStatus,
        options: dict[str, Any] | None = None,
        booking_id: str | None = None,
        reserved_cents: float = 0.0,
    ) -> OutputRow:
        notebook = self.notebooks[notebook_id]
        row = {
            "id": str(uuid.uuid4()),
            "notebook_id": notebook_id,
            "owner": notebook["owner"],
            "origin_title": notebook["title"],
            "deleted_at": None,
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
            "options": options or {},
            "booking_id": booking_id,
        }
        self.outputs[row["id"]] = row
        self.reserved[row["id"]] = reserved_cents
        return self._output_row(row)

    def touch_output(self, output_id: str, phase: dict[str, Any] | None = None) -> None:
        self.touches.append(output_id)
        if phase is None or phase == self.outputs[output_id].get("phase"):
            self.beats.append(output_id)  # a plain beat: the step did not change
        if phase is not None:
            self.outputs[output_id]["phase"] = phase
            self.phases.setdefault(output_id, []).append(dict(phase))

    def charged(self, action_id: str) -> bool:
        return any(str(i) == str(action_id) for _, i in self.bookings)

    def waiting_outputs(self, older_than_s: int) -> list[OutputRow]:
        cutoff = datetime.now(UTC) - timedelta(seconds=older_than_s)
        return [
            self._output_row(r)
            for r in self.outputs.values()
            if r["status"] == "waiting"
            and r["deleted_at"] is None
            and datetime.fromisoformat(r["created_at"]) < cutoff
        ]

    def get_output(self, output_id: str) -> OutputRow | None:
        row = self.outputs.get(output_id)
        return self._output_row(row) if row else None

    def get_shared_output(self, share_token: str) -> OutputRow | None:
        for row in self.outputs.values():
            if row["share_token"] == share_token:
                return self._output_row(row)
        return None

    def get_shared_notebook(self, share_token: str) -> dict[str, Any] | None:
        for notebook in self.notebooks.values():
            if notebook.get("share_token") == share_token:
                return {"id": notebook["id"], "title": notebook["title"]}
        return None

    def rename_output(self, output_id: str, title: str) -> None:
        row = self.outputs[output_id]
        row["title"] = title
        if row["source_id"] in self.sources:
            self.sources[row["source_id"]]["name"] = title

    def list_outputs(self, notebook_id: str) -> list[OutputRow]:
        return [
            self._output_row(r)
            for r in self.outputs.values()
            if r["notebook_id"] == notebook_id and r["deleted_at"] is None
        ]

    def list_library_outputs(self, owner: str, kind: str | None, trash: bool) -> list[OutputRow]:
        rows = [
            r
            for r in self.outputs.values()
            if r["owner"] == owner
            and (kind is None or r["kind"] == kind)
            and (r["deleted_at"] is not None) == trash
        ]
        rows.sort(key=lambda r: r["deleted_at"] or r["created_at"], reverse=True)
        return [self._output_row(r) for r in rows]

    def trash_outputs(self, output_ids: list[str]) -> None:
        for output_id in output_ids:
            row = self.outputs[output_id]
            source = self.sources.pop(row["source_id"], None) if row["source_id"] else None
            if source is not None:
                self.trashed_sources[source["id"]] = source
            if row["deleted_at"] is None:
                row["deleted_at"] = datetime.now(UTC).isoformat()

    def restore_output(self, output_id: str) -> None:
        row = self.outputs[output_id]
        source = self.trashed_sources.pop(row["source_id"], None) if row["source_id"] else None
        if source is not None and row["notebook_id"] in self.notebooks:
            self.sources[source["id"]] = source
        row["deleted_at"] = None

    def expired_outputs(self) -> list[OutputRow]:
        cutoff = datetime.now(UTC) - timedelta(days=self.trash_days)
        return [
            self._output_row(r)
            for r in self.outputs.values()
            if r["deleted_at"] is not None and datetime.fromisoformat(r["deleted_at"]) <= cutoff
        ]

    def delete_notebook(self, notebook_id: str) -> None:
        """ingest's notebook delete as rag sees it: links go, outputs keep
        their rows with the origin set to null."""
        del self.notebooks[notebook_id]
        for source_id, s in list(self.sources.items()):
            if s["notebook_id"] == notebook_id:
                if s["kind"] == "generated":
                    self.trashed_sources[source_id] = s
                del self.sources[source_id]
        for row in self.outputs.values():
            if row["notebook_id"] == notebook_id:
                row["notebook_id"] = None

    def update_output(self, output_id: str, **fields: Any) -> None:
        if fields.get("status") in ("ready", "failed"):
            fields["finished_at"] = datetime.now(UTC).isoformat()
        self.outputs[output_id].update(fields)

    def add_attempt(self, output_id: str, record: dict[str, Any]) -> None:
        log = self.outputs[output_id].setdefault("attempt_log", [])
        log.append(record)

    def find_outputs(self, id_prefix: str, limit: int) -> list[tuple[OutputRow, str]]:
        found = [r for r in self.outputs.values() if r["id"].replace("-", "").startswith(id_prefix)]
        found.sort(key=lambda r: r["created_at"], reverse=True)
        return [(self._output_row(r), self.emails.get(r["owner"], "")) for r in found[:limit]]

    def delete_output(self, output_id: str) -> None:
        del self.outputs[output_id]

    def audio_outputs(self, output_ids: list[str] | None) -> list[OutputRow]:
        return [
            self._output_row(r)
            for r in self.outputs.values()
            if r["kind"] == "audio"
            and r["status"] == "ready"
            and "key" in (r["content"] or {})
            and (output_ids is None or r["id"] in output_ids)
        ]

    def claim_output(self, worker_id: str, stale_after_s: int) -> OutputRow | None:
        for row in sorted(self.outputs.values(), key=lambda r: r["created_at"]):
            if row["status"] not in ("waiting", "processing") or row["claimed_by"] is not None:
                continue
            if row["deleted_at"] is not None:
                continue
            selected = row["options"].get("sources")
            if any(
                s["status"] == "processing" and s["kind"] != "generated"
                for s in self.sources.values()
                if s["notebook_id"] == row["notebook_id"]
                and (selected is None or s["id"] in selected)
            ):
                continue
            row["claimed_by"] = worker_id
            row["attempts"] += 1
            return self._output_row(row)
        return None

    def release_output(self, output_id: str, error: str | None = None) -> None:
        self.outputs[output_id].update(claimed_by=None, error=error)

    def _output_row(self, row: dict[str, Any]) -> OutputRow:
        fields = {k: v for k, v in row.items() if k not in ("claimed_by", "copied_from")}
        deleted = row["deleted_at"]
        purge_at = (
            (datetime.fromisoformat(deleted) + timedelta(days=self.trash_days)).isoformat()
            if deleted
            else None
        )
        return OutputRow(purge_at=purge_at, **fields)

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
            SourceState(
                s["id"],
                s["kind"],
                s["status"],
                s["id"],
                s["name"],
                s.get("error"),
                s.get("read_at"),
            )
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

    def notebook_documents(self, notebook_id: str) -> list[NotebookDocument]:
        output_kinds = {o["source_id"]: o["kind"] for o in self.outputs.values()}
        return [
            NotebookDocument(s["id"], s["name"], s["kind"], output_kinds.get(s["id"]))
            for s in self.sources.values()
            if s["notebook_id"] == notebook_id and s["status"] == "ready"
        ]

    def create_generated_source(self, notebook_id: str, name: str, summary: str) -> str:
        return self.add_source(notebook_id, name, "processing", summary, kind="generated")

    def insert_chunks(self, source_id, chunks, embeddings) -> None:
        assert len(chunks) == len(embeddings)
        self.chunks[source_id] = list(zip(chunks, embeddings, strict=True))

    def set_source_status(self, source_id: str, status: str, error: str | None = None) -> None:
        self.sources[source_id].update(status=status, error=error)

    def delete_source(self, source_id: str) -> None:
        self.sources.pop(source_id, None)
        self.trashed_sources.pop(source_id, None)
        self.chunks.pop(source_id, None)

    # deleting a user
    def _owned_notebooks(self, user_id: str) -> set[str]:
        return {n["id"] for n in self.notebooks.values() if n["owner"] == user_id}

    def user_output_contents(self, user_id: str) -> list[dict[str, Any]]:
        return [
            o["content"]
            for o in self.outputs.values()
            if o["owner"] == user_id and o["content"] is not None
        ]

    def delete_user_data(self, user_id: str) -> None:
        mine = self._owned_notebooks(user_id)
        for o in self.outputs.values():
            if o["owner"] == user_id and o["source_id"]:
                self.delete_source(o["source_id"])
        self.outputs = {k: o for k, o in self.outputs.items() if o["owner"] != user_id}
        self.messages = [m for m in self.messages if m["notebook_id"] not in mine]
        self.conversations = {
            k: c for k, c in self.conversations.items() if c["notebook_id"] not in mine
        }

    # credit
    def has_credit(self, user_id: str) -> bool:
        return self.balance > 0

    def balance_cents(self, user_id: str) -> Decimal:
        return Decimal(self.balance)

    def held_cents(self, user_id: str) -> Decimal:
        outputs = sum(
            Decimal(str(self.reserved.get(o["id"], 0)))
            for o in self.outputs.values()
            if o["owner"] == user_id
            and o["status"] in ("waiting", "processing")
            and o["deleted_at"] is None
        )
        return outputs + Decimal(str(self.ingest_held))

    # starter copies
    def claim_output_copy(self, worker_id: str, stale_after_s: int) -> OutputCopy | None:
        for row in self.copies.values():
            if row["error"] is None and row["claimed_by"] is None:
                row["claimed_by"] = worker_id
                row["attempts"] += 1
                return OutputCopy(
                    row["target_notebook"],
                    row["source_notebook"],
                    row["owner"],
                    row["source_map"],
                    row["chunk_map"],
                    row["attempts"],
                )
        return None

    def end_output_copy(self, target_notebook: str, error: str | None, final: bool) -> None:
        if error is None:
            del self.copies[target_notebook]
        else:
            row = self.copies[target_notebook]
            row["claimed_by"] = None
            row["error"] = error if final else None

    def copied_outputs(self, notebook_id: str) -> set[str]:
        return {
            r["copied_from"]
            for r in self.outputs.values()
            if r["notebook_id"] == notebook_id and r.get("copied_from")
        }

    def copy_output(self, row, output_id, target_notebook, content, options, provenance) -> bool:
        if row.id in self.copied_outputs(target_notebook):
            return False
        notebook = self.notebooks[target_notebook]
        source_id = None
        if row.source_id:
            old = self.sources[row.source_id]
            source_id = self.add_source(
                target_notebook, old["name"], "ready", old["summary"], "generated"
            )
            self.chunks[source_id] = list(self.chunks.get(row.source_id, []))
        self.outputs[output_id] = {
            **self.outputs[row.id],
            "id": output_id,
            "notebook_id": target_notebook,
            "owner": notebook["owner"],
            "origin_title": notebook["title"],
            "content": content,
            "options": options,
            "provenance": provenance,
            "source_id": source_id,
            "share_token": None,
            "deleted_at": None,
            "claimed_by": None,
            "copied_from": row.id,
        }
        return True

    # agent plans
    def create_plan(self, plan: dict[str, Any]) -> None:
        self.plans[plan["id"]] = {
            "question": None,
            "notes": [],
            "sources": [],
            **copy.deepcopy(plan),
            "confirmed_at": None,
            "finished_at": None,
        }

    def user_preference(self, user_id: str, key: str) -> Any:
        return self.preferences.get(user_id, {}).get(key)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        plan = self.plans.get(plan_id)
        return copy.deepcopy(plan) if plan else None

    def save_plan(self, plan_id: str, **fields: Any) -> None:
        public = fields.pop("plan", None)
        self.plans[plan_id].update(copy.deepcopy(fields))
        if public is not None:
            message_id = self.plans[plan_id]["message_id"]
            next(m for m in self.messages if m["id"] == message_id)["plan"] = public

    def running_plans(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(p) for p in self.plans.values() if p["status"] == "running"]

    def pricing_rules(self) -> PricingRules:
        return self.rules

    def admin_role(self, user_id: str) -> Role:
        if user_id in self.admins:
            return "admin"
        return "viewer" if user_id in self.viewers else "user"

    def get_chunk(self, chunk_id: str, user_id: str) -> dict[str, Any] | None:
        owner, row = self.chunk_rows.get(chunk_id, (None, None))
        return row if owner == user_id else None

    def daily_stats(self, days: int) -> list[dict[str, Any]]:
        """Rows as the SQL returns them; tests set ``daily`` to what a day holds."""
        today = datetime.now(UTC).date()
        rows = []
        for i in range(days):
            day = today - timedelta(days=days - 1 - i)
            messages, by_kind = self.daily.get(day.isoformat(), (0, {}))
            rows.append({"day": day, "messages": messages, "by_kind": by_kind})
        return rows

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

    def record_usage(self, booking: Booking, usage: Usage) -> None:
        self.usage.append((booking.user_id, booking.notebook_id, usage))
        self.bookings.append((booking.action, booking.action_id))


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.found = chunks
        self.calls: list[dict[str, Any]] = []

    def search(
        self, notebook_id, embedding, k, floor, source_id=None, generated=False, source_ids=None
    ) -> list[RetrievedChunk]:
        self.calls.append(
            {
                "notebook_id": notebook_id,
                "k": k,
                "floor": floor,
                "source_id": source_id,
                "generated": generated,
                "source_ids": source_ids,
            }
        )
        hits = [c for c in self.found if c.similarity >= floor]
        if source_id is not None:
            hits = [c for c in hits if c.source_id == source_id]
        else:
            hits = [c for c in hits if (c.source_kind == "generated") == generated]
        if source_ids is not None:
            hits = [c for c in hits if c.source_id in source_ids]
        return hits[:k]

    def chunks(self, notebook_id: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
        self.calls.append({"notebook_id": notebook_id, "chunk_ids": chunk_ids})
        return [c for c in self.found if c.chunk_id in chunk_ids]


class FakeEmbedder:
    model = "test-embedding"
    dimension = 3

    def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors = [[0.1, 0.2, float(len(t))] for t in texts]
        return EmbeddingResult(vectors, Usage("embedding", "test-embedding", 7 * len(texts), 0))


class FakeIngest:
    """Ingest's API as the agent uses it: records the calls and the bearer."""

    def __init__(
        self,
        library: list[dict[str, Any]] | None = None,
        fail: bool = False,
        store: FakeStore | None = None,
    ) -> None:
        self.store = store
        self.calls: list[tuple[str, str, Any]] = []
        self.items = library or []
        self.fail = fail

    @property
    def acted(self) -> list[tuple[str, str, Any]]:
        """The calls that change something; estimates left out."""
        return [c for c in self.calls if c[0] != "estimate_sources"]

    def add_url(self, bearer: str, notebook_id: str, url: str) -> dict[str, Any]:
        from lasteverlm_rag.ingest_client import IngestError

        self.calls.append(("add_url", bearer, url))
        if self.fail:
            raise IngestError(400, "url: credentials are not allowed")
        return {"id": str(uuid.uuid4()), "status": "processing"}

    def add_library(self, bearer: str, notebook_id: str, library_ids: list[str]) -> dict[str, Any]:
        self.calls.append(("add_library", bearer, library_ids))
        return {"added": library_ids, "already": []}

    def library(self, bearer: str) -> list[dict[str, Any]]:
        self.calls.append(("library", bearer, None))
        return self.items

    def url_charge_cents(self, bearer: str) -> Decimal:
        return Decimal("0.42")

    def process(self, bearer: str, library_ids: list[str]) -> dict[str, Any]:
        self.calls.append(("process", bearer, library_ids))
        if self.store is not None:  # ingest marks them processing; the worker reads them
            for library_id in library_ids:
                self.store.sources[library_id]["status"] = "processing"
        return {"queued": library_ids, "unchanged": []}

    def refetch(self, bearer: str, link_id: str) -> dict[str, Any]:
        self.calls.append(("refetch", bearer, link_id))
        if self.store is not None:
            self.store.sources[link_id]["status"] = "processing"
        return {"library_id": link_id, "version": 1, "fetched_at": "2026-10-14T00:00:00Z"}

    def estimate_sources(
        self, bearer: str, library_ids: list[str], refetch: list[str]
    ) -> list[dict[str, Any]]:
        self.calls.append(("estimate_sources", bearer, (library_ids, refetch)))
        return [
            {
                "library_id": i,
                "charge_cents_min": "1.5",
                "charge_cents_max": "1.5",
                "basis": "3 pages",
            }
            for i in library_ids
        ] + [
            {
                "library_id": i,
                "charge_cents_min": "0",
                "charge_cents_max": "0.4",
                "basis": "web page",
            }
            for i in refetch
        ]


class FakeLLM:
    """Replies with the scripted texts in order; the last one repeats."""

    model = "test-llm"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies) or [""]
        self.calls: list[tuple[str, str]] = []
        self.budgets: list[int | None] = []

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
        self.budgets.append(max_tokens)
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return CompletionResult(reply, Usage("llm", "test-llm", 50, 20))


class FakeTTS:
    """Returns one fake MP3 frame per segment and bills one second per 15
    characters, rounded up, as the platform's header would report."""

    model = "test-tts"

    def __init__(self, fail: bool = False, silent: bool = False) -> None:
        self.fail = fail
        self.silent = silent  # answers with no audio at all
        self.inputs: list[str] = []
        self.settings: list[tuple[str | None, float | None]] = []

    @staticmethod
    def seconds(text: str) -> int:
        return -(-len(text) // 15)

    def synthesize(
        self, text: str, *, voice: str | None = None, speed: float | None = None
    ) -> SpeechResult:
        if self.fail:
            raise ProviderError("speech request failed: boom")
        self.inputs.append(text)
        self.settings.append((voice, speed))
        usage = Usage("tts", self.model, self.seconds(text), 0)
        if self.silent:
            raise ProviderError("speech model test-tts returned no audio", usage=usage)
        return SpeechResult(b"\xff\xf3" + text[:4].encode(), usage)


class FakeDecision:
    """Answers every question with ``answer`` (raw, the platform's shape) and
    bills 100 input tokens; records each state and question set it got."""

    model = "test-decision"

    def __init__(self, answer: dict[str, Any] | None = None) -> None:
        self.answer = answer or {"type": "noul", "noul": 0.8}
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def decide(self, state: Any, questions: Any) -> DecisionResult:
        self.calls.append((state, dict(questions)))
        return DecisionResult(
            {qid: self.answer for qid in questions}, Usage("decision", self.model, 100, 0)
        )


class FakeObjects:
    def __init__(self, fail_delete: bool = False) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_delete = fail_delete

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        return self.objects[key][0]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, *keys: str) -> None:
        if self.fail_delete:
            raise StorageError("delete failed: AccessDenied at https://s3.internal")
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
    dependency_probe: Any = None,
    decision: FakeDecision | None = None,
    judges: dict[str, Any] | None = None,
    ingest: Any = None,
) -> TestClient:
    generators = registry(tts_available=tts is not None)
    ingest = ingest or FakeIngest(store=store)
    if getattr(ingest, "store", None) is None:
        ingest.store = store
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
        decision=decision,
        judges=judges,
        ingest=ingest,
        # as the API wires it: an output's maximum is what its creation must find covered
        output_max=output_estimator(
            settings.model_prices,
            store.pricing_rules,
            generators,
            Models(
                llm=settings.inference.llm_model,
                embedding=settings.inference.embedding_model,
                decision=settings.inference.decision_model,
                tts=settings.tts_model,
                judges={str(k): v for k, v in settings.inference.judge_models.items()},
            ),
        ),
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
        voice_samples=VoiceSamples(store, tts, objects),
        dependency_probe=dependency_probe,
        ingest=ingest,
    )
    client = TestClient(app, raise_server_exceptions=False)
    client.worker = Worker(  # type: ignore[attr-defined]
        store, outputs, worker_id="test-worker", agent=client.app.state.agent
    )
    return client
