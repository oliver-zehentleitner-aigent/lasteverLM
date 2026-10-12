"""Shared machinery for generators that ask the model for one JSON document."""

from __future__ import annotations

import json
import re
from typing import Any

from lasteverlm_core import OutputKind, ProviderError
from pydantic import BaseModel, ValidationError

from ..models import GeneratedOutput, Passage, SourceSummary
from . import CompleteFn

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

SYSTEM_RULES = """You create documents strictly from the material the user provides.

Rules:
- Use only the provided material. Do not add facts from your own knowledge.
- Write in the language the material is written in.
- "title" names this document specifically (its subject and form); never reuse the notebook's name.
- Answer with one JSON object only, no prose before or after it, no code fences.
"""


class GenerationFailed(Exception):
    """The model did not produce a document matching the kind's schema."""


class JsonGenerator:
    """Prompt once, parse and validate the JSON; on a schema failure retry once
    with the validation error appended so the model can correct itself."""

    kind: OutputKind
    focus_query: str
    instructions: str
    schema: type[BaseModel]
    max_tokens: int = 4000

    def generate(
        self,
        complete: CompleteFn,
        notebook_title: str,
        summaries: list[SourceSummary],
        passages: list[Passage],
    ) -> GeneratedOutput:
        user = render_material(notebook_title, summaries, passages) + "\n\n" + self.instructions
        system = SYSTEM_RULES
        last_error = ""
        for attempt in range(2):
            prompt = (
                user
                if attempt == 0
                else f"{user}\n\nYour previous answer was invalid: {last_error}"
            )
            text = complete(system, prompt, self.max_tokens).text
            if not text.strip():
                # no content at all is a provider failure (e.g. a reasoning model that spent
                # its budget on thinking), not a schema miss: the worker retries it
                raise ProviderError(f"{self.kind}: the model returned no content")
            try:
                document = self.schema.model_validate(parse_json(text))
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:500]
                continue
            return self.to_output(document)
        raise GenerationFailed(f"{self.kind}: model output did not match the schema: {last_error}")

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        raise NotImplementedError


def parse_json(text: str) -> Any:
    """Tolerate a fenced block or stray text around the object."""
    match = _FENCE.match(text)
    if match:
        text = match.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the model output")
    return json.loads(text[start : end + 1])


def render_material(
    notebook_title: str, summaries: list[SourceSummary], passages: list[Passage]
) -> str:
    parts = [f'Notebook: "{notebook_title}"', "", "Source summaries:"]
    for s in summaries:
        parts.append(f"- {s.name}: {s.summary}")
    if passages:
        parts += ["", "Relevant passages:"]
        for p in passages:
            where = f"{p.source_name}, page {p.page}" if p.page is not None else p.source_name
            parts.append(f"[{p.n}] ({where})\n{p.text}")
    return "\n".join(parts)
