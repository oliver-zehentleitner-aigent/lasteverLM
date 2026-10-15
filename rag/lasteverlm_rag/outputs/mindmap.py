from __future__ import annotations

from collections.abc import Mapping, Set
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
    # 3: every fitting source, unused named; 2: cites passages
    prompt_version: str = "4"  # 4: every detail cited, one no passage states left out
    instructions: str = (
        "Build a mind map of the material: one root node whose label spans all sources (for "
        "sources on distinct topics, name them together, e.g. 'Linux administration: vi and "
        "VNC'), 4 to 8 main branches with at least one branch per source when the sources "
        "cover distinct topics, each with 2 to 6 sub-nodes, at most three levels deep, short "
        f'labels. {CITE_RULE} Every node below the root lists its passages in "refs". '
        'Reply as {"title": "...", "root": {"label": "...", "refs": [], "children": '
        '[{"label": "...", "refs": [n, ...], "children": [...]}, ...]}}.'
    )

    # -- editing: a unit is a node, in pre-order; the root is unit 0 ----------

    def editable(self, document: BaseModel, index: int) -> dict[str, Any]:
        assert isinstance(document, Mindmap)
        node = _preorder(document.root)[index]
        return {"label": node.label, "refs": node.refs}

    def edit(self, document: BaseModel, index: int, fields: Mapping[str, Any]) -> BaseModel:
        assert isinstance(document, Mindmap)
        root = document.root.model_copy(deep=True)
        node = _preorder(root)[index]
        revised = Node.model_validate({**fields, "children": []})
        node.label, node.refs = revised.label, revised.refs
        return document.model_copy(update={"root": root})

    def remove(self, document: BaseModel, indexes: Set[int]) -> BaseModel:
        """Without those nodes; a removed node's children take its place."""
        assert isinstance(document, Mindmap)
        root = document.root.model_copy(deep=True)
        gone = {id(n) for i, n in enumerate(_preorder(root)) if i in indexes and i > 0}

        def prune(node: Node) -> list[Node]:
            children = [kept for child in node.children for kept in prune(child)]
            if id(node) in gone:
                return children
            node.children = children
            return [node]

        prune(root)
        return document.model_copy(update={"root": root})

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


def _preorder(node: Node) -> list[Node]:
    """The nodes in unit order: a node, then its children's subtrees."""
    return [node] + [n for child in node.children for n in _preorder(child)]


def _outline(node: dict[str, Any], depth: int) -> str:
    line = "  " * depth + "- " + node["label"]
    return "\n".join([line] + [_outline(child, depth + 1) for child in node["children"]])
