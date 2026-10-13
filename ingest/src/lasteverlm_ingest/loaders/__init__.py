"""Source loaders: turn the raw bytes of a source into text passages.

One loader per source kind, found through `LoaderRegistry`. The registry
is the extension point for new kinds: add a loader, register it under
its kind, nothing else changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lasteverlm_core import Passage, Usage

if TYPE_CHECKING:
    from lasteverlm_ingest.loaders.image import ImageLoader

__all__ = [
    "LoaderError",
    "LoaderRegistry",
    "ModelLoader",
    "Passage",
    "SourceLoader",
    "TransientLoaderError",
    "default_registry",
]


class LoaderError(Exception):
    """The source could not be read; the message is shown to the user."""


class TransientLoaderError(Exception):
    """Reading failed in a way that may pass on a later attempt (a
    timeout, a server error); the message is shown to the user."""


class SourceLoader(Protocol):
    def load(self, data: bytes) -> list[Passage]: ...


@runtime_checkable
class ModelLoader(Protocol):
    """A loader that reads the source with a billed model call. The
    worker checks the credit before calling it and records the usage it
    returns."""

    @property
    def model(self) -> str: ...

    def load_with_usage(self, data: bytes) -> tuple[list[Passage], Usage]: ...


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


def default_registry(
    *, max_url_bytes: int = 20 * 1024 * 1024, image: ImageLoader | None = None
) -> LoaderRegistry:
    from lasteverlm_ingest.loaders.pdf import PdfLoader
    from lasteverlm_ingest.loaders.text import TextLoader
    from lasteverlm_ingest.loaders.url import Fetcher, UrlLoader

    pdf, text = PdfLoader(), TextLoader()
    registry = LoaderRegistry()
    registry.register("pdf", pdf)
    registry.register("text", text)
    registry.register(
        "url", UrlLoader(fetch=Fetcher(max_bytes=max_url_bytes).fetch, text=text, pdf=pdf)
    )
    if image is not None:
        registry.register("image", image)
    return registry
