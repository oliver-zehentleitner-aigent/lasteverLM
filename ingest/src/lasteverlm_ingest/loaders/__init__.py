"""Source loaders: turn the raw bytes of a source into text passages.

One loader per source kind, found through `LoaderRegistry`. The registry
is the extension point for new kinds: add a loader, register it under
its kind, nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lasteverlm_core import Passage, Usage

if TYPE_CHECKING:
    from lasteverlm_ingest.loaders.image import VisionReader

__all__ = [
    "Bill",
    "LoaderError",
    "LoaderRegistry",
    "ModelLoader",
    "Passage",
    "SourceLoader",
    "TransientLoaderError",
    "default_registry",
    "loader_key",
]


class LoaderError(Exception):
    """The source could not be read; the message is shown to the user."""


class TransientLoaderError(Exception):
    """Reading failed in a way that may pass on a later attempt (a
    timeout, a server error); the message is shown to the user."""


class SourceLoader(Protocol):
    def load(self, data: bytes) -> list[Passage]: ...


# Records one model call's usage; raises when the owner's credit is gone,
# which stops the loader before its next call.
Bill = Callable[[Usage], None]


@runtime_checkable
class ModelLoader(Protocol):
    """A loader that reads the source with billed model calls. The worker
    checks the credit before calling it; the loader hands every call's
    usage to `bill` as soon as the call returns."""

    def load_billed(self, data: bytes, bill: Bill) -> list[Passage]: ...


class LoaderRegistry:
    def __init__(self) -> None:
        self._loaders: dict[str, SourceLoader | ModelLoader] = {}

    def register(self, kind: str, loader: SourceLoader | ModelLoader) -> None:
        self._loaders[kind] = loader

    def get(self, kind: str) -> SourceLoader | ModelLoader:
        try:
            return self._loaders[kind]
        except KeyError:
            raise LoaderError(f"no loader for source kind {kind!r}") from None

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._loaders)


def loader_key(kind: str, capture: str | None) -> str:
    """The registry key for a library source: PDFs per capture mode
    (`pdf` is the text layer, `pdf:vision`, `pdf:auto`), everything else
    by kind."""
    if kind == "pdf" and capture in ("vision", "auto"):
        return f"pdf:{capture}"
    return kind


def default_registry(
    *,
    max_url_bytes: int = 20 * 1024 * 1024,
    vision: VisionReader | None = None,
    pdf_vision_max_pages: int = 100,
) -> LoaderRegistry:
    """Without a vision reader there are no image sources and PDFs are
    read by their text layer only."""
    from lasteverlm_ingest.loaders.image import ImageLoader
    from lasteverlm_ingest.loaders.pdf import PdfLoader, VisionPdfLoader
    from lasteverlm_ingest.loaders.text import TextLoader
    from lasteverlm_ingest.loaders.url import Fetcher, UrlLoader

    pdf, text = PdfLoader(), TextLoader()
    registry = LoaderRegistry()
    registry.register("pdf", pdf)
    registry.register("text", text)
    registry.register(
        "url", UrlLoader(fetch=Fetcher(max_bytes=max_url_bytes).fetch, text=text, pdf=pdf)
    )
    if vision is not None:
        registry.register("image", ImageLoader(vision))
        for capture in ("vision", "auto"):
            registry.register(
                f"pdf:{capture}",
                VisionPdfLoader(vision, capture, max_pages=pdf_vision_max_pages),
            )
    return registry
