"""Charts: proposed from the sources, picked by the user, every value checked
against the passages it cites."""

import copy
import json

import pytest

from lasteverlm_rag.outputs.chart import NO_SERIES, check_point

from .conftest import (
    AUTH,
    NOTEBOOK,
    OTHER_NOTEBOOK,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

PROPOSE = f"/api/rag/notebooks/{NOTEBOOK}/charts/propose"
OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
VISITORS = chunk(1, "In 2022 the museum had 1.906 visitors, in 2023 it had 2.410.")
SHARE = chunk(2, "Members made up 12,5 % of all visitors.")
PROPOSAL = json.dumps(
    {
        "charts": [
            {
                "title": "Visitors per year",
                "chart_type": "line",
                "x_label": "Year",
                "y_label": "Visitors",
                "series": [
                    {
                        "name": "Visitors",
                        "points": [
                            {"x": "2022", "y": 1906, "refs": [1]},
                            # off by one: not what the passage says
                            {"x": "2023", "y": 2411, "refs": [1]},
                            {"x": "Change", "y": 504, "refs": [], "derived_from": [1]},
                        ],
                    }
                ],
                "note": "Visitors of the museum.",
            },
            {
                "title": "Members",
                "chart_type": "pie",
                "series": [
                    {
                        "name": "Share",
                        "points": [
                            {"x": "Members", "y": 12.5, "refs": [2]},
                            {"x": "Others", "y": 87.5, "refs": [], "derived_from": [2]},
                        ],
                    }
                ],
            },
        ]
    }
)


def setup(settings, *replies, found=(VISITORS, SHARE)):
    store = FakeStore()
    store.add_source(NOTEBOOK, "museum.pdf", summary="Museum figures.")
    retriever = FakeRetriever(list(found))
    llm = FakeLLM(*replies)
    return store, retriever, llm, make_client(settings, store, retriever, llm)


def propose(client, body=None):
    r = client.post(PROPOSE, json=body or {}, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def points(chart):
    return [(p["x"], p["y"], p["support"]) for s in chart["series"] for p in s["points"]]


def test_a_proposal_returns_checked_candidates_and_stores_nothing(settings):
    store, _, llm, client = setup(settings, PROPOSAL)
    body = propose(client, {"instructions": "  Only   the visitors. ", "max": 4})
    assert body["reason"] is None
    first, second = body["candidates"]
    assert points(first) == [
        ("2022", 1906, "supported"),
        ("2023", 2411, "unsupported"),
        ("Change", 504, "derived"),
    ]
    assert points(second) == [("Members", 12.5, "supported"), ("Others", 87.5, "derived")]
    assert first["passages"] == [
        {"n": 1, "chunk_id": VISITORS.chunk_id, "source_name": "doc1.pdf", "page": None}
    ]
    assert first["proposal"]["model"] == "test-llm"
    assert first["proposal"]["prompt_version"] == "chart-v3"
    assert first["id"] != second["id"]
    system, user = llm.calls[0]
    assert "Propose up to 4 charts" in user
    assert 'User\'s instructions: "Only the visitors."' in system
    assert store.outputs == {}
    assert [u.kind for _, _, u in store.usage] == ["embedding", "llm"]


def test_no_digits_in_the_passages_means_no_model_call(settings):
    store, _, llm, client = setup(settings, PROPOSAL, found=[chunk(1, "No figures here.")])
    assert propose(client) == {"candidates": [], "reason": NO_SERIES}
    assert llm.calls == []
    assert [u.kind for _, _, u in store.usage] == ["embedding"]


def test_an_empty_answer_is_a_valid_answer(settings):
    _, _, _, client = setup(settings, '{"charts": []}')
    assert propose(client) == {"candidates": [], "reason": NO_SERIES}


def test_the_proposal_is_cut_to_max_and_validated(settings):
    _, _, llm, client = setup(settings, PROPOSAL)
    assert len(propose(client, {"max": 1})["candidates"]) == 1
    for bad in ({"max": 0}, {"max": 13}, {"instructions": "x" * 501}):
        assert client.post(PROPOSE, json=bad, headers=AUTH).status_code == 422
    assert client.post(PROPOSE, json={}).status_code == 401
    other = f"/api/rag/notebooks/{OTHER_NOTEBOOK}/charts/propose"
    assert client.post(other, json={}, headers=AUTH).status_code == 404


def test_picked_candidates_become_the_output_without_a_model_call(settings):
    store, _, llm, client = setup(settings, PROPOSAL)
    candidates = propose(client)["candidates"]
    r = client.post(
        OUTPUTS, json={"kind": "chart", "options": {"charts": candidates[::-1]}}, headers=AUTH
    )
    assert r.status_code == 202, r.text
    assert client.worker.run_once() == 1
    assert len(llm.calls) == 1  # the proposal's only
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready", out
    assert out["title"] == "Members and 1 more"
    members, visitors = out["content"]["charts"]
    # one numbering for both: the members' passage first, as picked
    assert members["series"][0]["points"][0] == {
        "x": "Members",
        "y": 12.5,
        "refs": [1],
        "support": "supported",
    }
    assert visitors["series"][0]["points"][2]["derived_from"] == [2]
    assert "id" not in members and "passages" not in members
    log = out["provenance"]
    assert [p["chunk_id"] for p in log["passages"]] == [SHARE.chunk_id, VISITORS.chunk_id]
    assert log["check"] == {
        "method": "number-match-v1",
        "supported": 2,
        "unsupported": 1,
        "derived": 2,
    }
    assert [c["role"] for c in log["calls"]] == ["proposal", "check"]
    assert log["usage"]["llm"] == {"tokens_in": 0, "tokens_out": 0}
    source = store.sources[out["source_id"]]
    assert source["kind"] == "generated" and source["name"] == "Members and 1 more"

    token = client.post(f"/api/rag/outputs/{out['id']}/share", headers=AUTH).json()
    shared = client.get(f"/api/rag/shared/{token['share_token']}").json()
    assert "charts" not in shared["options"] and "charts" not in shared["provenance"]["options"]
    assert VISITORS.chunk_id not in json.dumps(shared)


def test_a_value_changed_by_the_client_is_checked_again(settings):
    _, _, _, client = setup(settings, PROPOSAL)
    candidate = copy.deepcopy(propose(client)["candidates"][0])
    candidate["series"][0]["points"][0]["y"] = 1907
    candidate["series"][0]["points"][1]["support"] = "supported"  # ignored, checked again
    r = client.post(
        OUTPUTS, json={"kind": "chart", "options": {"charts": [candidate]}}, headers=AUTH
    )
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert points(out["content"]["charts"][0])[:2] == [
        ("2022", 1907, "unsupported"),
        ("2023", 2411, "unsupported"),
    ]


def test_a_passage_gone_before_the_worker_runs_leaves_its_values_unsupported(settings):
    _, retriever, _, client = setup(settings, PROPOSAL)
    candidate = propose(client)["candidates"][0]
    r = client.post(
        OUTPUTS, json={"kind": "chart", "options": {"charts": [candidate]}}, headers=AUTH
    )
    retriever.found = [SHARE]
    client.worker.run_once()
    out = client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()
    assert out["status"] == "ready"
    assert [s for _, _, s in points(out["content"]["charts"][0])] == ["unsupported"] * 3
    assert out["provenance"]["passages"] == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda c: [], "charts: 1 to 12 picked candidates"),
        (lambda c: [c] * 13, "charts: 1 to 12 picked candidates"),
        (lambda c: [{**c, "chart_type": "radar"}], "charts: chart_type"),
        (
            lambda c: [{**c, "chart_type": "pie", "series": c["series"] * 2}],
            "a pie chart has exactly one series",
        ),
    ],
)
def test_picked_candidates_that_do_not_fit_are_422(settings, change, message):
    _, _, _, client = setup(settings, PROPOSAL)
    candidate = propose(client)["candidates"][0]
    r = client.post(
        OUTPUTS, json={"kind": "chart", "options": {"charts": change(candidate)}}, headers=AUTH
    )
    assert r.status_code == 422 and message in r.json()["error"], r.text


def test_a_chart_takes_no_language():
    from lasteverlm_rag.options import OutputOptions, resolve

    with pytest.raises(ValueError, match="language: not an option of chart"):
        resolve("chart", OutputOptions(language="de"), "ryan")


def test_a_point_is_supported_only_by_a_written_number():
    texts = {1: "1.906 Besucher", 2: "12,5 %"}
    assert check_point({"y": 1906, "refs": [1]}, texts) == "supported"
    assert check_point({"y": 1906, "refs": [1, 3]}, texts) == "unsupported"  # 3 is no passage
    assert check_point({"y": 1906, "refs": []}, texts) == "unsupported"
    assert check_point({"y": 0.125, "refs": [2]}, texts) == "supported"
    assert check_point({"y": 87.5, "derived_from": [2]}, texts) == "derived"
    assert check_point({"y": 87.5, "derived_from": [4]}, texts) == "unsupported"
