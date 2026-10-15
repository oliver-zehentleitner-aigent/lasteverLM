"""In-memory stand-ins for the external systems. Tests never touch a
database, a bucket or an inference API."""

from __future__ import annotations

import hashlib
import math
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from lasteverlm_core import (
    Chunk,
    CompletionResult,
    EmbeddingResult,
    ModelPrices,
    Notebook,
    Passage,
    PricingRules,
    TranscriptionResult,
    Usage,
    UsageRecord,
    cost_cents,
    is_usage_action,
    parse_model_prices,
)

from lasteverlm_ingest.repository import (
    KINDS,
    MAX_ATTEMPTS,
    AdminStats,
    ChunkText,
    DailyStats,
    LibraryEntry,
    LibrarySource,
    LinkResult,
    NewLibrarySource,
    NotebookUse,
    Origin,
    OwnedNotebook,
    ProcessResult,
    StarterRef,
    StarterSource,
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
                '{"fake-embed": {"in": 2000, "out": 0}, "fake-llm": {"in": 30, "out": 150},'
                ' "fake-stt": {"in": 100, "out": 0}}'
            )
        )
        self.notebooks: dict[UUID, tuple[UUID, Notebook]] = {}
        self.library: dict[UUID, LibrarySource] = {}
        self.links: dict[UUID, tuple[UUID, UUID, datetime]] = {}
        self.chunks: dict[UUID, list[tuple[Chunk, list[float]]]] = {}
        self.usage: list[UsageRecord] = []
        self.credits: dict[UUID, int] = {}
        self.claimed: dict[UUID, str] = {}
        self.refreshed: list[UUID] = []
        self.default_balance = balance
        # Account seeds the pricing row with a rate; one dollar per euro here.
        self.rules = PricingRules(usd_per_eur=Decimal(1))
        self.admins: set[UUID] = set()
        self.viewers: set[UUID] = set()
        # account's users.preferences -> 'trash_days'; missing means 14
        self.trash_days: dict[UUID, int] = {}
        self.seeded: set[UUID] = set()
        # settings "starter_notebook", and rag's output_copies handover rows
        self.starter: StarterRef | None = None
        self.output_copies: list[tuple] = []
        self.chunk_ids: dict[UUID, list[UUID]] = {}
        self.purged_versions: list[str] = []
        # rag's outputs table as far as ingest reads it: generated library
        # id -> (origin notebook or None once deleted, origin title).
        self.outputs: dict[UUID, tuple[UUID | None, str]] = {}
        self.output_ids: dict[UUID, UUID] = {}
        self.retry_at: dict[UUID, datetime] = {}
        # rag's outputs.reserved_cents: output id -> (owner, status, cents).
        self.reservations: dict[UUID, tuple[UUID, str, Decimal]] = {}

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
        return self._listed(lib) and lib.deleted_at is None and lib.superseded_by is None

    def _trashed(self, lib: LibrarySource) -> bool:
        return self._listed(lib) and lib.deleted_at is not None

    def _purge_at(self, lib: LibrarySource) -> datetime:
        assert lib.deleted_at is not None
        return lib.deleted_at + timedelta(days=max(0, self.trash_days.get(lib.owner, 14)))

    # -- notebooks -------------------------------------------------------------

    def list_notebooks(self, owner: UUID) -> list[OwnedNotebook]:
        return [nb for o, nb in self.notebooks.values() if o == owner]

    def create_notebook(self, owner: UUID, title: str) -> OwnedNotebook:
        nb = OwnedNotebook(id=uuid4(), title=title, created_at=datetime.now(UTC))
        self.notebooks[nb.id] = (owner, nb)
        return nb

    def get_notebook(self, owner: UUID, notebook_id: UUID) -> OwnedNotebook | None:
        entry = self.notebooks.get(notebook_id)
        return entry[1] if entry and entry[0] == owner else None

    def _update_notebook(self, owner, notebook_id, **fields) -> OwnedNotebook | None:
        nb = self.get_notebook(owner, notebook_id)
        if nb is None:
            return None
        self.notebooks[notebook_id] = (owner, nb.model_copy(update=fields))
        return self.notebooks[notebook_id][1]

    def rename_notebook(self, owner, notebook_id, title):
        return self._update_notebook(owner, notebook_id, title=title)

    def share_notebook(self, owner, notebook_id):
        nb = self.get_notebook(owner, notebook_id)
        if nb is None:
            return None
        token = nb.share_token or secrets.token_urlsafe(24)
        self._update_notebook(owner, notebook_id, share_token=token)
        return token

    def unshare_notebook(self, owner, notebook_id):
        return self._update_notebook(owner, notebook_id, share_token=None) is not None

    def delete_notebook(self, owner: UUID, notebook_id: UUID) -> None:
        if self.get_notebook(owner, notebook_id) is None:
            return
        for link_id, (nb, _, _) in list(self.links.items()):
            if nb == notebook_id:
                self.links.pop(link_id, None)
        del self.notebooks[notebook_id]
        # rag's foreign key: the output keeps its title snapshot.
        for lib_id, (origin, title) in list(self.outputs.items()):
            if origin == notebook_id:
                self.outputs[lib_id] = (None, title)

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
            url=lib.url,
            summary=lib.summary,
            attempts=lib.attempts,
            size_bytes=lib.size_bytes,
            capture=lib.capture,
            starter=lib.starter,
            funded_request_at=lib.funded_request_at,
            funded_cents=lib.funded_cents,
            version=lib.version,
            fetched_at=lib.fetched_at,
            final_url=lib.final_url,
            checked_at=lib.checked_at,
            snapshot_path=lib.snapshot_path,
            transcribed_path=lib.transcribed_path,
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
        self.links.pop(source_id)

    def linkable(self, owner: UUID, library_id: UUID) -> bool:
        lib = self.library.get(library_id)
        return (
            lib is not None
            and lib.owner == owner
            and lib.deleted_at is None
            and (lib.kind != "generated" or lib.status == "ready")
        )

    def add_output(self, notebook_id: UUID, title: str, status: str = "ready") -> UUID:
        """What rag does for a finished output: a generated library source
        linked into its notebook (link id = library id) and the outputs
        row's origin."""
        owner = self.notebooks[notebook_id][0]
        lib = self.add_source(notebook_id, title, "generated", None)
        self.set_library_status(lib.library_id, status)
        self.outputs[lib.library_id] = (notebook_id, self.notebooks[notebook_id][1].title)
        self.output_ids[lib.library_id] = uuid4()
        assert self.library[lib.library_id].owner == owner
        return lib.library_id

    def request_refetch(self, library_id, estimate_cents=None, funded=False):
        lib = self.library.get(library_id)
        if (
            lib is None
            or lib.kind != "url"
            or lib.superseded_by is not None
            or lib.deleted_at is not None
            or lib.status not in ("ready", "added", "failed")
        ):
            return None
        self.library[library_id] = lib.model_copy(
            update={
                "status": "processing",
                "error": None,
                "attempts": 0,
                "refetch_requested_at": datetime.now(UTC) if lib.status == "ready" else None,
                "funded_request_at": datetime.now(UTC) if funded else None,
                "funded_cents": estimate_cents,
            }
        )
        self.claimed.pop(library_id, None)
        return self.library[library_id]

    def set_fetched(self, library_id, content_hash, final_url, snapshot_path):
        now = datetime.now(UTC)
        self.library[library_id] = self.library[library_id].model_copy(
            update={
                "fetched_at": now,
                "checked_at": now,
                "content_hash": content_hash,
                "final_url": final_url,
                "snapshot_path": snapshot_path,
            }
        )

    def refetch_unchanged(self, library_id, snapshot_path=None, final_url=None):
        lib = self.library[library_id]
        self.library[library_id] = lib.model_copy(
            update={
                "status": "ready",
                "checked_at": datetime.now(UTC),
                "refetch_requested_at": None,
                "error": None,
                "funded_request_at": None,
                "funded_cents": None,
                "snapshot_path": lib.snapshot_path or snapshot_path,
                "final_url": lib.final_url or final_url,
            }
        )
        self.claimed.pop(library_id, None)

    def new_version(self, library_id):
        old = self.library[library_id]
        new_id = uuid4()
        self.library[new_id] = old.model_copy(
            update={
                "id": new_id,
                "status": "processing",
                "version": old.version + 1,
                "fetched_at": None,
                "checked_at": None,
                "final_url": None,
                "snapshot_path": None,
                "content_hash": None,
                "refetch_requested_at": None,
                "summary": None,
                "attempts": 0,
                "created_at": datetime.now(UTC),
            }
        )
        self.library[library_id] = old.model_copy(
            update={
                "dedupe_key": None,
                "status": "ready",
                "refetch_requested_at": None,
                "superseded_by": new_id,
                "funded_request_at": None,
                "funded_cents": None,
            }
        )
        self.claimed.pop(library_id, None)
        for link_id, (nb, lib_id, created) in list(self.links.items()):
            if lib_id == library_id:
                self.links[link_id] = (nb, new_id, created)
        return new_id

    def queue_for_processing(self, owner, library_ids, estimates=None, funded=False):
        missing = [
            i
            for i in library_ids
            if (lib := self.library.get(i)) is None or lib.owner != owner or lib.deleted_at
        ]
        if missing:
            return ProcessResult(missing=missing)
        result = ProcessResult()
        for library_id in library_ids:
            lib = self.library[library_id]
            if lib.status == "added":
                update = {"status": "processing"}
                if estimates and library_id in estimates:
                    update |= {
                        "funded_cents": estimates[library_id],
                        "funded_request_at": datetime.now(UTC) if funded else None,
                    }
                self.library[library_id] = lib.model_copy(update=update)
                result.queued.append(library_id)
            else:
                result.unchanged.append(library_id)
        return result

    def link_many(self, owner, notebook_id, library_ids):
        missing = [i for i in library_ids if not self.linkable(owner, i)]
        if missing:
            return LinkResult(missing=missing)
        result = LinkResult()
        for library_id in library_ids:
            new = self.link_source(notebook_id, library_id)[1]
            (result.added if new else result.already).append(library_id)
        return result

    def list_generated(self, owner: UUID) -> list[LibraryEntry]:
        libs = [
            lib
            for lib in self.library.values()
            if lib.owner == owner
            and lib.kind == "generated"
            and lib.status == "ready"
            and lib.deleted_at is None
        ]
        entries = []
        for lib in sorted(libs, key=lambda x: x.created_at, reverse=True):
            origin_id, snapshot = self.outputs.get(lib.id, (None, None))
            title = self.notebooks[origin_id][1].title if origin_id else snapshot
            entries.append(
                self._entry(lib).model_copy(
                    update={
                        "origin": Origin(id=origin_id, title=title),
                        "output_id": self.output_ids.get(lib.id),
                    }
                )
            )
        return entries

    # -- the library -------------------------------------------------------------

    def find_library_source(self, owner: UUID, dedupe_key: str) -> LibrarySource | None:
        for lib in self.library.values():
            if lib.owner == owner and lib.dedupe_key == dedupe_key and self._listed(lib):
                return lib
        return None

    def create_library_source(self, new: NewLibrarySource) -> LibrarySource:
        # Like the unique index (owner, dedupe_key): independent of any lookup.
        for lib in self.library.values():
            if lib.owner == new.owner and lib.dedupe_key == new.dedupe_key:
                return lib
        lib = LibrarySource(**new.model_dump(), status="added", created_at=datetime.now(UTC))
        self.library[lib.id] = lib
        return lib

    def is_seeded(self, owner: UUID) -> bool:
        return owner in self.seeded

    def starter_ref(self):
        return self.starter

    def starter_sources(self, ref):
        if self.get_notebook(ref.owner_id, ref.notebook_id) is None:
            return None
        return [
            StarterSource(link_id=link_id, library=lib)
            for link_id, (nb, lib_id, _) in self.links.items()
            if nb == ref.notebook_id
            and (lib := self.library[lib_id]).owner == ref.owner_id
            and lib.kind != "generated"
            and lib.status == "ready"
            and lib.deleted_at is None
        ]

    def copy_starter(self, plan):
        if plan.owner in self.seeded:
            return None
        self.seeded.add(plan.owner)
        if any(lib.owner == plan.owner and self._listed(lib) for lib in self.library.values()):
            return None
        self.notebooks[plan.notebook_id] = (
            plan.owner,
            OwnedNotebook(id=plan.notebook_id, title=plan.title, created_at=datetime.now(UTC)),
        )
        source_map, chunk_map = {}, {}
        for source, library_id, link_id, key, converted, snapshot in plan.sources:
            old = source.library
            self.library[library_id] = old.model_copy(
                update={
                    "id": library_id,
                    "owner": plan.owner,
                    "storage_path": key,
                    "transcribed_path": converted,
                    "snapshot_path": snapshot,
                    "starter": True,
                    "status": "ready",
                    "attempts": 0,
                    "created_at": datetime.now(UTC),
                }
            )
            self.links[link_id] = (plan.notebook_id, library_id, datetime.now(UTC))
            self.chunks[library_id] = list(self.chunks.get(old.id, []))
            self.chunk_ids[library_id] = [uuid4() for _ in self.chunks[library_id]]
            source_map[str(source.link_id)] = str(link_id)
            source_map[str(old.id)] = str(library_id)
        maps = {"source_map": source_map, "chunk_map": chunk_map}
        self.output_copies.append((plan.notebook_id, plan.source_notebook, plan.owner, maps))
        return maps

    def retry_library_source(self, library_id: UUID) -> None:
        lib = self.library[library_id]
        if lib.status == "failed":
            self.library[library_id] = lib.model_copy(
                update={"status": "added", "error": None, "attempts": 0}
            )
            self.claimed.pop(library_id, None)
            self.retry_at.pop(library_id, None)

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
            starter=lib.starter,
            funded_request_at=lib.funded_request_at,
            funded_cents=lib.funded_cents,
            version=lib.version,
            fetched_at=lib.fetched_at,
            final_url=lib.final_url,
            checked_at=lib.checked_at,
            snapshot_path=lib.snapshot_path,
            storage_path=lib.storage_path,
            transcribed_path=lib.transcribed_path,
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

    def purge_library_source(self, owner: UUID, library_id: UUID) -> tuple[bool, list[str]]:
        lib = self.library.get(library_id)
        if lib is None or lib.owner != owner or not self._trashed(lib):
            return False, []
        self.purged_versions = []
        self._delete_library(library_id)
        return True, list(dict.fromkeys([*_keys([lib]), *self.purged_versions]))

    def user_object_keys(self, owner: UUID) -> list[str]:
        return _keys(
            [lib for lib in self.library.values() if lib.owner == owner and lib.kind != "generated"]
        )

    def delete_user_data(self, owner: UUID) -> None:
        for lib in [lib for lib in self.library.values() if lib.owner == owner]:
            self._delete_library(lib.id)
            for link_id, (_, lib_id, _) in list(self.links.items()):
                if lib_id == lib.id:
                    del self.links[link_id]
        for nb, (nb_owner, _) in list(self.notebooks.items()):
            if nb_owner == owner:
                del self.notebooks[nb]
                for link_id, (link_nb, _, _) in list(self.links.items()):
                    if link_nb == nb:
                        del self.links[link_id]
        self.seeded.discard(owner)

    def purge_expired(self) -> list[str]:
        now = datetime.now(UTC)
        gone = [
            lib
            for lib in self.library.values()
            if self._trashed(lib) and self._purge_at(lib) <= now
        ]
        self.purged_versions = []
        for lib in gone:
            self._delete_library(lib.id)
        return list(dict.fromkeys([*_keys(gone), *self.purged_versions]))

    def _delete_library(self, library_id: UUID) -> None:
        # Older versions of a web page go with it.
        for older in [lib.id for lib in self.library.values() if lib.superseded_by == library_id]:
            self.purged_versions.extend(_keys([self.library[older]]))
            self._delete_library(older)
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
        update = {"status": status, "error": error}
        if status in ("ready", "failed"):
            update |= {"funded_request_at": None, "funded_cents": None}
        self.library[library_id] = self.library[library_id].model_copy(update=update)

    def release_for_retry(self, library_id: UUID, error: str, delay_seconds: float) -> None:
        self.library[library_id] = self.library[library_id].model_copy(update={"error": error})
        self.claimed.pop(library_id, None)
        self.retry_at[library_id] = datetime.now(UTC) + timedelta(seconds=delay_seconds)

    def refresh_claim(self, library_id: UUID) -> None:
        self.refreshed.append(library_id)

    def release_waiting(self, library_id: UUID) -> None:
        lib = self.library[library_id]
        self.library[library_id] = lib.model_copy(
            update={"attempts": max(lib.attempts - 1, 0), "error": None}
        )
        self.claimed.pop(library_id, None)

    def claim_library_source(self, worker_id: str, stale_after_seconds: int) -> UUID | None:
        for lib in sorted(self.library.values(), key=lambda s: s.created_at):
            if (
                lib.status == "processing"
                and lib.kind != "generated"
                and lib.deleted_at is None
                and lib.id not in self.claimed
                and lib.attempts < MAX_ATTEMPTS
                and self.retry_at.get(lib.id, datetime.min.replace(tzinfo=UTC)) <= datetime.now(UTC)
                and self._fundable(lib)
            ):
                self.claimed[lib.id] = worker_id
                self.library[lib.id] = lib.model_copy(update={"attempts": lib.attempts + 1})
                return lib.id
        return None

    def set_library_summary(self, library_id: UUID, summary: str) -> None:
        self.library[library_id] = self.library[library_id].model_copy(update={"summary": summary})

    def set_transcribed_path(self, library_id: UUID, key: str) -> None:
        self.library[library_id] = self.library[library_id].model_copy(
            update={"transcribed_path": key}
        )

    def replace_chunks(
        self, library_id: UUID, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        self.chunks[library_id] = list(zip(chunks, vectors, strict=True))
        self.chunk_ids[library_id] = [uuid4() for _ in chunks]

    def list_chunks(self, library_id, offset, limit):
        rows = sorted(
            zip(self.chunk_ids.get(library_id, []), self.chunks.get(library_id, []), strict=True),
            key=lambda pair: pair[1][0].idx,
        )
        page = [
            ChunkText(chunk_id=cid, index=chunk.idx, page=chunk.page, text=chunk.text)
            for cid, (chunk, _) in rows[offset : offset + limit]
        ]
        return len(rows), page

    def record_usage(self, user_id, notebook_id, action, action_id, usage) -> UsageRecord:
        """core's booking without the database: the cost in US cents from
        the prices, in euro cents at the rules' rate, the charge from the
        rules (fees are core's business)."""
        assert is_usage_action(action), action
        cost_usd = cost_cents(self.prices, usage.model, usage.tokens_in, usage.tokens_out)
        cost = self.rules.cost_eur_cents(cost_usd)
        record = UsageRecord(
            user_id=user_id,
            notebook_id=notebook_id,
            service="ingest",
            action=action,
            action_id=action_id,
            kind=usage.kind,
            model=usage.model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            cost_usd_cents=cost_usd,
            usd_per_eur=self.rules.usd_per_eur,
            cost_cents=cost,
            charge_cents=self.rules.charge_cents(action, cost),
        )
        self.usage.append(record)
        return record

    def balance_cents(self, user_id: UUID):
        credits = self.credits.get(user_id, self.default_balance)
        return credits - sum(u.charge_cents for u in self.usage if u.user_id == user_id)

    def pricing_rules(self) -> PricingRules:
        return self.rules

    def has_exchange_rate(self) -> bool:
        return self.rules.usd_per_eur is not None

    def _fundable(self, lib):
        """The claim query's rule: funded at request, or the balance less what
        started work holds covers this read's estimate."""
        if lib.funded_request_at is not None:
            return True
        held = self.held_cents(lib.owner)  # this row is not funded
        balance = self.balance_cents(lib.owner)
        return balance > 0 and balance - held >= (lib.funded_cents or 0)

    def held_cents(self, owner):
        return sum(
            (
                lib.funded_cents or Decimal(0)
                for lib in self.library.values()
                if lib.owner == owner
                and lib.funded_request_at is not None
                and lib.status == "processing"
                and lib.deleted_at is None
            ),
            Decimal(0),
        ) + sum(
            (
                cents
                for who, status, cents in self.reservations.values()
                if who == owner and status in ("waiting", "processing")
            ),
            Decimal(0),
        )

    def has_credit(self, user_id: UUID) -> bool:
        # core's rule: a positive balance, for every user alike (admins too).
        return self.balance_cents(user_id) > 0

    def admin_role(self, user_id: UUID) -> str:
        if user_id in self.admins:
            return "admin"
        return "viewer" if user_id in self.viewers else "user"

    def admin_stats(self, stale_after_seconds: int) -> AdminStats:
        listed = [lib for lib in self.library.values() if self._listed(lib)]
        counts = {status: 0 for status in ("added", "processing", "ready", "failed")}
        for lib in listed:
            counts[lib.status] += 1
        running = sum(1 for lib in listed if lib.status == "processing" and lib.id in self.claimed)
        waiting = sum(
            1
            for lib in listed
            if lib.status == "processing" and lib.id not in self.claimed and not self._fundable(lib)
        )
        return AdminStats(
            sources=counts,
            jobs={
                "pending": counts["processing"] - running - waiting,
                "running": running,
                "waiting_for_credit": waiting,
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

    def presigned_get(
        self, key: str, expires_s: int = 3600, *, download_name: str | None = None
    ) -> str:
        url = f"https://storage.test/{key}?expires={expires_s}"
        return f"{url}&download={download_name}" if download_name else url


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


class FakeTranscriber:
    """Core's SpeechToText: one fixed transcript (or error) per call, every
    recording recorded with its file name."""

    def __init__(self, answer: str = "Hallo und willkommen zur Sendung.", error=None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[bytes, str]] = []

    @property
    def model(self) -> str:
        return "fake-stt"

    def transcribe(self, audio: bytes, filename: str) -> TranscriptionResult:
        self.calls.append((audio, filename))
        if self.error is not None:
            raise self.error
        return TranscriptionResult(self.answer, Usage("stt", "fake-stt", 90, 0), 90.0)


def _keys(libs: list[LibrarySource]) -> list[str]:
    return [
        k for lib in libs for k in (lib.storage_path, lib.transcribed_path, lib.snapshot_path) if k
    ]
