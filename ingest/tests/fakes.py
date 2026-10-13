"""In-memory stand-ins for the external systems. Tests never touch a
database, a bucket or an inference API."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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

from lasteverlm_ingest.repository import (
    KINDS,
    AdminStats,
    DailyStats,
    LibraryEntry,
    LibrarySource,
    NewLibrarySource,
    NotebookUse,
    StoredSource,
    TrashEntry,
)


class InMemoryRepository:
    """The library model in dicts: `library` (library sources), `links`
    (sources: link id -> notebook, library id, created), `chunks` per
    library source."""

    def __init__(self, balance: int = 1000, prices: ModelPrices | None = None) -> None:
        self.prices = (
            prices
            if prices is not None
            else parse_model_prices(
                '{"fake-embed": {"in": 2000, "out": 0}, "fake-llm": {"in": 30, "out": 150}}'
            )
        )
        self.notebooks: dict[UUID, tuple[UUID, Notebook]] = {}
        self.library: dict[UUID, LibrarySource] = {}
        self.links: dict[UUID, tuple[UUID, UUID, datetime]] = {}
        self.chunks: dict[UUID, list[tuple[Chunk, list[float]]]] = {}
        self.usage: list[UsageRecord] = []
        self.credits: dict[UUID, int] = {}
        self.claimed: dict[UUID, str] = {}
        self.default_balance = balance
        self.admins: set[UUID] = set()
        # account's users.preferences -> 'trash_days'; missing means 14
        self.trash_days: dict[UUID, int] = {}
        self.seeded: set[UUID] = set()

    # -- test helpers ----------------------------------------------------------

    def add_source(
        self,
        notebook_id: UUID,
        name: str,
        kind: str,
        storage_path: str | None,
        size_bytes: int | None = None,
        dedupe_key: str | None = None,
    ) -> StoredSource:
        """A library source and its link in one step, as a test fixture."""
        owner = self.notebooks[notebook_id][0]
        lib = LibrarySource(
            id=uuid4(),
            owner=owner,
            name=name,
            kind=kind,
            dedupe_key=dedupe_key,
            size_bytes=size_bytes,
            storage_path=storage_path,
            status="processing",
            created_at=datetime.now(UTC),
        )
        self.library[lib.id] = lib
        return self.link_source(notebook_id, lib.id)[0]

    def pending(self) -> int:
        return sum(
            1
            for lib in self.library.values()
            if lib.status == "processing" and self._active(lib) and lib.id not in self.claimed
        )

    @staticmethod
    def _listed(lib: LibrarySource) -> bool:
        return lib.kind != "generated"

    def _active(self, lib: LibrarySource) -> bool:
        return self._listed(lib) and lib.deleted_at is None

    def _trashed(self, lib: LibrarySource) -> bool:
        return self._listed(lib) and lib.deleted_at is not None

    def _purge_at(self, lib: LibrarySource) -> datetime:
        assert lib.deleted_at is not None
        return lib.deleted_at + timedelta(days=max(0, self.trash_days.get(lib.owner, 14)))

    # -- notebooks -------------------------------------------------------------

    def list_notebooks(self, owner: UUID) -> list[Notebook]:
        return [nb for o, nb in self.notebooks.values() if o == owner]

    def create_notebook(self, owner: UUID, title: str) -> Notebook:
        nb = Notebook(id=uuid4(), title=title, created_at=datetime.now(UTC))
        self.notebooks[nb.id] = (owner, nb)
        return nb

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> Notebook | None:
        entry = self.notebooks.get(notebook_id)
        return entry[1] if entry and entry[0] == owner else None

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> None:
        if self.get_notebook(owner, notebook_id) is None:
            return
        for link_id, (nb, lib_id, _) in list(self.links.items()):
            if nb == notebook_id:
                if self.library[lib_id].kind == "generated":
                    self._delete_library(lib_id)
                self.links.pop(link_id, None)
        del self.notebooks[notebook_id]

    # -- sources ---------------------------------------------------------------

    def _stored(self, link_id: UUID) -> StoredSource:
        nb, lib_id, created = self.links[link_id]
        lib = self.library[lib_id]
        return StoredSource(
            id=link_id,
            notebook_id=nb,
            name=lib.name,
            kind=lib.kind,
            status=lib.status,
            error=lib.error,
            created_at=created,
            library_id=lib.id,
            owner=lib.owner,
            storage_path=lib.storage_path,
            summary=lib.summary,
            attempts=lib.attempts,
            size_bytes=lib.size_bytes,
            capture=lib.capture,
            demo=lib.demo,
        )

    def list_sources(self, notebook_id: UUID) -> list[StoredSource]:
        return [self._stored(i) for i, (nb, _, _) in self.links.items() if nb == notebook_id]

    def get_source(self, source_id: UUID) -> StoredSource | None:
        return self._stored(source_id) if source_id in self.links else None

    def link_source(self, notebook_id: UUID, library_id: UUID) -> tuple[StoredSource, bool]:
        for link_id, (nb, lib, _) in self.links.items():
            if nb == notebook_id and lib == library_id:
                return self._stored(link_id), False
        link_id = uuid4()
        self.links[link_id] = (notebook_id, library_id, datetime.now(UTC))
        return self._stored(link_id), True

    def detach_source(self, source_id: UUID) -> None:
        if source_id not in self.links:
            return
        _, lib_id, _ = self.links.pop(source_id)
        if self.library[lib_id].kind == "generated":
            self._delete_library(lib_id)

    # -- the library -------------------------------------------------------------

    def find_library_source(self, owner: UUID, dedupe_key: str) -> LibrarySource | None:
        for lib in self.library.values():
            if lib.owner == owner and lib.dedupe_key == dedupe_key and self._listed(lib):
                return lib
        return None

    def create_library_source(self, new: NewLibrarySource) -> LibrarySource:
        found = self.find_library_source(new.owner, new.dedupe_key)
        if found is not None:
            return found
        lib = LibrarySource(**new.model_dump(), status="processing", created_at=datetime.now(UTC))
        self.library[lib.id] = lib
        return lib

    def claim_seed(self, owner: UUID) -> bool:
        if owner in self.seeded:
            return False
        self.seeded.add(owner)
        return not any(lib.owner == owner and self._listed(lib) for lib in self.library.values())

    def retry_library_source(self, library_id: UUID) -> None:
        lib = self.library[library_id]
        if lib.status == "failed":
            self.library[library_id] = lib.model_copy(
                update={"status": "processing", "error": None, "attempts": 0}
            )
            self.claimed.pop(library_id, None)

    def _entry(self, lib: LibrarySource) -> LibraryEntry:
        uses = sorted(
            (created, link_id, nb)
            for link_id, (nb, lib_id, created) in self.links.items()
            if lib_id == lib.id
        )
        return LibraryEntry(
            id=lib.id,
            name=lib.name,
            kind=lib.kind,
            status=lib.status,
            error=lib.error,
            size_bytes=lib.size_bytes,
            url=lib.url,
            created_at=lib.created_at,
            capture=lib.capture,
            demo=lib.demo,
            notebooks=[
                NotebookUse(id=nb, title=self.notebooks[nb][1].title, source_id=link_id)
                for _, link_id, nb in uses
            ],
        )

    def list_library(self, owner: UUID) -> list[LibraryEntry]:
        libs = [lib for lib in self.library.values() if lib.owner == owner and self._active(lib)]
        return [self._entry(lib) for lib in sorted(libs, key=lambda x: x.created_at, reverse=True)]

    def get_library_entry(self, owner: UUID, library_id: UUID) -> LibraryEntry | None:
        lib = self.library.get(library_id)
        if lib is None or lib.owner != owner or not self._active(lib):
            return None
        return self._entry(lib)

    def trash_library_source(self, owner: UUID, library_id: UUID) -> bool:
        lib = self.library.get(library_id)
        if lib is None or lib.owner != owner or not self._active(lib):
            return False
        self.library[library_id] = lib.model_copy(update={"deleted_at": datetime.now(UTC)})
        for link_id, (_, lib_id, _) in list(self.links.items()):
            if lib_id == library_id:
                del self.links[link_id]
        return True

    def list_trash(self, owner: UUID) -> list[TrashEntry]:
        libs = [lib for lib in self.library.values() if lib.owner == owner and self._trashed(lib)]
        return [
            TrashEntry(
                **lib.model_dump(include=set(TrashEntry.model_fields) - {"purge_at"}),
                purge_at=self._purge_at(lib),
            )
            for lib in sorted(libs, key=lambda x: x.deleted_at or x.created_at, reverse=True)
        ]

    def restore_library_source(self, owner: UUID, library_id: UUID) -> bool:
        lib = self.library.get(library_id)
        if lib is None or lib.owner != owner or not self._trashed(lib):
            return False
        self.library[library_id] = lib.model_copy(update={"deleted_at": None})
        return True

    def purge_library_source(self, owner: UUID, library_id: UUID) -> tuple[bool, str | None]:
        lib = self.library.get(library_id)
        if lib is None or lib.owner != owner or not self._trashed(lib):
            return False, None
        self._delete_library(library_id)
        return True, lib.storage_path

    def purge_expired(self) -> list[str]:
        now = datetime.now(UTC)
        gone = [
            lib
            for lib in self.library.values()
            if self._trashed(lib) and self._purge_at(lib) <= now
        ]
        for lib in gone:
            self._delete_library(lib.id)
        return [lib.storage_path for lib in gone if lib.storage_path]

    def _delete_library(self, library_id: UUID) -> None:
        self.library.pop(library_id, None)
        self.chunks.pop(library_id, None)
        for link_id, (_, lib_id, _) in list(self.links.items()):
            if lib_id == library_id:
                del self.links[link_id]

    # -- the worker --------------------------------------------------------------

    def get_library_source(self, library_id: UUID) -> LibrarySource | None:
        return self.library.get(library_id)

    def first_notebook(self, library_id: UUID) -> UUID | None:
        uses = sorted((c, nb) for nb, lib, c in self.links.values() if lib == library_id)
        return uses[0][1] if uses else None

    def set_library_status(self, library_id: UUID, status: str, error: str | None = None) -> None:
        self.library[library_id] = self.library[library_id].model_copy(
            update={"status": status, "error": error}
        )

    def claim_library_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        for lib in sorted(self.library.values(), key=lambda s: s.created_at):
            if (
                lib.status == "processing"
                and lib.kind != "generated"
                and lib.deleted_at is None
                and lib.id not in self.claimed
            ):
                self.claimed[lib.id] = worker_id
                self.library[lib.id] = lib.model_copy(update={"attempts": lib.attempts + 1})
                return lib.id
        return None

    def set_library_summary(self, library_id: UUID, summary: str) -> None:
        self.library[library_id] = self.library[library_id].model_copy(update={"summary": summary})

    def replace_chunks(
        self, library_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        self.chunks[library_id] = list(zip(chunks, vectors, strict=True))

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

    def has_credit(self, user_id: UUID) -> bool:
        return self.is_admin(user_id) or self.balance_cents(user_id) > 0

    def is_admin(self, user_id: UUID) -> bool:
        return user_id in self.admins

    def admin_stats(self, stale_after_seconds: int) -> AdminStats:
        listed = [lib for lib in self.library.values() if self._listed(lib)]
        counts = {status: 0 for status in ("processing", "ready", "failed")}
        for lib in listed:
            counts[lib.status] += 1
        running = sum(1 for lib in listed if lib.status == "processing" and lib.id in self.claimed)
        return AdminStats(
            sources=counts,
            jobs={
                "pending": counts["processing"] - running,
                "running": running,
                "failed": counts["failed"],
            },
            chunks=sum(len(self.chunks.get(lib.id, [])) for lib in listed),
            source_bytes=sum(lib.size_bytes or 0 for lib in listed),
        )

    def admin_daily(self, days: int) -> list[DailyStats]:
        today = datetime.now(UTC).date()
        out = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            libs = [
                lib
                for lib in self.library.values()
                if self._listed(lib) and lib.created_at.astimezone(UTC).date() == day
            ]
            out.append(
                DailyStats(
                    day=day,
                    sources_created=len(libs),
                    by_kind={k: sum(1 for lib in libs if lib.kind == k) for k in KINDS},
                    failed=sum(1 for lib in libs if lib.status == "failed"),
                )
            )
        return out


class FakeChat:
    """The OpenAI client's chat.completions as far as the vision reader uses
    it: one fixed answer (or error) per call, every request recorded."""

    def __init__(self, answer: str = "Umsatz 4,2 Mio\n\nA bar chart.", error=None) -> None:
        self.answer, self.error = answer, error
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=self.answer), finish_reason="stop")
            ],
            usage=SimpleNamespace(prompt_tokens=202, completion_tokens=40),
        )


class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.types: dict[str, str] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data
        self.types[key] = content_type

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.objects.pop(key, None)

    def presigned_get(self, key: str, expires_s: int = 3600) -> str:
        return f"https://storage.test/{key}?expires={expires_s}"


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
