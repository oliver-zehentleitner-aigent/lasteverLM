from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import OutputKind
from ..models import GeneratedOutput
from ._base import JsonGenerator


class Fact(BaseModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class Section(BaseModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Infographic(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    headline: str = Field(min_length=1)
    facts: list[Fact] = Field(min_length=1, max_length=12)
    sections: list[Section] = Field(min_length=1, max_length=8)


class InfographicGenerator(JsonGenerator):
    kind: OutputKind = "infographic"
    focus_query: str = "striking numbers, key facts, the one-line message"
    schema: type[BaseModel] = Infographic
    instructions: str = (
        "Design an infographic from the material: one headline, 4 to 8 key facts as short "
        "label/value pairs (numbers where the material has them), and 3 to 5 short sections "
        'of two or three sentences. Reply as {"title", "headline", "facts": [{"label", '
        '"value"}], "sections": [{"title", "text"}]}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Infographic)
        lines = [document.title, document.headline, ""]
        lines += [f"{f.label}: {f.value}" for f in document.facts]
        lines += [f"\n{s.title}\n{s.text}" for s in document.sections]
        return GeneratedOutput(
            title=document.title,
            content={
                "headline": document.headline,
                "facts": [f.model_dump() for f in document.facts],
                "sections": [s.model_dump() for s in document.sections],
            },
            index_text="\n".join(lines),
        )
