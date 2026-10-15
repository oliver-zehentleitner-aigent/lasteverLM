from uuid import UUID

import httpx
import pytest
from lasteverlm_core import ProviderError
from openai import APIConnectionError

from lasteverlm_ingest.loaders import LoaderError, default_registry, loader_key
from lasteverlm_ingest.loaders.image import VisionReader
from lasteverlm_ingest.loaders.pdf import (
    MAX_EDGE_PX,
    PdfLoader,
    VisionPdfLoader,
    has_text,
    legible,
    render_page,
)
from lasteverlm_ingest.worker import process_source
from tests.fakes import FakeChat, FakeEmbedder, InMemoryRepository, InMemoryStorage
from tests.test_loaders import minimal_pdf
from tests.test_worker import USER, deps

TEXT = "A page with a real text layer on it."
# What pypdf returns for a font without a usable ToUnicode map: glyph codes.
GLYPHS = "&MM,:N K OP&M,MM P2QL +457$$$ LL R! 3'.SM"
VI = "Kurzanleitung vi-Editor. Starten einer vi Sitzung: vi datei.txt öffnet die Datei."
MIXED = minimal_pdf([TEXT, "", "Another page that has its own text."])
REQUEST = httpx.Request("POST", "https://inference.test/v1/chat/completions")


def _vision(chat: FakeChat, capture: str, **kwargs) -> VisionPdfLoader:
    return VisionPdfLoader(VisionReader(chat, "fake-llm"), capture, **kwargs)  # type: ignore[arg-type]


def test_render_page_is_a_jpeg_within_the_size_cap():
    image = render_page(MIXED, 1)
    assert image.startswith(b"\xff\xd8\xff")
    from io import BytesIO

    from PIL import Image

    width, height = Image.open(BytesIO(image)).size
    assert max(width, height) <= MAX_EDGE_PX and min(width, height) > 500


def test_text_capture_reads_the_text_layer_and_names_the_mode_when_empty():
    passages = PdfLoader().load(MIXED)
    assert [p.page for p in passages] == [1, 3]
    with pytest.raises(LoaderError, match="capture mode text"):
        PdfLoader().load(minimal_pdf(["", ""]))


def test_auto_reads_only_the_pages_without_text():
    chat, billed = FakeChat(answer="Scanned page, read by the model."), []
    passages = _vision(chat, "auto").load_billed(MIXED, billed.append)
    assert [(p.page, p.text) for p in passages] == [
        (1, TEXT),
        (2, "Scanned page, read by the model."),
        (3, "Another page that has its own text."),
    ]
    assert len(chat.calls) == 1 and len(billed) == 1
    url = chat.calls[0]["messages"][1]["content"][0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    # A PDF with a text layer on every page costs nothing in auto.
    chat2, billed2 = FakeChat(), []
    _vision(chat2, "auto").load_billed(minimal_pdf([TEXT, TEXT]), billed2.append)
    assert chat2.calls == [] and billed2 == []


def test_vision_reads_every_page_and_keeps_page_numbers():
    chat, billed = FakeChat(answer="Read by the model."), []
    passages = _vision(chat, "vision").load_billed(MIXED, billed.append)
    assert [p.page for p in passages] == [1, 2, 3]
    assert len(chat.calls) == 3 and len(billed) == 3


def test_blank_pages_are_skipped_and_an_all_blank_pdf_fails_naming_the_mode():
    with pytest.raises(LoaderError, match="no readable content \\(capture mode vision\\)"):
        _vision(FakeChat(answer=" "), "vision").load_billed(MIXED, lambda u: None)
    billed: list = []
    with pytest.raises(LoaderError, match="capture mode auto"):
        _vision(FakeChat(answer=""), "auto").load_billed(minimal_pdf(["", ""]), billed.append)
    assert len(billed) == 2  # the model looked at both pages: both are billed


def test_page_cap():
    with pytest.raises(LoaderError, match="3 pages for the vision model.*at most 2"):
        _vision(FakeChat(), "vision", max_pages=2).load_billed(MIXED, lambda u: None)


def test_answered_pages_are_billed_when_another_page_fails():
    class OneFails(FakeChat):
        def create(self, **kwargs):
            if len(self.calls) == 1:
                self.calls.append(kwargs)
                raise APIConnectionError(request=REQUEST)
            return super().create(**kwargs)

    billed: list = []
    with pytest.raises(ProviderError):
        _vision(OneFails(), "vision").load_billed(MIXED, billed.append)
    assert len(billed) == 2


def test_credit_gone_stops_before_the_next_batch_but_bills_the_batch():
    pdf = minimal_pdf([""] * 6)
    chat, billed = FakeChat(), []

    def bill(usage) -> None:
        billed.append(usage)
        raise RuntimeError("credit exhausted")

    with pytest.raises(RuntimeError, match="credit exhausted"):
        _vision(chat, "vision").load_billed(pdf, bill)
    assert len(chat.calls) == 4 and len(billed) == 4  # one batch, all of it billed


def test_has_text_threshold():
    assert not has_text("  3  ") and not has_text("") and has_text(TEXT)


def test_a_text_layer_of_glyph_codes_is_not_text():
    assert not legible(GLYPHS) and not has_text(GLYPHS)
    assert legible(VI) and has_text(VI)
    assert has_text("Ärger über Öl, Maße: Größe, Füße und Übermaß in Grüße.")
    assert has_text("vncserver :1 -geometry 1920x1080 -depth 24\nvncserver -kill :1")


def test_auto_sends_a_glyph_code_page_to_the_model():
    chat = FakeChat(answer="Read by the model.")
    pdf = minimal_pdf([TEXT, GLYPHS])
    passages = _vision(chat, "auto").load_billed(pdf, lambda usage: None)
    assert len(chat.calls) == 1
    assert [(p.page, p.text) for p in passages] == [(1, TEXT), (2, "Read by the model.")]


def test_text_capture_skips_a_glyph_code_page():
    passages = PdfLoader().load(minimal_pdf([GLYPHS, TEXT]))
    assert [(p.page, p.text) for p in passages] == [(2, TEXT)]
    with pytest.raises(LoaderError, match="no legible text"):
        PdfLoader().load(minimal_pdf([GLYPHS]))


def test_loader_keys():
    assert loader_key("pdf", "text") == "pdf" and loader_key("pdf", None) == "pdf"
    assert loader_key("pdf", "vision") == "pdf:vision" and loader_key("image", None) == "image"
    assert {"pdf:vision", "pdf:auto", "image"} <= default_registry(
        vision=VisionReader(FakeChat(), "m")
    ).kinds
    assert "pdf:auto" not in default_registry().kinds


def _pdf_source(repo, storage, data, capture):
    nb = repo.create_notebook(USER, "nb")
    src = repo.add_source(nb.id, "scan.pdf", "pdf", "pdf-key")
    repo.library[src.library_id] = repo.library[src.library_id].model_copy(
        update={"capture": capture}
    )
    storage.put("pdf-key", data, "application/pdf")
    return src.library_id


def test_worker_bills_each_page_then_embeds_and_summarizes():
    repo, storage, chat = InMemoryRepository(), InMemoryStorage(), FakeChat(answer="Scan text.")
    lib = _pdf_source(repo, storage, MIXED, "auto")
    d = deps(repo, storage, FakeEmbedder(8))
    d = d.__class__(
        **{**d.__dict__, "loaders": default_registry(vision=VisionReader(chat, "fake-llm"))}
    )
    process_source(lib, d)
    assert repo.library[lib].status == "ready"
    assert [u.kind for u in repo.usage] == ["llm", "embedding", "llm"]
    text = " ".join(c.text for c, _ in repo.chunks[lib])
    assert TEXT in text and "Scan text." in text


def test_a_vision_pdf_is_read_to_the_end_even_if_credit_runs_out_on_the_way():
    from decimal import Decimal

    pdf = minimal_pdf([""] * 6)  # six scanned pages
    repo, storage, chat = (
        InMemoryRepository(balance=Decimal("0.01")),
        InMemoryStorage(),
        FakeChat(answer="Scan text."),
    )
    lib = _pdf_source(repo, storage, pdf, "vision")
    d = deps(repo, storage, FakeEmbedder(8))
    d = d.__class__(
        **{**d.__dict__, "loaders": default_registry(vision=VisionReader(chat, "fake-llm"))}
    )
    process_source(lib, d)
    assert repo.library[lib].status == "ready"
    # Every page read and booked, though the balance went below zero on page one.
    assert len(chat.calls) == 6
    assert [u.kind for u in repo.usage] == ["llm"] * 6 + ["embedding", "llm"]
    assert repo.balance_cents(repo.library[lib].owner) < 0


def test_vision_capture_without_a_vision_model_fails_loud():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    lib = _pdf_source(repo, storage, MIXED, "vision")
    process_source(lib, deps(repo, storage, FakeEmbedder(8)))
    source = repo.library[lib]
    assert source.status == "failed" and source.error == "capture mode vision needs a vision model"


def test_upload_capture_field_and_dedupe_per_mode(client, repo, vision_chat, run_queue):
    nb = client.post("/api/ingest/notebooks", json={"title": "c"}).json()["id"]
    url = f"/api/ingest/notebooks/{nb}/sources"

    def up(capture=None, data=MIXED, name="doc.pdf", media="application/pdf"):
        form = {} if capture is None else {"capture": capture}
        return client.post(url, files={"file": (name, data, media)}, data=form)

    auto = up()
    assert auto.status_code == 202 and auto.json()["capture"] == "auto"
    assert up("auto").status_code == 200  # same bytes, same mode: the same source
    vision = up("vision")
    assert vision.status_code == 202 and vision.json()["capture"] == "vision"
    assert vision.json()["library_id"] != auto.json()["library_id"]
    assert up("ocr").status_code == 400
    text = up("vision", data=b"plain text", name="a.txt", media="text/plain")
    assert text.status_code == 202 and text.json()["capture"] is None  # ignored for non-PDFs
    entries = {e["id"]: e["capture"] for e in client.get("/api/ingest/library").json()}
    assert entries[auto.json()["library_id"]] == "auto"
    assert entries[vision.json()["library_id"]] == "vision"
    run_queue()
    assert repo.library[UUID(vision.json()["library_id"])].status == "ready"
    assert len(vision_chat.calls) == 3 + 1  # vision: every page; auto: the blank one
