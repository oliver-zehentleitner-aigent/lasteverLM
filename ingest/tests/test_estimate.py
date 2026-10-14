from decimal import Decimal

import pytest
from lasteverlm_core import PricingRules, cost_cents, parse_model_prices

from lasteverlm_ingest.api import estimate as est

PRICES = parse_model_prices(
    '{"fake-embed": {"in": 2000, "out": 0}, "fake-llm": {"in": 30, "out": 150},'
    ' "fake-stt": {"in": 100, "out": 0}}'
)


def _cost(model, tokens_in, tokens_out=0, rate=Decimal(1)):
    return PricingRules(usd_per_eur=rate).cost_eur_cents(
        cost_cents(PRICES, model, tokens_in, tokens_out)
    )


@pytest.mark.parametrize(
    ("kind", "unit", "action", "calls"),
    [
        ("text", "page", "source:text", [("fake-embed", est.PAGE_TOKENS, 0)]),
        ("url", "web page", "source:url", [("fake-embed", est.WEB_PAGE_TOKENS, 0)]),
        ("pdf_text", "page", "source:pdf", [("fake-embed", est.PAGE_TOKENS, 0)]),
        (
            "pdf_vision",
            "page",
            "source:pdf",
            [("fake-llm", 515, 960), ("fake-embed", 960, 0)],
        ),
        ("image", "image", "source:image", [("fake-llm", 540, 500), ("fake-embed", 500, 0)]),
        ("audio", "minute", "source:audio", [("fake-stt", 60, 0), ("fake-embed", 200, 0)]),
    ],
)
def test_each_kind_is_priced_per_nominal_unit(client, kind, unit, action, calls):
    r = client.get(f"/api/ingest/estimate?kind={kind}")
    assert r.status_code == 200
    body = r.json()
    cost = sum((_cost(m, i, o) for m, i, o in calls), Decimal(0))
    assert (body["kind"], body["unit"], body["action"]) == (kind, unit, action)
    assert Decimal(body["cost_cents"]) == cost
    assert Decimal(body["charge_cents"]) == cost  # the default rules have no margin
    assert [(c["model"], c["tokens_in"], c["tokens_out"]) for c in body["nominal"]] == calls
    assert Decimal(body["per_source_charge_cents"]) == _cost("fake-llm", 6000, 300)


def test_margin_fee_and_rate_come_from_the_pricing_rules(client, repo):
    from lasteverlm_core.billing import ActionPricing

    repo.rules = PricingRules(
        usd_per_eur=Decimal(2),
        default_margin_pct=Decimal(50),
        actions={"source:text": ActionPricing(fixed_cents=Decimal(3))},
    )
    body = client.get("/api/ingest/estimate?kind=text").json()
    cost = _cost("fake-embed", est.PAGE_TOKENS, rate=Decimal(2))
    assert Decimal(body["cost_cents"]) == cost
    assert Decimal(body["charge_cents"]) == cost * Decimal("1.5")
    # The fixed fee is per source, not per page.
    summary = _cost("fake-llm", 6000, 300, rate=Decimal(2))
    assert Decimal(body["per_source_charge_cents"]) == summary * Decimal("1.5") + 3


def test_needs_a_bearer_a_known_kind_and_a_rate(client, repo):
    assert client.get("/api/ingest/estimate?kind=sculpture").status_code == 422
    assert (
        client.get("/api/ingest/estimate?kind=text", headers={"Authorization": ""}).status_code
        == 401
    )
    repo.rules = PricingRules()
    r = client.get("/api/ingest/estimate?kind=text")
    assert (
        r.status_code == 503 and r.json()["error"] == "pricing has no exchange rate, ask an admin"
    )
