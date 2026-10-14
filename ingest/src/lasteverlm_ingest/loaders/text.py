from __future__ import annotations

from lasteverlm_ingest.loaders import LoaderError, Passage


def decode_text(data: bytes) -> str:
    """UTF-8 with or without BOM; anything that is not valid UTF-8 is read
    as Latin-1 rather than rejected. Line ends as `\n`."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return text.replace("\r\n", "\n")


class TextLoader:
    """Plain text and Markdown, decoded by `decode_text`."""

    def load(self, data: bytes) -> list[Passage]:
        text = decode_text(data).strip()
        if not text:
            raise LoaderError("file contains no text")
        return [Passage(text=text)]
