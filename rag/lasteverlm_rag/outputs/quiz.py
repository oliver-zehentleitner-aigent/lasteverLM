from __future__ import annotations

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field, model_validator

from ..models import GeneratedOutput
from ._base import JsonGenerator


class Question(BaseModel):
    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)
    answer: str = Field(min_length=1)
    explanation: str = ""

    @model_validator(mode="after")
    def answer_is_an_option(self) -> Question:
        if self.answer not in self.options:
            raise ValueError("answer must be one of the options")
        return self


class Quiz(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    questions: list[Question] = Field(min_length=1, max_length=30)


class QuizGenerator(JsonGenerator):
    kind: OutputKind = "quiz"
    focus_query: str = "key facts, definitions, numbers, names"
    schema: type[BaseModel] = Quiz
    instructions: str = (
        "Write a multiple-choice quiz of 8 to 12 questions that tests understanding of the "
        "material. Each question has 4 options, exactly one correct answer that is copied "
        'verbatim into "answer", and a one-sentence explanation. Reply as '
        '{"title": "...", "questions": [{"question", "options", "answer", "explanation"}]}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Quiz)
        lines = [document.title, ""]
        for i, q in enumerate(document.questions, start=1):
            lines.append(f"{i}. {q.question}")
            lines.append(f"Answer: {q.answer}. {q.explanation}".strip())
        return GeneratedOutput(
            title=document.title,
            content={"questions": [q.model_dump() for q in document.questions]},
            index_text="\n".join(lines),
        )
