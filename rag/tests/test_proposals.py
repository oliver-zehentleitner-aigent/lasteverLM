"""Find tables / Find themes: candidates from the selected sources, each
with the sources it comes from; Create makes one table (or infographic part)
per picked candidate from its own sources only."""

import json

from .conftest import (
    AUTH,
    NOTEBOOK,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    chunk_uuid,
    make_client,
)
from .test_judging import judges

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
TABLES = f"/api/rag/notebooks/{NOTEBOOK}/tables/propose"
THEMES = f"/api/rag/notebooks/{NOTEBOOK}/infographics/propose"
PRICES = chunk(1, "The ferry costs 12 euros, the bus 3 euros.")
VISITORS = chunk(2, "The museum had 1.906 visitors in 2022 and 2.410 in 2023.")

IDEAS = json.dumps(
    {
        "tables": [
            {
                "title": "Ticket prices",
                "columns": ["Mode", "Price"],
                "preview": [["Ferry", "12 €"]],
                "refs": [1],
            },
            {
                "title": "Museum visitors",
                "columns": ["Year", "Visitors"],
                "preview": [["2022", "1906"]],
                "refs": [2],
            },
            {"title": "Invented", "columns": ["x"], "refs": [9]},  # no passage behind it
        ]
    }
)
THEME_IDEAS = json.dumps(
    {
        "themes": [
            {
                "title": "Travel",
                "headline": "Ferries cost more",
                "facts": [{"label": "Ferry", "value": "12 €"}],
                "refs": [1],
            }
        ]
    }
)


def setup(settings, *replies, judge_models=None):
    store = FakeStore()
    for piece, name in ((PRICES, "prices.pdf"), (VISITORS, "museum.pdf")):
        store.sources[piece.source_id] = {
            "id": piece.source_id,
            "notebook_id": NOTEBOOK,
            "name": name,
            "kind": "pdf",
            "status": "ready",
            "summary": f"{name} figures.",
            "error": None,
        }
    llm = FakeLLM(*replies)
    client = make_client(
        settings, store, FakeRetriever([PRICES, VISITORS]), llm, judges=judge_models
    )
    return store, llm, client


def test_find_tables_proposes_one_per_set_of_things_with_its_sources(settings):
    store, llm, client = setup(settings, IDEAS)
    r = client.post(TABLES, json={"max": 4, "instructions": "Prices first."}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reason"] is None
    prices, visitors = body["candidates"]  # the one citing no passage is not offered
    assert prices["title"] == "Ticket prices" and prices["columns"] == ["Mode", "Price"]
    assert prices["preview"] == [["Ferry", "12 €"]]
    assert prices["sources"] == [{"source_id": str(PRICES.source_id), "name": "doc1.pdf"}]
    assert visitors["sources"] == [{"source_id": str(VISITORS.source_id), "name": "doc2.pdf"}]
    assert prices["passages"][0]["chunk_id"] == str(PRICES.chunk_id)
    assert prices["proposal"]["prompt_version"].startswith("table-propose-v")
    assert "Propose up to 4 distinct tables" in llm.calls[0][1]
    assert store.outputs == {}
    assert {a for a, _ in store.bookings} == {"table_propose"}


def test_find_themes_proposes_infographic_themes(settings):
    _, _, client = setup(settings, THEME_IDEAS)
    (theme,) = client.post(THEMES, json={}, headers=AUTH).json()["candidates"]
    assert (theme["title"], theme["headline"]) == ("Travel", "Ferries cost more")
    assert theme["facts"] == [{"label": "Ferry", "value": "12 €"}]


def table(title, rows, refs):
    return json.dumps({"title": title, "columns": ["A", "B"], "rows": rows, "row_refs": refs})


def test_create_makes_one_table_per_picked_candidate_from_its_own_sources(settings):
    store, llm, client = setup(
        settings,
        IDEAS,
        table("Ticket prices", [["Ferry", "12"], ["Bus", "3"]], [[1], [1]]),
        table("Museum visitors", [["2022", "1906"]], [[2]]),
    )
    candidates = client.post(TABLES, json={}, headers=AUTH).json()["candidates"]
    r = client.post(
        OUTPUTS, json={"kind": "table", "options": {"tables": candidates}}, headers=AUTH
    )
    assert r.status_code == 202, r.text
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready", out
    assert out["title"] == "Ticket prices · Museum visitors"
    first, second = out["content"]["tables"]
    assert (first["title"], first["candidate_id"]) == ("Ticket prices", candidates[0]["id"])
    assert [r["support"] for r in first["row_refs"]] == ["supported", "supported"]
    assert second["rows"] == [["2022", "1906"]] and second["row_refs"][0]["refs"] == [2]
    # each table was written from its own source's passages only
    _, prices_prompt = llm.calls[1]
    _, visitors_prompt = llm.calls[2]
    assert PRICES.text in prices_prompt and VISITORS.text not in prices_prompt
    assert VISITORS.text in visitors_prompt and PRICES.text not in visitors_prompt
    assert 'Make the table "Ticket prices" with these columns: Mode; Price.' in prices_prompt
    assert out["provenance"]["coverage"]["cited"] == 2


def test_a_candidate_from_another_selection_is_refused(settings):
    store, _, client = setup(settings, IDEAS)
    candidates = client.post(TABLES, json={}, headers=AUTH).json()["candidates"]
    body = {
        "kind": "table",
        "options": {"tables": candidates[1:]},  # the visitors table
        "source_ids": [str(PRICES.source_id)],
    }
    r = client.post(OUTPUTS, json=body, headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "candidate_out_of_scope"
    assert "tables:" in r.json()["error"] and store.outputs == {}
    forged = {
        **candidates[0],
        "passages": [{**candidates[0]["passages"][0], "chunk_id": chunk_uuid(9)}],
    }
    r = client.post(OUTPUTS, json={"kind": "table", "options": {"tables": [forged]}}, headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "candidate_out_of_scope"


def test_create_makes_an_infographic_part_per_theme(settings):
    part = json.dumps(
        {
            "title": "Travel",
            "headline": "Ferries cost more",
            "facts": [{"label": "Ferry", "value": "12 euros", "refs": [1]}],
            "sections": [{"title": "Prices", "text": "The ferry costs 12 euros.", "refs": [1]}],
        }
    )
    _, _, client = setup(settings, THEME_IDEAS, part)
    themes = client.post(THEMES, json={}, headers=AUTH).json()["candidates"]
    r = client.post(
        OUTPUTS, json={"kind": "infographic", "options": {"themes": themes}}, headers=AUTH
    )
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready", out
    (made,) = out["content"]["parts"]
    assert (made["title"], made["headline"], made["candidate_id"]) == (
        "Travel",
        "Ferries cost more",
        themes[0]["id"],
    )
    assert made["facts"][0]["support"] == "supported"


def test_a_judged_composite_revises_and_removes_across_tables(settings):
    store, _, client = setup(
        settings,
        IDEAS,
        table("Ticket prices", [["Ferry", "12"]], [[1]]),
        table("Museum visitors", [["wrong", "9999"]], [[2]]),
        json.dumps({"units": [{"index": 1, "action": "drop", "unit": {}}]}),
        judge_models=judges(),
    )
    candidates = client.post(TABLES, json={}, headers=AUTH).json()["candidates"]
    r = client.post(
        OUTPUTS,
        json={"kind": "table", "options": {"tables": candidates, "verification": "thorough"}},
        headers=AUTH,
    )
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready", out
    # the visitors table lost its only row, so it went with it
    assert [t["title"] for t in out["content"]["tables"]] == ["Ticket prices"]
    assert out["provenance"]["judge"]["removed"][0]["verdict"] == "dropped in revision"


def test_the_estimate_prices_proposals_and_scales_with_the_picked(settings):
    _, _, client = setup(settings, IDEAS)
    r = client.post("/api/rag/estimate", json={"action": "table_propose"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["charge_cents_max"] > 0
    candidates = client.post(TABLES, json={}, headers=AUTH).json()["candidates"]
    one = client.post("/api/rag/estimate", json={"kind": "table"}, headers=AUTH).json()
    two = client.post(
        "/api/rag/estimate", json={"kind": "table", "options": {"tables": candidates}}, headers=AUTH
    ).json()
    assert two["charge_cents_max"] > one["charge_cents_max"]
