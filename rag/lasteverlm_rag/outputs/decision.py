"""Decision output: a question answered from the notebook's sources.

Two independent calls over the same numbered passages:

- the platform's decision model gives the number (``model_answer``): the
  probability of "yes", or the chosen option or level with its distribution
  and confidence;
- the LLM, which never sees that number, writes a short verdict, evidence
  for and against (each item citing passages, checked like every other
  kind's units) and the gaps a confident answer would need filled; for a
  choice or a scale it names the option its evidence argues about
  (``llm_choice``).

``agreement`` compares the number with the balance of supported evidence
and is shown whatever it says. Without supported evidence on either side
the verdict is "The sources do not decide this.", whatever the number.
"""

from __future__ import annotations

from typing import Any, Literal

from lasteverlm_core import OutputKind
from pydantic import BaseModel, Field

from ..models import GeneratedOutput, Passage, Unit
from ._base import CITE_RULE, JsonGenerator

UNDECIDED_TEXT = "The sources do not decide this."
YES_THRESHOLD, NO_THRESHOLD = 0.6, 0.4
EVIDENCE_MAX = 8
GAPS_MAX = 6

Agreement = Literal["consistent", "conflicting", "unclear", "undecided"]


class EvidenceItem(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    refs: list[int] = Field(default_factory=list, max_length=8)


class Evidence(BaseModel):
    verdict_text: str = Field(min_length=1, max_length=600)
    llm_choice: str | None = None
    evidence_for: list[EvidenceItem] = Field(default_factory=list, max_length=EVIDENCE_MAX)
    evidence_against: list[EvidenceItem] = Field(default_factory=list, max_length=EVIDENCE_MAX)
    gaps: list[str] = Field(default_factory=list, max_length=GAPS_MAX)


def evidence_instructions(question: str, decision_type: str, labels: list[str]) -> str:
    """The LLM's task: the question in its type, never the decision model's answer."""
    if decision_type == "yes_no":
        task = (
            "Answer the yes/no question below from the material. evidence_for supports "
            '"yes", evidence_against supports "no". Leave "llm_choice" null.'
        )
    else:
        kind = "option" if decision_type == "choice" else "level (they are ordered, lowest first)"
        listed = "; ".join(f'"{label}"' for label in labels)
        task = (
            f"Pick the {kind} the material supports best, copied verbatim into "
            f'"llm_choice", from: {listed}. evidence_for supports your pick, '
            "evidence_against speaks against it or for another."
        )
    return (
        f'Question: {question}\n\n{task} Write "verdict_text" as one or two sentences. '
        f"{CITE_RULE} Each evidence item is one statement with its passage numbers in "
        '"refs". List in "gaps" what the material does not say that a confident answer '
        "would need; an empty list when nothing is missing. Do not invent evidence: an "
        "empty side is a valid answer. "
        'Reply as {"verdict_text": "...", "llm_choice": null or "...", "evidence_for": '
        '[{"text": "...", "refs": [n, ...]}], "evidence_against": [...], "gaps": ["..."]}.'
    )


class DecisionGenerator(JsonGenerator):
    """The LLM half of a decision; the service runs the decision model and
    joins both with ``decision_content``."""

    kind: OutputKind = "decision"
    # the job's question is the focus query (see ``focus``)
    focus_query: str = "the decision question"
    schema: type[BaseModel] = Evidence
    instructions: str = ""
    prompt_version: str = "1"
    max_tokens: int = 3000

    def prompt(self, style: str | None) -> tuple[str, type[BaseModel]]:
        raise NotImplementedError("a decision is prompted through evidence_prompt")

    def evidence_prompt(self, options: dict[str, Any]) -> tuple[str, type[BaseModel]]:
        labels = options.get("choices") or options.get("levels") or []
        return (
            evidence_instructions(options["question"], options["decision_type"], labels),
            Evidence,
        )

    def to_output(self, document: BaseModel) -> GeneratedOutput:
        raise NotImplementedError("a decision is joined by decision_content")


def decision_content(
    options: dict[str, Any], model_answer: dict[str, Any], evidence: Evidence
) -> tuple[dict[str, Any], list[Unit]]:
    """The content (before the support check) and its units: every evidence
    item is one. ``finish_decision`` sets the agreement after the check."""
    labels = options.get("choices") or options.get("levels") or []
    llm_choice = evidence.llm_choice if evidence.llm_choice in labels else None
    pro = [{"text": e.text} for e in evidence.evidence_for]
    con = [{"text": e.text} for e in evidence.evidence_against]
    units = [
        Unit(target, e.text, e.refs)
        for target, e in zip(
            pro + con, evidence.evidence_for + evidence.evidence_against, strict=True
        )
    ]
    content: dict[str, Any] = {
        "question": options["question"],
        "decision_type": options["decision_type"],
        "model_answer": model_answer,
        "verdict_text": " ".join(evidence.verdict_text.split()),
        "evidence_for": pro,
        "evidence_against": con,
        "gaps": [" ".join(g.split()) for g in evidence.gaps if g.strip()],
    }
    if options["decision_type"] != "yes_no":
        content["llm_choice"] = llm_choice
    return content, units


def finish_decision(content: dict[str, Any]) -> str | None:
    """Set ``agreement`` and ``agreement_note`` from the checked evidence;
    returns the LLM's verdict when it is replaced (undecided), for the log."""
    pro = sum(e.get("support") == "supported" for e in content["evidence_for"])
    con = sum(e.get("support") == "supported" for e in content["evidence_against"])
    agreement, note = _agreement(content, pro, con)
    content["agreement"], content["agreement_note"] = agreement, note
    if agreement == "undecided":
        replaced = str(content["verdict_text"])
        content["verdict_text"] = UNDECIDED_TEXT
        return replaced
    return None


def _agreement(content: dict[str, Any], pro: int, con: int) -> tuple[Agreement, str]:
    if pro == 0 and con == 0:
        return "undecided", "No evidence item is supported by the passages it cites."
    balance = f"{pro} supported for, {con} against"
    answer = content["model_answer"]
    if content["decision_type"] == "yes_no":
        p = float(answer["probability_yes"])
        if (p >= YES_THRESHOLD and pro > con) or (p <= NO_THRESHOLD and con > pro):
            return "consistent", f"The model says {p:.0%} yes; the evidence: {balance}."
        if (p >= YES_THRESHOLD and con > pro) or (p <= NO_THRESHOLD and pro > con):
            return "conflicting", f"The model says {p:.0%} yes; the evidence: {balance}."
        return "unclear", f"The model says {p:.0%} yes; the evidence: {balance}."
    model_pick = (
        answer.get("choice") if content["decision_type"] == "choice" else answer.get("level")
    )
    llm_pick = content.get("llm_choice")
    said = f"The model picks {model_pick!r}, the evidence argues for {llm_pick!r} ({balance})."
    if llm_pick is None:
        return "unclear", f"The evidence names no option of the list ({balance})."
    if model_pick == llm_pick and pro > con:
        return "consistent", said
    if (model_pick != llm_pick and pro > con) or (model_pick == llm_pick and con > pro):
        return "conflicting", said
    return "unclear", said


# -- the decision model's side -----------------------------------------------

QUESTION_ID = "decision"
STATE_VERSION = "decision-state-v1"


def decision_state(question: str, passages: list[Passage]) -> dict[str, Any]:
    """What the decision model decides on: the question and the numbered
    passages, the same material the evidence cites."""
    return {
        "question": question,
        "passages": [
            {"n": p.n, "source": p.source_name, "page": p.page, "text": p.text} for p in passages
        ],
    }


def decision_question(options: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The question in the platform's shape for the chosen type."""
    question: dict[str, Any] = {"instructions": options["question"]}
    if options["decision_type"] == "yes_no":
        question["type"] = "noul"
    elif options["decision_type"] == "choice":
        question.update(type="choice", criteria={label: None for label in options["choices"]})
    else:
        question.update(type="score", criteria=list(options["levels"]))
    return {QUESTION_ID: question}


def model_answer(options: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """The platform's answer, normalised for the content: probabilities in
    0..1, a scale's distribution keyed by level label, its score the
    probability-weighted level index (0 = lowest)."""
    if options["decision_type"] == "yes_no":
        p = float(raw["noul"])
        return {"probability_yes": p, "answer": "yes" if p >= 0.5 else "no"}
    if options["decision_type"] == "choice":
        return {
            "choice": raw["choice"],
            "distribution": {k: float(v) for k, v in raw["probabilities"].items()},
            "confidence": float(raw["confidence"]),
        }
    levels = list(options["levels"])
    legend = {int(k): v for k, v in raw["legend"].items()}
    score = float(raw["score"])
    nearest = min(max(round(score), 0), len(levels) - 1)
    return {
        "level": legend.get(nearest, levels[nearest]),
        "score": score,
        "legend": levels,
        "distribution": {
            legend.get(int(k), levels[int(k)]): float(v) for k, v in raw["probabilities"].items()
        },
        "confidence": float(raw["confidence"]),
    }


def decision_title(question: str) -> str:
    return question if len(question) <= 200 else question[:199] + "…"


def decision_index_text(content: dict[str, Any]) -> str:
    """What chat can retrieve and cite: the question, the verdict and the evidence."""
    lines = [content["question"], "", content["verdict_text"]]
    lines += [f"For: {e['text']}" for e in content["evidence_for"]]
    lines += [f"Against: {e['text']}" for e in content["evidence_against"]]
    lines += [f"Not in the sources: {g}" for g in content["gaps"]]
    return "\n".join(lines)
