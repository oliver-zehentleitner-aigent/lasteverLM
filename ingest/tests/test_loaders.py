import pytest

from lasteverlm_ingest.loaders import LoaderError, LoaderRegistry, default_registry
from lasteverlm_ingest.loaders.pdf import PdfLoader
from lasteverlm_ingest.loaders.text import TextLoader


def minimal_pdf(pages: list[str]) -> bytes:
    """A hand-built PDF with one Helvetica line per page."""
    objects: list[bytes] = []
    first_page_obj = 4
    kids = [f"{first_page_obj + 2 * i} 0 R" for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, line in enumerate(pages):
        page_obj = first_page_obj + 2 * i
        content = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_obj + 1} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>stream\n" % len(content) + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_text_utf8_with_bom_and_crlf():
    passages = TextLoader().load("﻿Erste Zeile\r\nZweite Zeile\r\n".encode())
    assert passages == [type(passages[0])(text="Erste Zeile\nZweite Zeile", page=None)]


def test_text_latin1_fallback():
    assert TextLoader().load("Grüße".encode("latin-1"))[0].text == "Grüße"


def test_text_empty_is_an_error():
    with pytest.raises(LoaderError, match="no text"):
        TextLoader().load(b"  \n ")


def test_pdf_one_passage_per_page_with_text():
    passages = PdfLoader().load(minimal_pdf(["Hello ingest", "", "Page three"]))
    assert [(p.page, p.text) for p in passages] == [(1, "Hello ingest"), (3, "Page three")]


def test_pdf_without_text_is_an_error():
    with pytest.raises(LoaderError, match="no extractable text"):
        PdfLoader().load(minimal_pdf([""]))


def test_pdf_garbage_is_an_error():
    with pytest.raises(LoaderError):
        PdfLoader().load(b"this is not a pdf")


def test_registry_kinds_and_unknown_kind():
    registry = default_registry()
    assert registry.kinds == {"pdf", "text"}
    with pytest.raises(LoaderError, match="no loader"):
        LoaderRegistry().get("url")
