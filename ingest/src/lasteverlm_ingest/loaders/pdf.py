"""PDFs in three capture modes.

`text` reads the text layer (pypdf), one passage per page that has a
legible one.
`vision` renders every page (pypdfium2) and has the vision model
transcribe it, one billed call per page. `auto` reads the text layer and
renders only the pages without one, so a scanned or a mixed PDF works and
only the pages that need the model cost a call. Page numbers are kept
for citations in every mode.
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from lasteverlm_core import Usage
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from lasteverlm_ingest.loaders import Bill, LoaderError, Passage
from lasteverlm_ingest.loaders.image import PAGE_PROMPT, VisionReader

Capture = Literal["text", "vision", "auto"]
CAPTURE_MODES: tuple[Capture, ...] = ("text", "vision", "auto")
DEFAULT_CAPTURE: Capture = "auto"

# A page with fewer visible characters than this has no usable text layer
# (a scan with a page number or a stray OCR fragment on it).
MIN_PAGE_CHARS = 20
# Nor does a page whose visible characters are mostly not letters: a font
# without a usable ToUnicode map gives pypdf its glyph codes, a salad like
# "&MM,:N K OP&M,MM P2QL" at about half letters. Prose, umlauts included,
# is above 0.9, a page of shell commands about 0.75. A page of bare
# numbers falls below too and is read by the model in auto.
MIN_LETTER_SHARE = 0.6
# Legible for the model without paying for pixels it does not need: 150
# dpi, A4 comes out at 1241 x 1754; the long edge is capped for large pages.
RENDER_DPI = 150
MAX_EDGE_PX = 2000
JPEG_QUALITY = 85
# Model calls in flight at once; usage is billed as each batch returns.
PARALLEL_PAGES = 4
# Most pages of a PDF read at all, in any mode: the text layer of every
# page is extracted, which costs worker time a 20 MB file of tiny pages
# could stretch without end. The vision cap (PDF_VISION_MAX_PAGES) is lower.
MAX_PAGES = 2000


def text_pages(data: bytes) -> list[str]:
    """The text layer of every page, '' where a page has none."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise LoaderError("PDF is encrypted")
        if len(reader.pages) > MAX_PAGES:
            raise LoaderError(f"PDF has {len(reader.pages)} pages; at most {MAX_PAGES} are read")
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except PyPdfError as exc:
        raise LoaderError(f"PDF could not be read: {exc}") from exc


def legible(page: str) -> bool:
    """True when the visible characters are mostly letters (str.isalpha,
    so any script counts); an empty page is not legible."""
    visible = [c for c in page if not c.isspace()]
    return bool(visible) and sum(c.isalpha() for c in visible) >= MIN_LETTER_SHARE * len(visible)


def pdf_page_count(data: bytes) -> int | None:
    """The number of pages, for estimating what reading the PDF costs; None
    when it cannot be read here (the worker then fails it with the reason)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return None if reader.is_encrypted else len(reader.pages)
    except Exception:
        # Only an estimate: any file pypdf cannot count is read (and, if
        # broken, failed with the reason) by the worker.
        return None


def has_text(page: str) -> bool:
    """A usable text layer: enough characters, and legible ones."""
    return sum(not c.isspace() for c in page) >= MIN_PAGE_CHARS and legible(page)


def render_page(data: bytes, index: int) -> bytes:
    """One page as a JPEG at RENDER_DPI, long edge at most MAX_EDGE_PX."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
        try:
            page = pdf[index]
            width, height = page.get_size()
            scale = min(RENDER_DPI / 72, MAX_EDGE_PX / max(width, height))
            image = page.render(scale=scale).to_pil().convert("RGB")
        finally:
            pdf.close()
    except pdfium.PdfiumError as exc:
        raise LoaderError(f"PDF page {index + 1} could not be rendered: {exc}") from exc
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


class PdfLoader:
    """The text-layer reader; `text` capture, and PDFs behind a URL."""

    def load(self, data: bytes) -> list[Passage]:
        passages = [
            Passage(text=text, page=number)
            for number, text in enumerate(text_pages(data), start=1)
            if legible(text)
        ]
        if not passages:
            raise LoaderError(
                "PDF contains no legible text (capture mode text; "
                "upload it with capture auto or vision to have the pages read)"
            )
        return passages


class VisionPdfLoader:
    """`vision` and `auto` capture: pages are rendered and read by the
    vision model, every page (`vision`) or the pages without a text layer
    (`auto`)."""

    def __init__(self, vision: VisionReader, capture: Capture, *, max_pages: int = 100) -> None:
        assert capture in ("vision", "auto")
        self._vision = vision
        self._capture = capture
        self._max_pages = max_pages

    def load_billed(self, data: bytes, bill: Bill) -> list[Passage]:
        pages = text_pages(data)
        texts: dict[int, str] = {}
        to_read: list[int] = []
        for index, text in enumerate(pages):
            if self._capture == "auto" and has_text(text):
                texts[index] = text
            else:
                to_read.append(index)
        if len(to_read) > self._max_pages:
            raise LoaderError(
                f"PDF has {len(to_read)} pages for the vision model (capture mode "
                f"{self._capture}); at most {self._max_pages} are read per upload"
            )
        with ThreadPoolExecutor(max_workers=PARALLEL_PAGES) as pool:
            for start in range(0, len(to_read), PARALLEL_PAGES):
                batch = to_read[start : start + PARALLEL_PAGES]
                # pdfium is not thread-safe: pages are rendered here, one at a
                # time (fast), and only the model calls run in parallel.
                images = [render_page(data, i) for i in batch]
                futures = [pool.submit(self._read, image) for image in images]
                failure: BaseException | None = None
                for index, future in zip(batch, futures, strict=True):
                    error = future.exception()
                    if error is not None:
                        failure = failure or error
                        continue
                    text, usage = future.result()
                    texts[index] = text
                    # Every answered call is billed, also when a sibling
                    # failed or the credit ran out on an earlier one; the
                    # first failure stops the loader before the next batch.
                    try:
                        bill(usage)
                    except Exception as exc:
                        failure = failure or exc
                if failure is not None:
                    raise failure
        passages = [Passage(text=texts[i], page=i + 1) for i in sorted(texts) if texts[i].strip()]
        if not passages:
            raise LoaderError(f"PDF holds no readable content (capture mode {self._capture})")
        return passages

    def _read(self, image: bytes) -> tuple[str, Usage]:
        return self._vision.read(image, "image/jpeg", PAGE_PROMPT)
