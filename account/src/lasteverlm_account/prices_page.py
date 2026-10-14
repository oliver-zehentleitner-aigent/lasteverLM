"""The public price list as a server-rendered, script-free HTML page, built from the same
``PublicPrices`` as ``GET /prices`` so the two cannot disagree. It exists for readers that
do not run JavaScript, such as ingest's URL loader reading the starter notebook's price
source (context/finance.md, "The price list also comes as script-free HTML"). English only,
in the web's words; every value is escaped."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from html import escape

from .models import PublicPriceRow, PublicPrices

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)

GROUPS = (("sources", "Sources"), ("chat", "Chat"), ("outputs", "Outputs"), ("extras", "Extras"))
SOURCES = {
    "source:pdf": "PDF (Text)",
    "source:pdf:vision": "PDF (Vision)",
    "source:text": "Text",
    "source:url": "Web page",
    "source:image": "Image",
    "source:audio": "Audio",
}
OUTPUTS = {
    "output:report": "Report",
    "output:quiz": "Quiz",
    "output:table": "Data table",
    "output:mindmap": "Mindmap",
    "output:infographic": "Infographic",
    "output:audio": "Audio",
    "output:decision": "Decision",
    "output:chart": "Chart",
    "output:flashcards": "Flashcards",
}
EXTRAS = {
    "judge:low": "Judge, low",
    "judge:medium": "Judge, medium",
    "judge:high": "Judge, high",
    "judge": "Check with a judge",
    "chart_propose": "Find charts",
    "decision": "Weighing a decision",
    "summary": "Summary of a source",
    "voice_sample": "Voice sample",
}
LABELS = {"chat_answer": "Question to your sources", **SOURCES, **OUTPUTS, **EXTRAS}
ORDER = {a: i for i, a in enumerate((*SOURCES, "chat_answer", *OUTPUTS, *EXTRAS))}
UNITS = {
    "question": "per question",
    "output": "per output",
    "source": "per source",
    "check": "per check",
    "chart_proposal": "per search",
    "summary": "per summary",
    "decision": "per decision",
    "voice_sample": "per sample",
    "audio_minute": "per minute of audio",
    "page": "per page",
    "image": "per image",
    "web_page": "per web page",
}

HOW_IT_WORKS = (
    "Every price is in euros and comes from what these actions really took over the last"
    " {days} days, at today's prices.",
    "Adding a source is free.",
    "Processing it (reading, transcribing, indexing) costs, as listed below.",
    "You see the estimated price for your own choice before every action.",
    "Credit does not expire.",
)
JUDGE_NOTE = (
    "The judge rows are a check you ask for on an existing output or chat answer. A judge"
    " chosen while creating an output is included in that output's price."
)


def group_of(action: str) -> str:
    if action.startswith("source:"):
        return "sources"
    if action.startswith("output:"):
        return "outputs"
    return "chat" if action == "chat_answer" else "extras"


def action_label(row: PublicPriceRow) -> str:
    action = f"judge:{row.level}" if row.level else row.action
    return LABELS.get(action, action)


def format_price(cents: float) -> str:
    """As the web shows it: whole cents from 10 cents up, below that two significant
    digits (€0.0034), so a fraction of a cent is neither €0.00 nor six decimals."""
    euros = Decimal(str(cents)) / 100
    if cents >= 10 or cents == 0:
        return f"€{euros.quantize(Decimal('0.01'), ROUND_HALF_UP)}"
    rounded = euros.quantize(Decimal(1).scaleb(euros.adjusted() - 1), ROUND_HALF_UP)
    return f"€{rounded.normalize():f}"  # at most two significant digits, as Intl does


def price_text(row: PublicPriceRow) -> str:
    """ "€0.01–€0.05 per page + €0.01 per source · estimated", or "no price yet"."""
    if row.price_per_unit_cents is None:
        return "no price yet"
    low, high = row.price_min_cents, row.price_max_cents
    if low is not None and high is not None and format_price(low) != format_price(high):
        price = f"{format_price(low)}–{format_price(high)}"
    else:
        price = format_price(row.price_per_unit_cents)
    text = f"{price} {UNITS.get(row.unit, f'per {row.unit}')}"
    if row.per_source_cents:
        text += f" + {format_price(row.per_source_cents)} per source"
    return text + (" · estimated" if row.estimated else "")


def typical_text(row: PublicPriceRow) -> str:
    t = row.typical_cents
    if t is None:
        return "no experience yet"
    return f"{format_price(t.p25)}–{format_price(t.p75)}, median {format_price(t.median)}"


def rate_text(prices: PublicPrices) -> str:
    if prices.usd_per_eur is None:
        return "No exchange rate is set yet, so nothing can be priced at the moment."
    text = f"Model prices are in US dollars and converted at 1 EUR = {prices.usd_per_eur} USD"
    if prices.rate_source == "ECB" and prices.rate_date:
        return f"{text} (ECB reference rate of {prices.rate_date.isoformat()})."
    return f"{text}."


def render(prices: PublicPrices) -> str:
    e = escape
    how = " ".join(HOW_IT_WORKS).format(days=prices.window_days)
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>lasteverLM prices: what things cost</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:56rem;margin:2rem auto;"
        "padding:0 1rem}table{border-collapse:collapse;width:100%}th,td{text-align:left;"
        "padding:.3rem .6rem;border-bottom:1px solid #ccc;vertical-align:top}</style>",
        "</head><body>",
        "<h1>What things cost</h1>",
        "<h2>How it works</h2>",
        f"<p>{e(how)}</p>",
    ]
    for key, title in GROUPS:
        rows = sorted(
            (r for r in prices.actions if group_of(r.action) == key),
            key=lambda r: (ORDER.get(r.action, len(ORDER)), r.action),
        )
        if not rows:
            continue
        parts += [
            f"<h2>{e(title)}</h2>",
            "<table><thead><tr><th>What</th><th>Price per unit</th>"
            "<th>Typical per action</th><th>Model</th></tr></thead><tbody>",
        ]
        for r in rows:
            parts.append(
                f'<tr data-action="{e(r.action)}"><td>{e(action_label(r))}</td>'
                f"<td>{e(price_text(r))}</td><td>{e(typical_text(r))}</td>"
                f"<td>{e(r.model or '—')}</td></tr>"
            )
        parts.append("</tbody></table>")
        if any(r.action.startswith("judge:") for r in rows):
            parts.append(f"<p>{e(JUDGE_NOTE)}</p>")
    parts += [
        "<h2>Exchange rate</h2>",
        f"<p>{e(rate_text(prices))}</p>",
        "</body></html>",
    ]
    return "\n".join(parts) + "\n"
