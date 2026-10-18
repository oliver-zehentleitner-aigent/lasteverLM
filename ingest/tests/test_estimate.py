from decimal import Decimal
from uuid import uuid4

import pytest
from lasteverlm_core import DEMO_USER_ID, PricingRules, cost_cents, parse_model_prices

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
            [("fake-llm", 2 * 515, 960), ("fake-embed", 960, 0)],  # two tiles per page
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


def _add(repo, nb, name, kind, **fields):
    lib = repo.add_source(nb, name, kind, f"k/{name}", fields.pop("size", None)).library_id
    repo.library[lib] = repo.library[lib].model_copy(update={"status": "added", **fields})
    return lib


def _charge(calls, text_tokens, action):
    """What _Pricing charges with the test settings and default rules."""
    summary = ("fake-llm", min(text_tokens, 6000), 300)
    return sum((_cost(m, i, o) for m, i, o in (*calls, summary)), Decimal(0))


def test_unread_sources_are_priced_from_what_is_stored(client, repo):
    nb = repo.create_notebook(DEMO_USER_ID, "nb").id
    text = _add(repo, nb, "a.txt", "text", size=8000)
    pdf = _add(repo, nb, "p.pdf", "pdf", capture="text", page_count=12)
    scan = _add(repo, nb, "s.pdf", "pdf", capture="auto", page_count=3)
    wav = _add(repo, nb, "r.wav", "audio", duration_seconds=180.0)
    url = _add(repo, nb, "https://x.test/", "url")
    done = _add(repo, nb, "old.txt", "text", size=10)
    repo.set_library_status(done, "ready")
    r = client.post(
        "/api/ingest/sources/estimate",
        json={"library_ids": [str(i) for i in (text, pdf, scan, wav, url, done)]},
    )
    assert r.status_code == 200
    items = {i["library_id"]: i for i in r.json()["items"]}

    def money(item):
        return Decimal(item["charge_cents_min"]), Decimal(item["charge_cents_max"])

    t = items[str(text)]
    assert t["unread"] and t["basis"] == "4 pages of text"
    assert money(t) == (_charge([("fake-embed", 2000, 0)], 2000, "source:text"),) * 2
    p = items[str(pdf)]
    assert p["basis"] == "12 pages, text layer"
    assert money(p)[0] == _charge([("fake-embed", 6000, 0)], 6000, "source:pdf")
    s = items[str(scan)]
    assert s["basis"] == "3 pages, text layer or vision per page"
    low, high = money(s)
    assert low == _charge([("fake-embed", 1500, 0)], 1500, "source:pdf") and high > low
    a = items[str(wav)]
    assert a["basis"] == "3 min audio"
    assert money(a)[0] == _charge([("fake-stt", 180, 0), ("fake-embed", 600, 0)], 600, "x")
    u = items[str(url)]
    assert u["basis"] == "web page, not fetched yet" and money(u)[0] < money(u)[1]
    d = items[str(done)]
    assert not d["unread"] and money(d) == (0, 0) and d["basis"] == "read already"


def test_a_page_to_refetch_costs_nothing_if_unchanged(client, repo):
    nb = repo.create_notebook(DEMO_USER_ID, "nb").id
    url = _add(repo, nb, "https://x.test/", "url")
    repo.set_library_status(url, "ready")
    body = {"library_ids": [str(url)], "refetch": [str(url)]}
    [item] = client.post("/api/ingest/sources/estimate", json=body).json()["items"]
    assert item["basis"] == "re-read if changed" and Decimal(item["charge_cents_min"]) == 0
    assert Decimal(item["charge_cents_max"]) == _charge(
        [("fake-embed", est.WEB_PAGE_TOKENS, 0)], est.WEB_PAGE_TOKENS, "source:url"
    )


def test_refetch_alone_is_priced_and_nothing_at_all_is_refused(client, repo):
    nb = repo.create_notebook(DEMO_USER_ID, "nb").id
    url = _add(repo, nb, "https://x.test/", "url")
    repo.set_library_status(url, "ready")
    # rag sends an empty library_ids when every selected source is read already
    r = client.post("/api/ingest/sources/estimate", json={"library_ids": [], "refetch": [str(url)]})
    assert r.status_code == 200
    [item] = r.json()["items"]
    assert item["basis"] == "re-read if changed" and not item["unread"]
    r = client.post("/api/ingest/sources/estimate", json={"library_ids": [], "refetch": []})
    assert r.status_code == 422


def test_unknown_measures_give_a_range_and_foreign_ids_a_404(client, repo):
    nb = repo.create_notebook(DEMO_USER_ID, "nb").id
    old_pdf = _add(repo, nb, "old.pdf", "pdf", capture="text")  # before page counts
    m4a = _add(repo, nb, "t.m4a", "audio", size=4_000_000)  # length known only converted
    items = client.post(
        "/api/ingest/sources/estimate", json={"library_ids": [str(old_pdf), str(m4a)]}
    ).json()["items"]
    assert items[0]["basis"] == "page count unknown, text layer"
    assert items[1]["basis"] == "about 2–17 min audio"
    for item in items:
        assert Decimal(item["charge_cents_min"]) < Decimal(item["charge_cents_max"])
    theirs = repo.add_source(repo.create_notebook(uuid4(), "x").id, "x", "text", "k").library_id
    r = client.post("/api/ingest/sources/estimate", json={"library_ids": [str(theirs)]})
    assert r.status_code == 404 and str(theirs) in r.json()["error"]
