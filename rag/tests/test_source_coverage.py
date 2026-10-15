"""Which selected sources an output cites, read from its units' refs, and
why not where the model said so."""

import json

from lasteverlm_rag.models import Passage, Unit
from lasteverlm_rag.outputs._base import unused_sources
from lasteverlm_rag.provenance import shared_provenance, source_coverage

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, chunk, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"


def passage(n, source_id, name):
    return Passage(n, f"c{n}", source_id, name, "pdf", None, "text")


def test_coverage_counts_the_sources_the_units_cite():
    passages = [passage(1, "a", "a.pdf"), passage(2, "b", "b.pdf"), passage(3, "a", "a.pdf")]
    units = [Unit({"refs": [1, 3]}, "x", [1, 3]), Unit({"refs": []}, "y", [])]
    found = source_coverage(
        units,
        passages,
        [("a", "a.pdf"), ("b", "b.pdf"), ("c", "c.pdf")],
        [{"source": "B.pdf ", "reason": "It lists prices, not dates."}],
    )
    assert found == {
        "selected": 3,
        "cited": 1,
        "sources": [
            {"source_id": "a", "name": "a.pdf", "cited": True, "reason": None},
            {
                "source_id": "b",
                "name": "b.pdf",
                "cited": False,
                "reason": "It lists prices, not dates.",
            },
            {"source_id": "c", "name": "c.pdf", "cited": False, "reason": None},
        ],
    }


def test_without_units_every_passage_counts_as_cited():
    passages = [passage(1, "a", "a.pdf")]
    assert source_coverage([], passages, [("a", "a.pdf")], [])["cited"] == 1


def test_the_models_unused_list_is_read_leniently():
    assert unused_sources({"unused_sources": [{"source": "x.pdf", "reason": " no  dates "}]}) == [
        {"source": "x.pdf", "reason": "no dates"}
    ]
    assert unused_sources({"unused_sources": "x"}) == [] and unused_sources([]) == []
    assert unused_sources({"unused_sources": [{"reason": "nameless"}, "x"]}) == []


def test_an_output_stores_its_coverage_and_the_shared_view_hides_the_ids(settings):
    store = FakeStore()
    sky, grass = chunk(1, "The sky is blue on a clear day."), chunk(2, "Grass is green in spring.")
    for piece, name in ((sky, "sky.pdf"), (grass, "grass.pdf")):
        store.sources[piece.source_id] = {
            "id": piece.source_id,
            "notebook_id": NOTEBOOK,
            "name": name,
            "kind": "pdf",
            "status": "ready",
            "summary": f"About {name}.",
            "error": None,
        }
    reply = json.dumps(
        {
            "title": "Sky",
            "markdown": "The sky is blue on a clear day. [1]",
            "unused_sources": [
                {"source": "grass.pdf", "reason": "It is about grass, not the sky."}
            ],
        }
    )
    client = make_client(settings, store, FakeRetriever([sky, grass]), FakeLLM(reply))
    r = client.post(OUTPUTS, json={"kind": "report"}, headers=AUTH)
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    coverage = out["provenance"]["coverage"]
    assert (coverage["selected"], coverage["cited"]) == (2, 1)
    by_name = {s["name"]: s for s in coverage["sources"]}
    assert by_name["sky.pdf"]["cited"] and not by_name["grass.pdf"]["cited"]
    assert by_name["grass.pdf"]["reason"] == "It is about grass, not the sky."
    shared = shared_provenance(out["provenance"])
    assert all("source_id" not in s for s in shared["coverage"]["sources"])
