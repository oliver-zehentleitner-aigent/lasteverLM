from __future__ import annotations

from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..models import GeneratedOutput
from ._base import JsonGenerator


class Node(BaseModel):
    label: str = Field(min_length=1)
    children: list[Node] = Field(default_factory=list)


class Mindmap(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    root: Node


class MindmapGenerator(JsonGenerator):
    kind: OutputKind = "mindmap"
    focus_query: str = "structure, main themes and their sub-topics"
    schema: type[BaseModel] = Mindmap
    instructions: str = (
        "Build a mind map of the material: one root node with the central theme, 4 to 8 "
        "main branches, each with 2 to 6 sub-nodes, at most three levels deep, short labels. "
        'Reply as {"title": "...", "root": {"label": "...", "children": [...]}}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Mindmap)
        return GeneratedOutput(
            title=document.title,
            content={"root": document.root.model_dump()},
            index_text=document.title + "\n" + _outline(document.root.model_dump(), 0),
        )


def _outline(node: dict[str, Any], depth: int) -> str:
    line = "  " * depth + "- " + node["label"]
    return "\n".join([line] + [_outline(child, depth + 1) for child in node["children"]])
