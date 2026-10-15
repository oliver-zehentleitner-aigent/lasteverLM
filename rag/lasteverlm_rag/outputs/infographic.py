from __future__ import annotations

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..models import GeneratedOutput, Unit
from ._base import CITE_RULE, JsonGenerator


class Fact(BaseModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    refs: list[int] = Field(default_factory=list, max_length=8)


class Section(BaseModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    refs: list[int] = Field(default_factory=list, max_length=8)


class Infographic(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    headline: str = Field(min_length=1)
    facts: list[Fact] = Field(min_length=1, max_length=12)
    sections: list[Section] = Field(min_length=1, max_length=8)


class InfographicGenerator(JsonGenerator):
    kind: OutputKind = "infographic"
    focus_query: str = "striking numbers, key facts, the one-line message"
    schema: type[BaseModel] = Infographic
    prompt_version: str = "3"  # 3: every fitting source, unused named; 2: cites passages
    instructions: str = (
        "Design an infographic from the material: one headline, 4 to 8 key facts as short "
        "label/value pairs (numbers where the material has them), and 3 to 5 short sections "
        f"of two or three sentences. {CITE_RULE} Each fact and each section lists its "
        'passage numbers in "refs". Reply as {"title", "headline", "facts": [{"label", '
        '"value", "refs": [n, ...]}], "sections": [{"title", "text", "refs": [n, ...]}]}.'
    )

    def unit_lists(self, document: BaseModel) -> tuple[str, ...]:
        return ("facts", "sections")

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Infographic)
        lines = [document.title, document.headline, ""]
        lines += [f"{f.label}: {f.value}" for f in document.facts]
        lines += [f"\n{s.title}\n{s.text}" for s in document.sections]
        facts = [{"label": f.label, "value": f.value} for f in document.facts]
        sections = [{"title": s.title, "text": s.text} for s in document.sections]
        units = [
            Unit(target, f"{f.label}: {f.value}", f.refs)
            for target, f in zip(facts, document.facts, strict=True)
        ] + [
            Unit(target, f"{s.title}. {s.text}", s.refs)
            for target, s in zip(sections, document.sections, strict=True)
        ]
        return GeneratedOutput(
            title=document.title,
            content={"headline": document.headline, "facts": facts, "sections": sections},
            index_text="\n".join(lines),
            units=units,
        )
