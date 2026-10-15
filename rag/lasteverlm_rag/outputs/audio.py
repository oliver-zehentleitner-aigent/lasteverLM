"""Audio output: a spoken-word script, synthesized by the service.

The generator only writes the script, in one of four styles: ``overview``
(a spoken summary, one narrator), ``story`` (the material told as a
narrative, one narrator), ``conversation`` (an interviewer asking and an
expert answering, two voices) or ``faq`` (the questions a listener would
ask, each followed by its answer, the same two voices in strict turn).
The script comes back as turns: who speaks (a role) and what. Synthesis,
storage and the ``{"url"}`` content happen in the output service, which
owns the text-to-speech provider, the object store and the mapping of
roles to voices. The turns are the transcript under the player, and the
script is the output's index text, so chat can cite what the audio says.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput, Passage, SourceSummary, SpeechTurn, Unit
from . import CompleteFn
from ._base import CITE_RULE, GenerationFailed, JsonGenerator

SCRIPT_MAX_CHARS = 6000
TURN_MAX_CHARS = 1500
MAX_TURNS = 80

NARRATOR = "narrator"
SPEAKER_LABELS = {"narrator": "Narrator", "interviewer": "Interviewer", "expert": "Expert"}

# What every style shares: spoken text for the ear, nothing a voice would
# read out wrongly, and nothing beyond the material. The passage numbers go
# into "refs" beside the text, never into it, where the voice would read them.
_SPOKEN = (
    "three to five minutes, plain spoken sentences, no headings, no lists, no markdown, "
    "no citation markers in the text, no stage directions"
)
_REFS = (
    f'{CITE_RULE} Put the numbers in the "refs" of the paragraph or turn they support, '
    "never in its text."
)


class Paragraph(BaseModel):
    text: str = Field(min_length=1, max_length=TURN_MAX_CHARS)
    refs: list[int] = Field(default_factory=list, max_length=8)


class AudioScript(BaseModel):
    """One narrator: the script as paragraphs, each with its passage numbers."""

    title: str = Field(min_length=1, max_length=200)
    paragraphs: list[Paragraph] = Field(min_length=1, max_length=MAX_TURNS)

    @model_validator(mode="after")
    def _within_the_length(self) -> AudioScript:
        total = sum(len(p.text) for p in self.paragraphs)
        if total > SCRIPT_MAX_CHARS:
            raise ValueError(f"the paragraphs are {total} characters, at most {SCRIPT_MAX_CHARS}")
        return self


class Turn(BaseModel):
    speaker: Literal["interviewer", "expert"]
    text: str = Field(min_length=1, max_length=TURN_MAX_CHARS)
    refs: list[int] = Field(default_factory=list, max_length=8)


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


FAQ_PAIRS_MIN, FAQ_PAIRS_MAX = 5, 8


class Faq(Conversation):
    """Questions a listener would ask, each followed by its answer: the
    interviewer asks, the expert answers, strictly in turn."""

    @model_validator(mode="after")
    def _question_then_answer(self) -> Faq:
        expected = ["interviewer", "expert"] * (len(self.turns) // 2 + 1)
        if [t.speaker for t in self.turns] != expected[: len(self.turns)]:
            raise ValueError("the turns alternate: a question by the interviewer, then its answer")
        pairs = len(self.turns) // 2
        if len(self.turns) % 2 or not FAQ_PAIRS_MIN <= pairs <= FAQ_PAIRS_MAX:
            raise ValueError(
                f"{FAQ_PAIRS_MIN} to {FAQ_PAIRS_MAX} question-answer pairs, each answered"
            )
        return self


# one per style of ``options.AUDIO_STYLES``
INSTRUCTIONS: dict[str, str] = {
    "overview": (
        "Write the script of a spoken overview of the material, to be read aloud by one "
        f"narrator: {_SPOKEN}. Start with what the material is about, walk through the main "
        f"points in order, end with a short wrap-up. {_REFS} "
        'Reply as {"title": "...", "paragraphs": [{"text": "...", "refs": [n, ...]}, ...]}.'
    ),
    "story": (
        "Write the script of a story told by one narrator: the content of the material as a "
        "narrative with a beginning, a middle and an end, "
        f"{_SPOKEN}. The narrative is the order and the framing, not the content: invent no "
        "events, people, places or facts; everything told comes from the material. "
        f"{_REFS} "
        'Reply as {"title": "...", "paragraphs": [{"text": "...", "refs": [n, ...]}, ...]}.'
    ),
    "conversation": (
        "Write the script of a conversation between two speakers: an interviewer, who "
        "introduces the topic, asks questions and leads through the material, and an expert, "
        f"who answers. {_SPOKEN[0].upper() + _SPOKEN[1:]}. The expert answers only from the "
        "material and says so when it does not cover a question; the interviewer asks about "
        "the material and adds no facts of their own. The speakers do not name themselves or "
        "each other. Start with the interviewer, end with a short wrap-up. "
        f"{_REFS} An interviewer's question needs no refs. "
        'Reply as {"title": "...", "turns": [{"speaker": "interviewer" or "expert", '
        '"text": "...", "refs": [n, ...]}, ...]}.'
    ),
    "faq": (
        f"Write the script of a spoken FAQ about the material: {FAQ_PAIRS_MIN} to "
        f"{FAQ_PAIRS_MAX} questions a listener would most likely ask about it, each followed "
        "by its answer. Two speakers take turns: the interviewer asks one question, the "
        "expert answers it, then the next question. Every question comes from the material, "
        "never from outside knowledge; every answer only from the material. "
        f"{_SPOKEN[0].upper() + _SPOKEN[1:]}. The speakers do not name themselves or each "
        f"other. {_REFS} A question needs no refs. "
        'Reply as {"title": "...", "turns": [{"speaker": "interviewer", "text": "question", '
        '"refs": []}, {"speaker": "expert", "text": "answer", "refs": [n, ...]}, ...]}.'
    ),
}


class AudioGenerator(JsonGenerator):
    kind: OutputKind = "audio"
    focus_query: str = "the story of the material, told in order"
    schema: type[BaseModel] = AudioScript
    prompt_version: str = "3"  # 3: every fitting source, unused named; 2: cites passages
    instructions: str = INSTRUCTIONS["overview"]

    def __init__(self, available: bool) -> None:
        self.available = available

    def prompt(self, options: Mapping[str, Any]) -> tuple[str, type[BaseModel]]:
        style = options.get("audio_style")
        if style == "conversation":
            return INSTRUCTIONS["conversation"], Conversation
        if style == "faq":
            return INSTRUCTIONS["faq"], Faq
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
        options: Mapping[str, Any] | None = None,
    ) -> GeneratedOutput:
        if not self.available:
            # fail before the script costs tokens nobody can listen to
            raise GenerationFailed("audio: text-to-speech is not available on this deployment")
        return super().generate(
            complete, notebook_title, summaries, passages, language=language, options=options
        )

    # a revised turn keeps its speaker
    fixed_fields: tuple[str, ...] = ("speaker",)

    def unit_lists(self, document: BaseModel) -> tuple[str, ...]:
        return ("turns",) if isinstance(document, Conversation) else ("paragraphs",)

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        parts: list[tuple[str, str, list[int]]]
        if isinstance(document, Conversation):
            parts = [(t.speaker, t.text, t.refs) for t in document.turns]
        else:
            assert isinstance(document, AudioScript)
            parts = [(NARRATOR, p.text, p.refs) for p in document.paragraphs]
        turns: list[SpeechTurn] = []
        transcript: list[dict[str, Any]] = []
        units: list[Unit] = []
        for speaker, raw, refs in parts:
            text = " ".join(raw.split())
            if not text:
                continue
            target: dict[str, Any] = {"speaker": speaker, "text": text}
            turns.append(SpeechTurn(speaker, text))
            transcript.append(target)
            # a question asks; it is checked only when it cites anyway
            units.append(Unit(target, text, refs, claim=speaker != "interviewer"))
        if not turns:
            raise GenerationFailed("audio: the script is empty")
        return GeneratedOutput(
            title=document.title,
            content={"transcript": transcript},
            index_text=document.title + "\n\n" + transcript_text(turns),
            speech=turns,
            units=units,
        )


def transcript_text(turns: list[SpeechTurn]) -> str:
    """The script as plain text: paragraphs for one narrator, labelled lines
    for a conversation."""
    if all(t.speaker == NARRATOR for t in turns):
        return "\n\n".join(t.text for t in turns)
    return "\n\n".join(f"{SPEAKER_LABELS[t.speaker]}: {t.text}" for t in turns)
