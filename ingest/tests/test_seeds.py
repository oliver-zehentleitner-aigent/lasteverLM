from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, MemoryRateLimitStore, probe_audio

from lasteverlm_ingest.loaders import default_registry
from lasteverlm_ingest.loaders.image import VisionReader, sniff_image_type
from lasteverlm_ingest.loaders.pdf import PdfLoader
from lasteverlm_ingest.loaders.text import TextLoader
from lasteverlm_ingest.loaders.url import Fetched, UrlLoader
from lasteverlm_ingest.main import create_app
from lasteverlm_ingest.seeds import DEMO_DIR, DEMO_URL, SEEDS, ensure_seeded
from lasteverlm_ingest.worker import process_source
from tests.conftest import DEMO_TOKEN, make_settings
from tests.fakes import (
    FakeChat,
    FakeEmbedder,
    FakeTranscriber,
    InMemoryRepository,
    InMemoryStorage,
)
from tests.test_worker import deps

USER = UUID("00000000-0000-4000-8000-0000000000aa")


def _seeding_client(repo, storage, embedder, summarizer) -> TestClient:
    app = create_app(
        make_settings(SEED_DEMO_LIBRARY="true"),
        rate_limit_store=MemoryRateLimitStore(),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
        loaders=default_registry(vision=VisionReader(FakeChat(), "fake-llm")),
    )
    return TestClient(app)


def test_the_demo_files_are_what_the_seeds_promise():
    pages = PdfLoader().load((DEMO_DIR / "field-notes.pdf").read_bytes())
    assert [p.page for p in pages] == [1, 2, 3]
    flat = [" ".join(p.text.split()) for p in pages]
    assert "brennet" in flat[0] and "dead reckoning" in flat[1]
    map_png = (DEMO_DIR / "marrow-bay-map.png").read_bytes()
    assert sniff_image_type(map_png) == "image/png" and len(map_png) < 300_000
    glossary = TextLoader().load((DEMO_DIR / "glossary.md").read_bytes())[0].text
    assert "brennet" in glossary and "smokra" in glossary
    recording = (DEMO_DIR / "hollin-interview.mp3").read_bytes()
    info = probe_audio(recording)
    assert info.format == "mp3" and 45 < info.seconds < 90 and len(recording) < 1_000_000
    # Its facts are in no other demo source, so a question about them has
    # to be answered from the transcript.
    script = (DEMO_DIR / "hollin-interview.txt").read_text()
    others = " ".join(flat) + glossary
    for fact in ("Old Grumble", "Puffin Sunday", "Kestrel", "paraffin"):
        assert fact in script and fact not in others
    assert [s.kind for s in SEEDS] == ["pdf", "text", "image", "url", "audio"]


def test_first_library_access_seeds_once(repo, storage, embedder, summarizer):
    with _seeding_client(repo, storage, embedder, summarizer) as client:
        client.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        # The demo user (the token's principal) is the sponsor: never seeded.
        assert client.get("/api/ingest/library").json() == []
    assert ensure_seeded(repo, storage, USER) == 5
    entries = repo.list_library(USER)
    assert sorted(e.kind for e in entries) == ["audio", "image", "pdf", "text", "url"]
    assert all(e.demo and e.notebooks == [] for e in entries)
    assert {e.kind: e.capture for e in entries}["pdf"] == "text"
    assert {e.kind: e.url for e in entries}["url"] == DEMO_URL
    assert len([k for k in storage.objects if k.startswith(str(USER))]) == 5
    assert ensure_seeded(repo, storage, USER) == 0 and len(repo.list_library(USER)) == 5
    # Deleting everything never brings the demo back.
    for e in entries:
        repo.trash_library_source(USER, e.id)
        repo.purge_library_source(USER, e.id)
    assert ensure_seeded(repo, storage, USER) == 0


def test_an_owner_with_sources_is_not_seeded(repo, storage):
    nb = repo.create_notebook(USER, "nb")
    repo.add_source(nb.id, "mine.txt", "text", "k")
    assert ensure_seeded(repo, storage, USER) == 0
    assert [e.name for e in repo.list_library(USER)] == ["mine.txt"]
    assert USER in repo.seeded


def test_first_upload_seeds_and_the_demo_file_dedupes(repo, storage, embedder, summarizer):
    other = uuid4()
    repo.trash_days.clear()
    with _seeding_client(repo, storage, embedder, summarizer) as client:
        client.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        nb = client.post("/api/ingest/notebooks", json={"title": "x"}).json()["id"]
        r = client.post(
            f"/api/ingest/notebooks/{nb}/sources",
            files={"file": ("a.txt", b"some text", "text/plain")},
        )
        assert r.status_code == 202
    # The demo user is never seeded, also on upload.
    assert [e.name for e in repo.list_library(DEMO_USER_ID)] == ["a.txt"]
    # Another user's upload of a demo file links their demo source.
    ensure_seeded(repo, storage, other)
    notebook = repo.create_notebook(other, "nb")
    glossary = next(e for e in repo.list_library(other) if e.kind == "text")
    data = (DEMO_DIR / "glossary.md").read_bytes()
    import hashlib

    found = repo.find_library_source(other, "sha256:" + hashlib.sha256(data).hexdigest())
    assert found is not None and found.id == glossary.id
    repo.link_source(notebook.id, glossary.id)


def test_the_demo_user_pays_for_processing_the_seeds():
    repo, storage, chat = InMemoryRepository(), InMemoryStorage(), FakeChat(answer="A map.")
    repo.credits[USER] = 0  # a new user has no credit
    ensure_seeded(repo, storage, USER)
    d = deps(repo, storage, FakeEmbedder(8))
    loaders = default_registry(vision=VisionReader(chat, "fake-llm"), transcriber=FakeTranscriber())
    page = Fetched(DEMO_URL, "text/plain", None, b"Dead reckoning estimates a position.")
    loaders.register("url", UrlLoader(fetch=lambda url: page, text=TextLoader(), pdf=PdfLoader()))
    d = d.__class__(**{**d.__dict__, "loaders": loaders})
    for entry in repo.list_library(USER):
        process_source(entry.id, d)
    assert {e.kind: e.status for e in repo.list_library(USER)} == {
        "pdf": "ready",
        "text": "ready",
        "image": "ready",
        "url": "ready",
        "audio": "ready",
    }
    # The recording went through the normal pipeline: one billed transcription.
    assert [u.kind for u in repo.usage].count("stt") == 1
    assert repo.usage and {u.user_id for u in repo.usage} == {DEMO_USER_ID}
    # Booked as demo_seed, one action per seeded source.
    seeded = [u for u in repo.usage if u.user_id == DEMO_USER_ID]
    assert {u.action for u in seeded} == {"demo_seed"}
    assert len({u.action_id for u in seeded}) == 5
    assert repo.balance_cents(USER) == 0
    # The new user's own upload is still their own and still needs credit.
    nb = repo.create_notebook(USER, "nb")
    own = repo.add_source(nb.id, "own.txt", "text", "own")
    storage.put("own", b"my own text", "text/plain")
    process_source(own.library_id, d)
    assert repo.library[own.library_id].status == "processing"  # waits for credit
    assert repo.usage[-1].user_id == DEMO_USER_ID  # nothing billed to the new user
