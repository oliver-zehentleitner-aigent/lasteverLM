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
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from lasteverlm_core import ExchangeRateMissingError, PricingRules, cost_cents
from pydantic import BaseModel, Field, model_validator

from lasteverlm_ingest.api.deps import worker_deps
from lasteverlm_ingest.auth import CurrentUser
from lasteverlm_ingest.repository import LibrarySource
from lasteverlm_ingest.worker import WorkerDeps

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
# A rendered page is read in tiles (loaders/tiles.py): an A4 or letter page
# at the render DPI in two. Each tile costs a call's input; the transcript,
# the output, stays about one page (docs/vision-eval.md).
VISION_PAGE_TILES = 2
# One image: the former demo map, 537 input and 119 output tokens
# (measured); a photo of a printed page answers longer, so the output is
# taken as a page's transcript.
IMAGE_IN, IMAGE_OUT = 540, 500
# An image over the tiling threshold is read in tiles, each a call of its
# own; the upload records how many (page_count). For an image uploaded
# before that, up to this many (a 2880×1800 screenshot).
IMAGE_TILES_UNKNOWN = 4
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
            (
                ("llm", VISION_PAGE_TILES * VISION_PAGE_IN, VISION_PAGE_OUT),
                (embed, VISION_PAGE_OUT, 0),
            ),
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


# -- the cost of reading given sources ----------------------------------------

# A web page before its first fetch: from a short page to a long article.
WEB_PAGE_MIN_TOKENS, WEB_PAGE_MAX_TOKENS = 500, 20_000
# Text: about four characters per token, a page about 2,000 characters.
CHARS_PER_TOKEN, CHARS_PER_PAGE = 4, 2000
# A recording whose length is only known after converting: from its size
# at 256 kbit/s (shortest) to 32 kbit/s (longest), at most four hours.
AUDIO_MAX_BYTES_PER_SECOND, AUDIO_MIN_BYTES_PER_SECOND = 32_000, 4_000
AUDIO_MAX_SECONDS = 4 * 3600
# Embedding tokens per second of speech (150 words a minute).
SPEECH_TOKENS_PER_SECOND = MINUTE_TOKENS / MINUTE_SECONDS

Calls = tuple[tuple[str, int, int], ...]


class SourcesEstimateRequest(BaseModel):
    # Sources to read; empty when the plan only fetches pages again.
    library_ids: list[UUID] = Field(default_factory=list, max_length=200)
    # Web pages already read that the plan would fetch again.
    refetch: list[UUID] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _something_to_price(self) -> SourcesEstimateRequest:
        if not self.library_ids and not self.refetch:
            raise ValueError("library_ids or refetch must name at least one source")
        return self


class SourceEstimate(BaseModel):
    library_id: UUID
    kind: str
    unread: bool
    charge_cents_min: Decimal
    charge_cents_max: Decimal
    basis: str


class SourcesEstimate(BaseModel):
    items: list[SourceEstimate]


@dataclass(frozen=True)
class _Pricing:
    rules: PricingRules
    prices: Any
    models: dict[str, str]
    summary_in: int
    summary_out: int

    def charge(self, action: str, calls: Calls, text_tokens: int) -> Decimal:
        """One source read with `calls`: the margin on their cost, plus the
        summary (its input capped) and the action's fixed fee."""
        summary_in = min(text_tokens, self.summary_in)
        all_calls = (*calls, ("llm", summary_in, self.summary_out))
        cost = sum(
            (
                self.rules.cost_eur_cents(cost_cents(self.prices, self.models[m], i, o))
                for m, i, o in all_calls
            ),
            Decimal(0),
        )
        return self.rules.charge_cents(action, cost) + self.rules.fixed_cents(action)


def _embed(tokens: int) -> Calls:
    return (("embedding", tokens, 0),)


def _vision(pages: int) -> Calls:
    return (
        ("llm", pages * VISION_PAGE_TILES * VISION_PAGE_IN, pages * VISION_PAGE_OUT),
        *_embed(pages * VISION_PAGE_OUT),
    )


def _unread(p: _Pricing, lib: LibrarySource, max_pages: int) -> tuple[Decimal, Decimal, str]:
    action = f"source:{lib.kind}"
    size = lib.size_bytes or 0
    if lib.kind == "text":
        tokens = max(1, size // CHARS_PER_TOKEN)
        pages = max(1, -(-size // CHARS_PER_PAGE))
        charge = p.charge(action, _embed(tokens), tokens)
        return charge, charge, f"{pages} {'page' if pages == 1 else 'pages'} of text"
    if lib.kind == "url":
        low = p.charge(action, _embed(WEB_PAGE_MIN_TOKENS), WEB_PAGE_MIN_TOKENS)
        high = p.charge(action, _embed(WEB_PAGE_MAX_TOKENS), WEB_PAGE_MAX_TOKENS)
        return low, high, "web page, not fetched yet"
    if lib.kind == "image":
        low_tiles, high_tiles = (
            (lib.page_count, lib.page_count) if lib.page_count else (1, IMAGE_TILES_UNKNOWN)
        )

        def image(tiles: int) -> Decimal:
            out = tiles * IMAGE_OUT
            return p.charge(action, (("llm", tiles * IMAGE_IN, out), *_embed(out)), out)

        if not lib.page_count:
            basis = f"image, 1–{IMAGE_TILES_UNKNOWN} tiles"
        elif lib.page_count == 1:
            basis = "image"
        else:
            basis = f"image, read in {lib.page_count} tiles"
        return image(low_tiles), image(high_tiles), basis
    if lib.kind == "pdf":
        known = lib.page_count is not None
        low_pages, high_pages = (lib.page_count, lib.page_count) if known else (1, max_pages)
        assert low_pages is not None and high_pages is not None
        text = {
            n: p.charge(action, _embed(n * PAGE_TOKENS), n * PAGE_TOKENS)
            for n in {low_pages, high_pages}
        }
        vision = {
            n: p.charge(action, _vision(n), n * VISION_PAGE_OUT) for n in {low_pages, high_pages}
        }
        mode = lib.capture or "text"
        count = f"{lib.page_count} pages" if known else "page count unknown"
        if mode == "text":
            return text[low_pages], text[high_pages], f"{count}, text layer"
        if mode == "vision":
            return vision[low_pages], vision[high_pages], f"{count}, read by the vision model"
        return text[low_pages], vision[high_pages], f"{count}, text layer or vision per page"
    if lib.kind == "audio":
        if lib.duration_seconds is not None:
            low_s = high_s = max(1, round(lib.duration_seconds))
            basis = f"{max(1, round(low_s / 60))} min audio"
        else:
            low_s = max(1, min(AUDIO_MAX_SECONDS, size // AUDIO_MAX_BYTES_PER_SECOND))
            high_s = max(1, min(AUDIO_MAX_SECONDS, size // AUDIO_MIN_BYTES_PER_SECOND))
            basis = f"about {max(1, round(low_s / 60))}–{max(1, round(high_s / 60))} min audio"

        def audio(seconds: int) -> Decimal:
            tokens = round(seconds * SPEECH_TOKENS_PER_SECOND)
            return p.charge(action, (("stt", seconds, 0), *_embed(tokens)), tokens)

        return audio(low_s), audio(high_s), basis
    return Decimal(0), Decimal(0), lib.kind


def pricing_for(deps: WorkerDeps) -> _Pricing:
    """The prices, the current pricing rules and the models a read uses."""
    inference = deps.settings.inference
    return _Pricing(
        rules=deps.repository.pricing_rules(),
        prices=deps.settings.model_prices,
        models={
            "embedding": inference.embedding_model,
            "llm": inference.llm_model,
            "stt": inference.stt_model,
        },
        summary_in=deps.settings.summary_input_tokens,
        summary_out=deps.settings.summary_max_tokens,
    )


def estimate_read(
    pricing: _Pricing, lib: LibrarySource, refetch: bool, max_pages: int
) -> tuple[Decimal, Decimal, str]:
    """What reading `lib` would charge, (min, max, basis): an unread one
    from what is stored about it, a web page fetched again as up to one
    web page, anything read already nothing. Raises
    `ExchangeRateMissingError` without a rate."""
    if lib.status == "added":
        return _unread(pricing, lib, max_pages)
    if refetch and lib.kind == "url":
        high = pricing.charge("source:url", _embed(WEB_PAGE_TOKENS), WEB_PAGE_TOKENS)
        return Decimal(0), high, "re-read if changed"
    return Decimal(0), Decimal(0), "read already"


@router.post("/sources/estimate", response_model=SourcesEstimate)
def estimate_sources(
    request: Request, user: CurrentUser, body: SourcesEstimateRequest
) -> SourcesEstimate:
    """What reading the caller's given library sources would charge, before
    anything is read: unread (`added`) ones from their stored size, page
    count or duration, a range where those are not known yet; read ones
    nothing, unless listed in `refetch` (a web page fetched again: nothing
    if unchanged, a web page if changed). Euro cents, exact. 404 naming any
    id that is not the caller's."""
    deps = worker_deps(request)
    repo = deps.repository
    ids = list(dict.fromkeys([*body.library_ids, *body.refetch]))
    found = {i: repo.get_library_source(i) for i in ids}
    missing = [
        str(i) for i, lib in found.items() if lib is None or lib.owner != user or lib.deleted_at
    ]
    if missing:
        raise HTTPException(
            status_code=404, detail=f"library sources not found: {', '.join(missing)}"
        )
    pricing = pricing_for(deps)
    refetch = set(body.refetch)
    items = []
    try:
        for library_id in ids:
            lib = found[library_id]
            assert lib is not None
            low, high, basis = estimate_read(
                pricing, lib, library_id in refetch, deps.settings.pdf_vision_max_pages
            )
            items.append(
                SourceEstimate(
                    library_id=library_id,
                    kind=lib.kind,
                    unread=lib.status == "added",
                    charge_cents_min=low,
                    charge_cents_max=high,
                    basis=basis,
                )
            )
    except ExchangeRateMissingError:
        raise HTTPException(
            status_code=503, detail="pricing has no exchange rate, ask an admin"
        ) from None
    return SourcesEstimate(items=items)
