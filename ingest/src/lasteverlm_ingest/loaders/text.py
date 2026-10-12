from __future__ import annotations

from lasteverlm_ingest.loaders import LoaderError, Passage


class TextLoader:
    """Plain text and Markdown. UTF-8 with or without BOM; anything that
    is not valid UTF-8 is read as Latin-1 rather than rejected."""

    def load(self, data: bytes) -> list[Passage]:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        text = text.replace("\r\n", "\n").strip()
        if not text:
            raise LoaderError("file contains no text")
        return [Passage(text=text)]
