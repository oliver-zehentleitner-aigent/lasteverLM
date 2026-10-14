"""Audio output: a spoken-word script, synthesized by the service.

The generator only writes the script, in one of three styles: ``overview``
(a spoken summary, one narrator), ``story`` (the material told as a
narrative, one narrator) or ``conversation`` (an interviewer asking and an
expert answering, two voices). The script comes back as turns: who speaks
(a role) and what. Synthesis, storage and the ``{"url"}`` content happen in
the output service, which owns the text-to-speech provider, the object
store and the mapping of roles to voices. The turns are the transcript
under the player, and the script is the output's index text, so chat can
cite what the audio says.
"""

from __future__ import annotations

import re
from typing import Literal

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput, Passage, SourceSummary, SpeechTurn
from . import CompleteFn
from ._base import GenerationFailed, JsonGenerator

SCRIPT_MAX_CHARS = 6000
TURN_MAX_CHARS = 1500
MAX_TURNS = 80

NARRATOR = "narrator"
SPEAKER_LABELS = {"narrator": "Narrator", "interviewer": "Interviewer", "expert": "Expert"}

_PARAGRAPH = re.compile(r"\n\s*\n")

# What every style shares: spoken text for the ear, nothing a voice would
# read out wrongly, and nothing beyond the material.
_SPOKEN = (
    "three to five minutes, plain spoken sentences, no headings, no lists, no markdown, "
    "no citation markers, no stage directions"
)


class AudioScript(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    script: str = Field(min_length=1, max_length=SCRIPT_MAX_CHARS)


class Turn(BaseModel):
    speaker: Literal["interviewer", "expert"]
    text: str = Field(min_length=1, max_length=TURN_MAX_CHARS)


class Conversation(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    turns: list[Turn] = Field(min_length=2, max_length=MAX_TURNS)

    @model_validator(mode="after")
    def _both_speak_within_the_length(self) -> Conversation:
        if {t.speaker for t in self.turns} != {"interviewer", "expert"}:
            raise ValueError("both the interviewer and the expert must speak")
        total = sum(len(t.text) for t in self.turns)
        if total > SCRIPT_MAX_CHARS:
            raise ValueError(f"the turns are {total} characters, at most {SCRIPT_MAX_CHARS}")
        return self


# one per style of ``options.AUDIO_STYLES``
INSTRUCTIONS: dict[str, str] = {
    "overview": (
        "Write the script of a spoken overview of the material, to be read aloud by one "
        f"narrator: {_SPOKEN}. Start with what the material is about, walk through the main "
        "points in order, end with a short wrap-up. Separate paragraphs with a blank line. "
        'Reply as {"title": "...", "script": "..."}.'
    ),
    "story": (
        "Write the script of a story told by one narrator: the content of the material as a "
        "narrative with a beginning, a middle and an end, "
        f"{_SPOKEN}. The narrative is the order and the framing, not the content: invent no "
        "events, people, places or facts; everything told comes from the material. "
        "Separate paragraphs with a blank line. "
        'Reply as {"title": "...", "script": "..."}.'
    ),
    "conversation": (
        "Write the script of a conversation between two speakers: an interviewer, who "
        "introduces the topic, asks questions and leads through the material, and an expert, "
        f"who answers. {_SPOKEN[0].upper() + _SPOKEN[1:]}. The expert answers only from the "
        "material and says so when it does not cover a question; the interviewer asks about "
        "the material and adds no facts of their own. The speakers do not name themselves or "
        "each other. Start with the interviewer, end with a short wrap-up. "
        'Reply as {"title": "...", "turns": [{"speaker": "interviewer" or "expert", '
        '"text": "..."}, ...]}.'
    ),
}


class AudioGenerator(JsonGenerator):
    kind: OutputKind = "audio"
    focus_query: str = "the story of the material, told in order"
    schema: type[BaseModel] = AudioScript
    instructions: str = INSTRUCTIONS["overview"]

    def __init__(self, available: bool) -> None:
        self.available = available

    def prompt(self, style: str | None) -> tuple[str, type[BaseModel]]:
        if style == "conversation":
            return INSTRUCTIONS["conversation"], Conversation
        if style == "story":
            return INSTRUCTIONS["story"], AudioScript
        return INSTRUCTIONS["overview"], AudioScript

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
        *,
        language: str | None = None,
        style: str | None = None,
    ) -> GeneratedOutput:
        if not self.available:
            # fail before the script costs tokens nobody can listen to
            raise GenerationFailed("audio: text-to-speech is not available on this deployment")
        return super().generate(
            complete, notebook_title, summaries, passages, language=language, style=style
        )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        if isinstance(document, Conversation):
            turns = [SpeechTurn(t.speaker, " ".join(t.text.split())) for t in document.turns]
        else:
            assert isinstance(document, AudioScript)
            paragraphs = [" ".join(p.split()) for p in _PARAGRAPH.split(document.script)]
            turns = [SpeechTurn(NARRATOR, p) for p in paragraphs if p]
        if not turns:
            raise GenerationFailed("audio: the script is empty")
        return GeneratedOutput(
            title=document.title,
            content={"transcript": [{"speaker": t.speaker, "text": t.text} for t in turns]},
            index_text=document.title + "\n\n" + transcript_text(turns),
            speech=turns,
        )


def transcript_text(turns: list[SpeechTurn]) -> str:
    """The script as plain text: paragraphs for one narrator, labelled lines
    for a conversation."""
    if all(t.speaker == NARRATOR for t in turns):
        return "\n\n".join(t.text for t in turns)
    return "\n\n".join(f"{SPEAKER_LABELS[t.speaker]}: {t.text}" for t in turns)
