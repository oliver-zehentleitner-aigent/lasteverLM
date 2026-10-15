"""Flashcards: a front (a term or a question) and a back (what the material
says about it), optionally a hint. The back carries the claim: each card is
one unit, checked like a quiz answer, its front giving the context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput, Unit
from ._base import CITE_RULE, JsonGenerator
from .quiz import AUDIENCE

# one per value of ``options.DIFFICULTIES``
DIFFICULTY: dict[str, str] = {
    "easy": "Easy: the main terms and points, stated plainly.",
    "medium": "Medium: main points and specific details, names and numbers.",
    "hard": ("Hard: specifics, relations between points and the conclusions the material draws."),
}
# output tokens per card (front, back, hint, refs) and the floor
TOKENS_PER_CARD, MIN_BUDGET = 150, 4000


class Card(BaseModel):
    front: str = Field(min_length=1, max_length=300)
    back: str = Field(min_length=1, max_length=600)
    hint: str | None = Field(default=None, max_length=200)
    refs: list[int] = Field(default_factory=list, max_length=8)


class Deck(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # room above the largest count, so a model that writes one too many is cut, not failed
    cards: list[Card] = Field(min_length=1, max_length=60)


def deck_schema(count: int) -> type[Deck]:
    """A deck of the number of cards asked for: fewer is a schema miss (the
    corrective retry names it), more are cut to the first ``count``."""

    class Counted(Deck):
        @model_validator(mode="after")
        def _the_count(self) -> Counted:
            if len(self.cards) < count:
                raise ValueError(f"{len(self.cards)} cards, but exactly {count} were asked for")
            self.cards = self.cards[:count]
            return self

    return Counted


class FlashcardsGenerator(JsonGenerator):
    kind: OutputKind = "flashcards"
    focus_query: str = "key terms, definitions, facts, names, numbers"
    schema: type[BaseModel] = Deck
    # 2: every fitting source used, an unused one named
    prompt_version: str = "3"  # 3: every detail cited, one no passage states left out
    instructions: str = ""

    def prompt(self, options: Mapping[str, Any]) -> tuple[str, type[BaseModel]]:
        count = int(options.get("card_count", 15))
        return (
            f"Write exactly {count} flashcards that help learn the material. A card's front "
            "is a term or a short question; its back is what the material says about it, in "
            'one or two sentences; an optional "hint" helps without giving the back away. '
            f"{DIFFICULTY[options.get('difficulty', 'medium')]} "
            f"{AUDIENCE[options.get('audience', 'adults')]} {CITE_RULE} Each card lists in "
            '"refs" the passages its back comes from. Reply as {"title": "...", "cards": '
            '[{"front": "...", "back": "...", "hint": null or "...", "refs": [n, ...]}]}.',
            deck_schema(count),
        )

    def budget(self, options: Mapping[str, Any]) -> int:
        return max(MIN_BUDGET, TOKENS_PER_CARD * int(options.get("card_count", 15)))

    def unit_lists(self, document: BaseModel) -> tuple[str, ...]:
        return ("cards",)

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Deck)
        lines = [document.title, ""]
        cards: list[dict[str, Any]] = []
        units: list[Unit] = []
        for card in document.cards:
            target: dict[str, Any] = {"front": card.front, "back": card.back}
            if card.hint:
                target["hint"] = card.hint
            cards.append(target)
            # the back is the claim; the front says what it is about
            units.append(Unit(target, f"{card.front} {card.back}", card.refs))
            lines += [f"Q: {card.front}", f"A: {card.back}"]
        return GeneratedOutput(
            title=document.title,
            content={"cards": cards},
            index_text="\n".join(lines),
            units=units,
        )
