"""The demo library: one source per kind that every new user finds in
their library, so they can try the system at once.

The five sources form one fictional set around Zeltavia (the country of
the family's smoke test): an expedition's field notes as a PDF with page
breaks, a glossary as text, a map of Marrow Bay as an image, a real
article on dead reckoning, the navigation the field notes describe, and
a radio interview with the keeper of Hollin Lighthouse as an MP3, whose
facts are in no other source. The
files live in `demo/` next to this module (built by `demo/build.py` at
the root of the service). They are inserted as ordinary library sources
flagged `demo`, processed by the worker like any upload, and paid for by
the demo user: a new user has no credit yet.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from lasteverlm_core import DEMO_USER_ID, Storage, object_key

from lasteverlm_ingest.dedupe import file_key, url_key
from lasteverlm_ingest.repository import NewLibrarySource, Repository

log = logging.getLogger(__name__)

DEMO_DIR = Path(__file__).parent / "demo"
DEMO_URL = "https://en.wikipedia.org/wiki/Dead_reckoning"


@dataclass(frozen=True)
class Seed:
    name: str
    kind: str
    file: str | None = None
    content_type: str = "application/octet-stream"
    capture: str | None = None
    url: str | None = None


SEEDS = (
    Seed("field-notes-1893.pdf", "pdf", "field-notes.pdf", "application/pdf", capture="text"),
    Seed("zeltavian-glossary.md", "text", "glossary.md", "text/plain; charset=utf-8"),
    Seed("marrow-bay-map.png", "image", "marrow-bay-map.png", "image/png"),
    Seed(DEMO_URL, "url", url=DEMO_URL, content_type="text/uri-list"),
    Seed("hollin-interview.mp3", "audio", "hollin-interview.mp3", "audio/mpeg"),
)


def ensure_seeded(repo: Repository, storage: Storage, owner: UUID) -> int:
    """Give a new owner the demo library, once. Returns the number of
    sources created (0 when already considered, when the owner had
    entries, or for the demo user itself). Same keys as an upload, so the
    user uploading a demo file again links the demo source."""
    if owner == DEMO_USER_ID or not repo.claim_seed(owner):
        return 0
    created = 0
    for seed in SEEDS:
        library_id = uuid4()
        if seed.url is not None:
            data = seed.url.encode()
            dedupe_key = url_key(seed.url)
            key = object_key(owner, library_id, "url")
        else:
            assert seed.file is not None
            data = (DEMO_DIR / seed.file).read_bytes()
            dedupe_key = file_key(data, seed.capture)
            key = object_key(owner, library_id, seed.name)
        storage.put(key, data, seed.content_type)
        repo.create_library_source(
            NewLibrarySource(
                id=library_id,
                owner=owner,
                name=seed.name,
                kind=seed.kind,
                dedupe_key=dedupe_key,
                url=seed.url,
                size_bytes=None if seed.url else len(data),
                storage_path=key,
                capture=seed.capture,
                demo=True,
            )
        )
        created += 1
    log.info("seeded the demo library for %s (%d sources)", owner, created)
    return created
