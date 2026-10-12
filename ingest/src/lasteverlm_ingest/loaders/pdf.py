from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from lasteverlm_ingest.loaders import LoaderError, Passage


class PdfLoader:
    """One passage per page that has extractable text. Scanned PDFs
    without a text layer yield nothing; OCR is out of scope."""

    def load(self, data: bytes) -> list[Passage]:
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise LoaderError("PDF is encrypted")
            passages = []
            for number, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    passages.append(Passage(text=text, page=number))
        except PyPdfError as exc:
            raise LoaderError(f"PDF could not be read: {exc}") from exc
        if not passages:
            raise LoaderError("PDF contains no extractable text")
        return passages
