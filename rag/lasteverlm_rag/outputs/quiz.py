from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput, Unit
from ._base import CITE_RULE, JsonGenerator


class Question(BaseModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)
    answer: str = Field(min_length=1)
    explanation: str = ""
    refs: list[int] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def answer_is_an_option(self) -> Question:
        if self.answer not in self.options:
            raise ValueError("answer must be one of the options")
        return self


class Quiz(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # room above the largest count, so a model that writes one too many is cut, not failed
    questions: list[Question] = Field(min_length=1, max_length=40)


# one per value of ``options.DIFFICULTIES`` and ``options.AUDIENCES``
DIFFICULTY: dict[str, str] = {
    "easy": "Easy: ask about the main points stated plainly; wrong options are clearly wrong.",
    "medium": ("Medium: mix main points with specific details; wrong options are plausible."),
    "hard": (
        "Hard: ask about specifics, relations between points and conclusions the material "
        "draws; wrong options are close to the right one."
    ),
}
AUDIENCE: dict[str, str] = {
    "children": "Write for children: short sentences, simple words, a friendly tone.",
    "teens": "Write for teenagers: clear everyday language, terms explained briefly.",
    "adults": "Write for adults without special knowledge of the subject.",
    "experts": "Write for experts: the subject's terminology, no basic explanations.",
}
# output tokens per question (question, four options, explanation, refs) and the floor
TOKENS_PER_QUESTION, MIN_BUDGET = 250, 4000


def quiz_schema(count: int) -> type[Quiz]:
    """A quiz of the number of questions asked for: fewer is a schema miss
    (the corrective retry names it), more are cut to the first ``count``."""

    class Counted(Quiz):
        @model_validator(mode="after")
        def _the_count(self) -> Counted:
            if len(self.questions) < count:
                raise ValueError(
                    f"{len(self.questions)} questions, but exactly {count} were asked for"
                )
            self.questions = self.questions[:count]
            return self

    return Counted


class QuizGenerator(JsonGenerator):
    kind: OutputKind = "quiz"
    focus_query: str = "key facts, definitions, numbers, names"
    schema: type[BaseModel] = Quiz
    # 3: number of questions, difficulty and audience; 2: cites passages for provenance
    prompt_version: str = "3"
    instructions: str = ""

    def prompt(self, options: Mapping[str, Any]) -> tuple[str, type[BaseModel]]:
        count = int(options.get("question_count", 10))
        return (
            f"Write a multiple-choice quiz of exactly {count} questions that tests "
            "understanding of the material. Each question has 4 options, exactly one correct "
            'answer that is copied verbatim into "answer", and a one-sentence explanation. '
            f"{DIFFICULTY[options.get('difficulty', 'medium')]} "
            f"{AUDIENCE[options.get('audience', 'adults')]} {CITE_RULE} Each question lists in "
            '"refs" the passages its answer comes from. Reply as {"title": "...", '
            '"questions": [{"question", "options", "answer", "explanation", "refs": [n, ...]}]}.',
            quiz_schema(count),
        )

    def budget(self, options: Mapping[str, Any]) -> int:
        return max(MIN_BUDGET, TOKENS_PER_QUESTION * int(options.get("question_count", 10)))

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Quiz)
        lines = [document.title, ""]
        for i, q in enumerate(document.questions, start=1):
            lines.append(f"{i}. {q.question}")
            lines.append(f"Answer: {q.answer}. {q.explanation}".strip())
        questions = [q.model_dump(exclude={"refs"}) for q in document.questions]
        # the claim of a question is its answer, with the explanation
        units = [
            Unit(target, f"{q.question} {q.answer}. {q.explanation}", q.refs)
            for target, q in zip(questions, document.questions, strict=True)
        ]
        return GeneratedOutput(
            title=document.title,
            content={"questions": questions},
            index_text="\n".join(lines),
            units=units,
        )
