from __future__ import annotations

from typing import Any

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..models import GeneratedOutput, Unit
from ._base import CITE_RULE, JsonGenerator


class Node(BaseModel):
    label: str = Field(min_length=1)
    children: list[Node] = Field(default_factory=list)
    refs: list[int] = Field(default_factory=list, max_length=8)


class Mindmap(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    root: Node


class MindmapGenerator(JsonGenerator):
    kind: OutputKind = "mindmap"
    focus_query: str = "structure, main themes and their sub-topics"
    schema: type[BaseModel] = Mindmap
    prompt_version: str = "2"  # 2: cites passages for provenance
    instructions: str = (
        "Build a mind map of the material: one root node whose label spans all sources (for "
        "sources on distinct topics, name them together, e.g. 'Linux administration: vi and "
        "VNC'), 4 to 8 main branches with at least one branch per source when the sources "
        "cover distinct topics, each with 2 to 6 sub-nodes, at most three levels deep, short "
        f'labels. {CITE_RULE} Every node below the root lists its passages in "refs". '
        'Reply as {"title": "...", "root": {"label": "...", "refs": [], "children": '
        '[{"label": "...", "refs": [n, ...], "children": [...]}, ...]}}.'
    )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        assert isinstance(document, Mindmap)
        units: list[Unit] = []
        root = _content(document.root, units, depth=0)
        return GeneratedOutput(
            title=document.title,
            content={"root": root},
            index_text=document.title + "\n" + _outline(root, 0),
            units=units,
        )


def _content(node: Node, units: list[Unit], depth: int) -> dict[str, Any]:
    """The node as content, its unit appended: the root names the whole map
    and is no claim unless it cites."""
    target: dict[str, Any] = {"label": node.label}
    units.append(Unit(target, node.label, node.refs, claim=depth > 0))
    target["children"] = [_content(child, units, depth + 1) for child in node.children]
    return target


def _outline(node: dict[str, Any], depth: int) -> str:
    line = "  " * depth + "- " + node["label"]
    return "\n".join([line] + [_outline(child, depth + 1) for child in node["children"]])
