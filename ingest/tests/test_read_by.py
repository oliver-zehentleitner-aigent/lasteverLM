"""Which models read a source: `read_by` on the source and the chunks
view, and `vision` on each chunk, so the web can say "Described by …",
"Page read by …" or "Transcribed by …"."""

from uuid import UUID

from lasteverlm_core import Chunk

from lasteverlm_ingest.loaders import default_registry
from lasteverlm_ingest.loaders.image import VisionReader
from lasteverlm_ingest.worker import process_source
from tests.fakes import FakeChat, FakeEmbedder, FakeTranscriber, InMemoryRepository, InMemoryStorage
from tests.test_audio_loader import _add_audio, _audio_deps
from tests.test_image_loader import _add_image, _image_deps
from tests.test_pdf_capture import MIXED, _pdf_source
from tests.test_worker import add_source, deps


def test_each_kind_records_the_model_that_made_its_text():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    image = _add_image(repo, storage)
    process_source(image, _image_deps(repo, storage, FakeEmbedder(8), FakeChat()))
    assert repo.library[image].read_by == {"vision": "fake-llm", "stt": None}
    assert repo.library[image].vision_pages is None

    audio = _add_audio(repo, storage)
    process_source(audio, _audio_deps(repo, storage, FakeTranscriber()))
    assert repo.library[audio].read_by == {"vision": None, "stt": "fake-stt"}

    text = add_source(repo, storage, b"plain words here", key="t")
    process_source(text, deps(repo, storage, FakeEmbedder(8)))
    assert repo.library[text].status == "ready" and repo.library[text].read_by is None


def _pdf_deps(repo, storage):
    d = deps(repo, storage, FakeEmbedder(8))
    vision = VisionReader(FakeChat(answer="Scan text."), "fake-llm")
    return d.__class__(**{**d.__dict__, "loaders": default_registry(vision=vision)})


def test_a_pdf_records_which_pages_the_vision_model_read():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    auto = _pdf_source(repo, storage, MIXED, "auto")  # page 2 has no text layer
    process_source(auto, _pdf_deps(repo, storage))
    assert repo.library[auto].read_by == {"vision": "fake-llm", "stt": None}
    assert repo.library[auto].vision_pages == [2]
    every = _pdf_source(repo, storage, MIXED, "vision")
    process_source(every, _pdf_deps(repo, storage))
    assert repo.library[every].vision_pages == [1, 2, 3]


def test_an_auto_pdf_whose_pages_all_have_text_was_read_by_no_model():
    from tests.test_loaders import minimal_pdf
    from tests.test_pdf_capture import TEXT

    repo, storage = InMemoryRepository(), InMemoryStorage()
    lib = _pdf_source(repo, storage, minimal_pdf([TEXT, TEXT]), "auto")
    process_source(lib, _pdf_deps(repo, storage))
    assert repo.library[lib].read_by is None and repo.library[lib].vision_pages is None


def _linked(client, repo, kind, read_by, vision_pages=None):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    src = repo.add_source(UUID(nb), f"a.{kind}", kind, "k")
    repo.replace_chunks(
        src.library_id,
        [
            Chunk(idx=i, text=f"chunk {i}", page=(i + 1 if kind == "pdf" else None))
            for i in range(3)
        ],
        [[float(i), 0.0] for i in range(3)],
    )
    repo.set_read_by(src.library_id, read_by, vision_pages)
    return nb, src


def test_the_api_shows_read_by_and_which_chunks_vision_read(client, repo):
    nb, src = _linked(client, repo, "pdf", {"vision": "qwen-vl", "stt": None}, [2])
    [listed] = client.get(f"/api/ingest/notebooks/{nb}/sources").json()
    assert listed["read_by"] == {"vision": "qwen-vl", "stt": None}
    assert "vision_pages" not in listed
    body = client.get(f"/api/ingest/sources/{src.id}/chunks").json()
    assert body["read_by"] == {"vision": "qwen-vl", "stt": None}
    assert [(c["page"], c["vision"]) for c in body["chunks"]] == [(1, False), (2, True), (3, False)]


def test_an_image_is_vision_throughout_and_text_is_read_by_no_model(client, repo):
    _, image = _linked(client, repo, "image", {"vision": "qwen-vl", "stt": None})
    chunks = client.get(f"/api/ingest/sources/{image.id}/chunks").json()["chunks"]
    assert all(c["vision"] for c in chunks)
    nb, text = _linked(client, repo, "text", None)
    body = client.get(f"/api/ingest/sources/{text.id}/chunks").json()
    assert body["read_by"] is None and not any(c["vision"] for c in body["chunks"])
    assert client.get(f"/api/ingest/notebooks/{nb}/sources").json()[0]["read_by"] is None
    # A recording names its speech model, and no chunk is vision.
    _, audio = _linked(client, repo, "audio", {"vision": None, "stt": "whisper"})
    body = client.get(f"/api/ingest/sources/{audio.id}/chunks").json()
    assert body["read_by"] == {"vision": None, "stt": "whisper"}
    assert not any(c["vision"] for c in body["chunks"])
