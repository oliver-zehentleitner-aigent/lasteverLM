"""Audio output: a spoken-word script, synthesized by the service.

The generator only writes the script (title plus the text to be read
aloud). Synthesis, storage and the ``{"url"}`` content happen in the
output service, which owns the text-to-speech provider and the object
store. The script is also the output's index text, so chat can cite what
the audio says.
"""

from __future__ import annotations

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..models import GeneratedOutput, Passage, SourceSummary
from . import CompleteFn
from ._base import GenerationFailed, JsonGenerator

SCRIPT_MAX_CHARS = 6000


class AudioScript(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    script: str = Field(min_length=1, max_length=SCRIPT_MAX_CHARS)


class AudioGenerator(JsonGenerator):
    kind: OutputKind = "audio"
    focus_query: str = "the story of the material, told in order"
    schema: type[BaseModel] = AudioScript
    instructions: str = (
        "Write the script of a spoken overview of the material, to be read aloud by one "
        "narrator: three to five minutes, plain sentences, no headings, no lists, no "
        "markdown, no citation markers, no stage directions. Start with what the material "
        "is about, walk through the main points in order, end with a short wrap-up. "
        'Reply as {"title": "...", "script": "..."}.'
    )

    def __init__(self, available: bool) -> None:
        self.available = available

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
    ) -> GeneratedOutput:
        if not self.available:
            # fail before the script costs tokens nobody can listen to
            raise GenerationFailed("audio: text-to-speech is not available on this deployment")
        return super().generate(complete, notebook_title, summaries, passages)

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, AudioScript)
        return GeneratedOutput(
            title=document.title,
            content={},
            index_text=f"{document.title}\n\n{document.script}",
            speech=document.script,
        )
