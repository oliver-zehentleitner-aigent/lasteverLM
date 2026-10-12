"""Audio output: prepared, not available.

The inference platform offers no text-to-speech endpoint yet. The generator
exists so the kind is registered and the frontend can show the tile; a
request fails with a clear error instead of pretending. When a speech
endpoint exists: write the script with the LLM (a spoken-word summary),
synthesize it with ``TextToSpeech``, store the file, return ``{"url"}``.
"""

from __future__ import annotations

from ..contracts import OutputKind
from ..models import GeneratedOutput, Passage, SourceSummary
from . import CompleteFn
from ._base import GenerationFailed


class AudioGenerator:
    kind: OutputKind = "audio"
    focus_query: str = "the story of the material, told in order"

    def __init__(self, available: bool) -> None:
        self.available = available

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
    ) -> GeneratedOutput:
        raise GenerationFailed("audio: text-to-speech is not available on this deployment")
