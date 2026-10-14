"""What adding a source costs, per nominal unit, for the public price list.

Account's price list calls this server-side and publishes only the charge. Every unit is priced
through core's billing with the current pricing rules (margin on the
cost; the action's fixed fee is reported apart, since it is booked once
per source, not per unit). The nominal sizes below are what one unit
costs in model calls; they come from measurements on the former Zeltavia demo set and
the live vision runs, and are deliberately round.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from lasteverlm_core import ExchangeRateMissingError, PricingRules, cost_cents
from pydantic import BaseModel

from lasteverlm_ingest.api.deps import worker_deps
from lasteverlm_ingest.auth import CurrentUser

router = APIRouter()

Kind = Literal["text", "url", "pdf_text", "pdf_vision", "image", "audio"]

# Embedding tokens of one page of text: a dense A4 page of prose is about
# 2,000 characters, the platform's tokenizer about four characters per
# token (the former demo field notes: 4,460 characters on 3 pages).
PAGE_TOKENS = 500
# One web page: the former demo article (Wikipedia, "Dead reckoning") is 24,348
# characters as text after the HTML is reduced, about 6,000 tokens.
WEB_PAGE_TOKENS = 6000
# One PDF page read by the vision model: 515 input and 960 output tokens,
# measured on two scanned A4 pages (context/pdf-capture.md); the
# transcript is then embedded.
VISION_PAGE_IN, VISION_PAGE_OUT = 515, 960
# One image: the former demo map, 537 input and 119 output tokens
# (measured); a photo of a printed page answers longer, so the output is
# taken as a page's transcript.
IMAGE_IN, IMAGE_OUT = 540, 500
# One minute of audio: 60 billed seconds of transcription; speech is about
# 150 words a minute, about 200 tokens to embed.
MINUTE_SECONDS, MINUTE_TOKENS = 60, 200
# The summary each source gets once, at most this input (SUMMARY_INPUT_TOKENS
# default) and this output: reported per source, as an upper bound.
SUMMARY_IN, SUMMARY_OUT = 6000, 300


@dataclass(frozen=True)
class _Unit:
    action: str
    unit: str
    # (model setting, tokens in, tokens out) per model call of one unit
    calls: tuple[tuple[str, int, int], ...]


def _units() -> dict[Kind, _Unit]:
    embed = "embedding"
    return {
        "text": _Unit("source:text", "page", ((embed, PAGE_TOKENS, 0),)),
        "url": _Unit("source:url", "web page", ((embed, WEB_PAGE_TOKENS, 0),)),
        "pdf_text": _Unit("source:pdf", "page", ((embed, PAGE_TOKENS, 0),)),
        "pdf_vision": _Unit(
            "source:pdf",
            "page",
            (("llm", VISION_PAGE_IN, VISION_PAGE_OUT), (embed, VISION_PAGE_OUT, 0)),
        ),
        "image": _Unit(
            "source:image", "image", (("llm", IMAGE_IN, IMAGE_OUT), (embed, IMAGE_OUT, 0))
        ),
        "audio": _Unit(
            "source:audio", "minute", (("stt", MINUTE_SECONDS, 0), (embed, MINUTE_TOKENS, 0))
        ),
    }


class NominalCall(BaseModel):
    """One model call of a nominal unit: tokens, or seconds for `stt`."""

    model: str
    tokens_in: int
    tokens_out: int


class Estimate(BaseModel):
    """Euro cents, exact. `cost_cents`/`charge_cents` for one `unit`;
    `per_source_charge_cents` once per source on top: the action's fixed
    fee and the summary call (at most its input). `nominal` is what the
    unit is priced as."""

    kind: Kind
    unit: str
    action: str
    cost_cents: Decimal
    charge_cents: Decimal
    per_source_charge_cents: Decimal
    nominal: list[NominalCall]


@router.get("/estimate", response_model=Estimate)
def estimate(request: Request, _: CurrentUser, kind: Kind) -> Estimate:
    """Any bearer (account calls it server-side with a short-lived token):
    it reads nothing of the caller, but `cost_cents` is the platform's cost
    and not for anonymous callers."""
    deps = worker_deps(request)
    inference = deps.settings.inference
    models = {
        "embedding": inference.embedding_model,
        "llm": inference.llm_model,
        "stt": inference.stt_model,
    }
    prices = deps.settings.model_prices
    rules: PricingRules = deps.repository.pricing_rules()
    unit = _units()[kind]
    try:
        cost = sum(
            (
                rules.cost_eur_cents(cost_cents(prices, models[model], tokens_in, tokens_out))
                for model, tokens_in, tokens_out in unit.calls
            ),
            Decimal(0),
        )
        summary = rules.cost_eur_cents(cost_cents(prices, models["llm"], SUMMARY_IN, SUMMARY_OUT))
    except ExchangeRateMissingError:
        raise HTTPException(
            status_code=503, detail="pricing has no exchange rate, ask an admin"
        ) from None
    return Estimate(
        kind=kind,
        unit=unit.unit,
        action=unit.action,
        cost_cents=cost,
        charge_cents=rules.charge_cents(unit.action, cost),
        per_source_charge_cents=rules.charge_cents(unit.action, summary)
        + rules.fixed_cents(unit.action),
        nominal=[
            NominalCall(model=models[model], tokens_in=tokens_in, tokens_out=tokens_out)
            for model, tokens_in, tokens_out in unit.calls
        ],
    )
