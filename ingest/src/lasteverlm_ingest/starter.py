"""The starter notebook: every new user gets a copy of the notebook an
admin marks as the starter (account's settings row "starter_notebook").

On the owner's first notebook list (the first thing the web loads after
sign-in), library listing or upload, the starter's uploads are
copied for them: the stored objects under the owner's prefix, then in
one transaction the notebook, the library rows (ready, flagged
`starter`, no processing and no charge), their links and their chunks
with embeddings. The same transaction hands rag the id maps
(`output_copies`), and rag's worker copies the starter's outputs into
the new notebook. Nothing is shared between users: the copies are the
owner's own and can be deleted like any upload. Without a starter
nothing is seeded, and the owner is not marked, so they get the starter
once one is set (as long as their library is still empty).

The owner can also ask for the starter again (`recreate_starter`, at most
one an hour): a new notebook flagged `starter`, linking the starter
sources they still have and copying the rest.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from lasteverlm_core import Storage, StorageError, object_key

from lasteverlm_ingest.loaders.convert import MEDIA_TYPES, sniff_container
from lasteverlm_ingest.loaders.image import sniff_image_type
from lasteverlm_ingest.repository import Repository, StarterCopy, StarterRef
from lasteverlm_ingest.worker import SNAPSHOT_NAME, TRANSCRIBED_NAME

log = logging.getLogger(__name__)

# As the upload stores them (api/sources.py, _CONTENT_TYPE).
_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
    "url": "text/uri-list",
}


def ensure_starter(repo: Repository, storage: Storage, owner: UUID) -> int:
    """Copy the starter notebook for a new owner, once. Returns the number of
    sources copied (0 when the owner was considered already, there is no
    starter, the owner is the starter's own author, or copying failed and
    will be tried again on the next access)."""
    if repo.is_seeded(owner):
        return 0
    ref = repo.starter_ref()
    if ref is None or ref.owner_id == owner:
        return 0
    plan = _plan(repo, ref, owner)
    if plan is None:
        return 0
    copied = _copy_objects(storage, owner, plan)
    if copied is None:
        return 0
    if repo.copy_starter(plan) is None:
        # Another request seeded this owner first, or they have entries.
        _remove(storage, copied)
        return 0
    log.info("copied the starter notebook for %s (%d sources)", owner, len(plan.sources))
    return len(plan.sources)


@dataclass(frozen=True)
class Recreated:
    """The outcome of a copy made on request: the new notebook's id, or why
    there is none (`no_starter`, `too_soon` with `retry_after` seconds,
    `storage` when an object could not be copied)."""

    notebook_id: UUID | None = None
    refused: str | None = None
    retry_after: int = 0


def recreate_starter(repo: Repository, storage: Storage, owner: UUID) -> Recreated:
    """A fresh copy of the current starter on the owner's request, at most
    one an hour, whether or not they were seeded before. Starter sources
    the owner still has (deleting a notebook keeps its sources) are linked
    again, restored from the trash if need be; only the ones that are gone
    are copied. Free, like the first copy."""
    wait = repo.starter_copy_wait(owner)
    if wait:
        return Recreated(refused="too_soon", retry_after=wait)
    ref = repo.starter_ref()
    if ref is None:
        return Recreated(refused="no_starter")
    plan = _plan(repo, ref, owner, reuse=True)
    if plan is None:
        return Recreated(refused="no_starter")
    copied = _copy_objects(storage, owner, plan)
    if copied is None:
        return Recreated(refused="storage")
    if repo.recreate_starter(plan) is None:
        _remove(storage, copied)
        return Recreated(refused="too_soon", retry_after=repo.starter_copy_wait(owner))
    log.info(
        "made the starter notebook again for %s (%d copied, %d linked)",
        owner,
        len(plan.sources),
        len(plan.reuse),
    )
    return Recreated(notebook_id=plan.notebook_id)


def _plan(
    repo: Repository, ref: StarterRef, owner: UUID, *, reuse: bool = False
) -> StarterCopy | None:
    """The copy to make, objects not copied yet: every starter source to
    copy, or with `reuse` to link when the owner already has it."""
    sources = repo.starter_sources(ref)
    notebook = repo.get_notebook(ref.owner_id, ref.notebook_id)
    if sources is None or notebook is None:
        log.warning("starter notebook %s not found; nothing is copied", ref.notebook_id)
        return None
    keys = [s.library.dedupe_key for s in sources if s.library.dedupe_key]
    owned = repo.owned_by_dedupe_key(owner, keys) if reuse and keys else {}
    plan = StarterCopy(
        owner=owner,
        source_notebook=ref.notebook_id,
        notebook_id=uuid4(),
        title=notebook.title,
        sources=[],
    )
    for source in sources:
        mine = owned.get(source.library.dedupe_key or "")
        if mine is not None:
            plan.reuse.append((source, mine, uuid4()))
        else:
            plan.sources.append((source, uuid4(), uuid4(), None, None, None))
    return plan


def _copy_objects(storage: Storage, owner: UUID, plan: StarterCopy) -> list[str] | None:
    """Copy the stored objects of the sources to copy under the owner's
    prefix and fill in their keys; None (and nothing left behind) when
    storage fails."""
    copied: list[str] = []
    filled = []
    try:
        for source, library_id, link_id, _, _, _ in plan.sources:
            old = source.library
            key = converted = snapshot = None
            if old.storage_path:
                key = object_key(owner, library_id, "url" if old.kind == "url" else old.name)
                data = storage.get(old.storage_path)
                storage.put(key, data, _media_type(old.kind, data))
                copied.append(key)
            if old.transcribed_path:
                converted = object_key(owner, library_id, TRANSCRIBED_NAME)
                storage.put(converted, storage.get(old.transcribed_path), "audio/mpeg")
                copied.append(converted)
            if old.snapshot_path:
                snapshot = object_key(owner, library_id, SNAPSHOT_NAME)
                storage.put(snapshot, storage.get(old.snapshot_path), "text/html; charset=utf-8")
                copied.append(snapshot)
            filled.append((source, library_id, link_id, key, converted, snapshot))
    except StorageError as exc:
        log.warning("starter copy for %s failed: %s", owner, exc)
        _remove(storage, copied)
        return None
    plan.sources[:] = filled
    return copied


def _media_type(kind: str, data: bytes) -> str:
    """The type the upload stored the object with (see api/sources.py)."""
    if kind == "image":
        return sniff_image_type(data) or "application/octet-stream"
    if kind == "audio":
        container = sniff_container(data)
        if container is not None:
            return MEDIA_TYPES[container]
        return "audio/wav" if data[:4] == b"RIFF" else "audio/mpeg"
    return _CONTENT_TYPE.get(kind, "application/octet-stream")


def _remove(storage: Storage, keys: list[str]) -> None:
    if keys:
        with contextlib.suppress(StorageError):
            storage.delete(*keys)
