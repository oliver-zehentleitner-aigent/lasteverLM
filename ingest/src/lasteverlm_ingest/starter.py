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
"""

from __future__ import annotations

import contextlib
import logging
from uuid import UUID, uuid4

from lasteverlm_core import Storage, StorageError, object_key

from lasteverlm_ingest.loaders.convert import MEDIA_TYPES, sniff_container
from lasteverlm_ingest.loaders.image import sniff_image_type
from lasteverlm_ingest.repository import Repository, StarterCopy
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
    sources = repo.starter_sources(ref)
    notebook = repo.get_notebook(ref.owner_id, ref.notebook_id)
    if sources is None or notebook is None:
        log.warning("starter notebook %s not found; nothing is seeded", ref.notebook_id)
        return 0
    copied: list[str] = []
    plan = StarterCopy(
        owner=owner,
        source_notebook=ref.notebook_id,
        notebook_id=uuid4(),
        title=notebook.title,
        sources=[],
    )
    try:
        for source in sources:
            old = source.library
            library_id = uuid4()
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
            plan.sources.append((source, library_id, uuid4(), key, converted, snapshot))
    except StorageError as exc:
        log.warning("starter copy for %s failed, tried again next time: %s", owner, exc)
        _remove(storage, copied)
        return 0
    if repo.copy_starter(plan) is None:
        # Another request seeded this owner first, or they have entries.
        _remove(storage, copied)
        return 0
    log.info("copied the starter notebook for %s (%d sources)", owner, len(plan.sources))
    return len(plan.sources)


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
