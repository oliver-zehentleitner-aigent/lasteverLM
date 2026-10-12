"""Source loaders: turn the raw bytes of a source into text passages.

One loader per source kind, found through `LoaderRegistry`. The registry
is the extension point for kinds that are not implemented yet (url,
image): add a loader, register it under its kind, nothing else changes.
"""

from __future__ import annotations

from typing import Protocol

from lasteverlm_core import Passage

__all__ = [
    "LoaderError",
    "LoaderRegistry",
    "Passage",
    "SourceLoader",
    "default_registry",
]


class LoaderError(Exception):
    """The source could not be read; the message is shown to the user."""


class SourceLoader(Protocol):
    def load(self, data: bytes) -> list[Passage]: ...


class LoaderRegistry:
    def __init__(self) -> None:
        self._loaders: dict[str, SourceLoader] = {}

    def register(self, kind: str, loader: SourceLoader) -> None:
        self._loaders[kind] = loader

    def get(self, kind: str) -> SourceLoader:
        try:
            return self._loaders[kind]
        except KeyError:
            raise LoaderError(f"no loader for source kind {kind!r}") from None

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._loaders)


def default_registry() -> LoaderRegistry:
    from lasteverlm_ingest.loaders.pdf import PdfLoader
    from lasteverlm_ingest.loaders.text import TextLoader

    registry = LoaderRegistry()
    registry.register("pdf", PdfLoader())
    registry.register("text", TextLoader())
    return registry
