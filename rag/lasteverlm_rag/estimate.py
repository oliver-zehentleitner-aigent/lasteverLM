"""What a user action would charge before it runs, for the UI to show.

An action is a list of model calls. Each call gets assumed token counts
in a low and a high case (below, documented as assumptions; the real
counts depend on the material). Each call is priced with core's
``cost_cents`` (US cents), converted at the pricing rules' exchange rate
and charged with the action's margin in euro cents (``PricingRules``),
and the action's fixed fee is added once, as core books it once per
action. This is an estimate, never a quote: the booking uses
the real counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from lasteverlm_core import ModelPrices, PricingRules, cost_cents

from .judging import MAX_ROUNDS
from .outputs import OutputGenerator
from .outputs._base import JsonGenerator
from .suggestions import NOTEBOOK_SUGGESTIONS_MAX_TOKENS

# -- assumptions (low, high) ------------------------------------------------------
QUERY_TOKENS = 30  # a question or focus query, embedded
PROMPT_TOKENS = (3000, 9000)  # summaries + passages (+ history) a model reads
ANSWER_TOKENS = (150, 1024)  # a chat answer (ANSWER_MAX_TOKENS)
SUMMARY_TOKENS = (300, 3000)  # a notebook's source summaries, for its starting questions
TTS_SECONDS = (180, 300)  # an audio output: three to five minutes
SAMPLE_SECONDS = (3, 8)  # a voice preview: one or two sentences
# claim units an output has, per kind; a quiz has its question count
UNITS: dict[str, tuple[int, int]] = {
    "report": (6, 16),
    "table": (6, 20),
    "mindmap": (12, 30),
    "infographic": (7, 13),
    "audio": (8, 30),
    "decision": (2, 10),
}
JUDGE_TOKENS_IN = (500, 1500)  # one claim and its passages
JUDGE_TOKENS_OUT = (60, 500)  # a verdict; some judge models reason first
# one failing unit in a revision call: its fields, reason and passages in, the revision out
REVISE_TOKENS_IN_PER_UNIT, REVISE_TOKENS_OUT_PER_UNIT = 800, 200


@dataclass(frozen=True)
class Call:
    model: str
    tokens_in: int
    tokens_out: int = 0


@dataclass(frozen=True)
class Models:
    """The models each call goes to, from the settings."""

    llm: str
    embedding: str
    decision: str
    tts: str | None
    judges: Mapping[str, str]


class CannotEstimate(ValueError):
    """The request names no action this service runs, or misses what it needs."""


def output_calls(
    kind: str,
    options: Mapping[str, Any],
    generator: OutputGenerator,
    models: Models,
    case: int,
) -> list[Call]:
    """The calls of one output job; ``case`` 0 is low, 1 is high."""
    if kind == "chart":
        # made from picked candidates without a model call; only the index
        return [Call(models.embedding, 2000 * (case + 1))]
    assert isinstance(generator, JsonGenerator)
    written = generator.budget(options) // (4 if case == 0 else 1)
    calls = [Call(models.embedding, QUERY_TOKENS)]
    if kind == "decision":
        calls.append(Call(models.decision, PROMPT_TOKENS[case]))
    calls.append(Call(models.llm, PROMPT_TOKENS[case], written))
    calls.append(Call(models.embedding, written))  # the index of the generated text
    if kind == "audio":
        if models.tts is None:
            raise CannotEstimate("audio: text-to-speech is not available on this deployment")
        calls.append(Call(models.tts, TTS_SECONDS[case]))
    level = options.get("judge")
    if level:
        calls += judge_calls(kind, options, models, str(level), case, revise=True)
    return calls


def judge_calls(
    kind: str,
    options: Mapping[str, Any],
    models: Models,
    level: str,
    case: int,
    *,
    revise: bool,
) -> list[Call]:
    """Low: every unit judged once and passing. High: every unit failing
    every round, so judged ``MAX_ROUNDS`` times, with a revision call of
    all of them between rounds (only in generation)."""
    model = models.judges.get(level)
    if model is None:
        raise CannotEstimate(f"judge: unknown level {level!r}")
    units = int(options.get("question_count", 10)) if kind == "quiz" else UNITS[kind][case]
    rounds = 1 if case == 0 or not revise else MAX_ROUNDS
    judged = [Call(model, JUDGE_TOKENS_IN[case], JUDGE_TOKENS_OUT[case])] * (units * rounds)
    revisions = [
        Call(models.llm, units * REVISE_TOKENS_IN_PER_UNIT, units * REVISE_TOKENS_OUT_PER_UNIT)
    ] * (rounds - 1)
    return judged + revisions


def action_calls(action: str, options: Mapping[str, Any], models: Models, case: int) -> list[Call]:
    """The calls of an action that is not an output."""
    if action == "chat_answer" and options.get("suggestions"):
        # a notebook's starting questions: one call over the source summaries
        return [Call(models.llm, SUMMARY_TOKENS[case], NOTEBOOK_SUGGESTIONS_MAX_TOKENS)]
    if action == "chat_answer":
        return [
            Call(models.embedding, QUERY_TOKENS),
            Call(models.llm, PROMPT_TOKENS[case], ANSWER_TOKENS[case]),
        ]
    if action == "chart_propose":
        return [Call(models.embedding, QUERY_TOKENS), Call(models.llm, PROMPT_TOKENS[case], 6000)]
    if action == "voice_sample":
        if models.tts is None:
            raise CannotEstimate("voice_sample: text-to-speech is not available on this deployment")
        return [Call(models.tts, SAMPLE_SECONDS[case])]
    if action == "judge":
        kind = str(options.get("kind", "report"))
        if kind not in UNITS and kind != "quiz":
            raise CannotEstimate(f"judge: cannot judge a {kind}")
        return judge_calls(kind, options, models, str(options.get("level")), case, revise=False)
    raise CannotEstimate(f"no estimate for action {action!r}")


def charge(
    prices: ModelPrices, rules: PricingRules, action: str, calls: list[Call]
) -> tuple[Decimal, Decimal, Decimal]:
    """The calls' cost in US cents and in euro cents, and their charge in
    euro cents with the action's fee counted once. Raises
    ``ExchangeRateMissingError`` when the rules have no rate."""
    cost_usd = sum(
        (cost_cents(prices, c.model, c.tokens_in, c.tokens_out) for c in calls), Decimal(0)
    )
    cost_eur = rules.cost_eur_cents(cost_usd)
    return cost_usd, cost_eur, rules.charge_cents(action, cost_eur) + rules.fixed_cents(action)


def estimate(
    prices: ModelPrices,
    rules: PricingRules,
    action: str,
    low: list[Call],
    high: list[Call],
) -> dict[str, Any]:
    usd_low, eur_low, charge_low = charge(prices, rules, action, low)
    usd_high, eur_high, charge_high = charge(prices, rules, action, high)
    return {
        "action": action,
        # what the user pays, in euro cents like their credit
        "charge_cents_min": _cents(charge_low, ROUND_FLOOR),
        "charge_cents_max": _cents(charge_high, ROUND_CEILING),
        "cost_eur_cents_min": _cents(eur_low, ROUND_FLOOR),
        "cost_eur_cents_max": _cents(eur_high, ROUND_CEILING),
        "cost_usd_cents_min": _cents(usd_low, ROUND_FLOOR),
        "cost_usd_cents_max": _cents(usd_high, ROUND_CEILING),
    }


def _cents(value: Decimal, rounding: str) -> float:
    """To a hundredth of a cent, rounded outwards so the range holds."""
    return float(value.quantize(Decimal("0.01"), rounding=rounding))
