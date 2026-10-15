"""A report's checkable units are its paragraphs, also when a heading is
followed by its paragraph without a blank line; a text that cites but
yields no unit never becomes a ready output; stored reports can be re-split."""

import json

import pytest

from lasteverlm_rag.options import REPORT_STYLES
from lasteverlm_rag.outputs.report import blocks
from lasteverlm_rag.repair_reports import repair_reports

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, chunk, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"
SKY = chunk(1, "The sky is blue on a clear day. Grass is green in spring.")
GLUED = (
    "# Sky\n## Colour\nThe sky is blue on a clear day. [1]\n## Grass\nGrass is green in spring. [1]"
)


def run(settings, markdown, **options):
    store = FakeStore()
    store.add_source(NOTEBOOK, "sky.pdf", summary="About the sky.")
    llm = FakeLLM(json.dumps({"title": "Sky", "markdown": markdown}))
    client = make_client(settings, store, FakeRetriever([SKY]), llm)
    r = client.post(OUTPUTS, json={"kind": "report", "options": options}, headers=AUTH)
    client.worker.run_once()
    return store, client.get(f"/api/rag/outputs/{r.json()['id']}", headers=AUTH).json()


def test_a_heading_is_its_own_line_and_the_lines_under_it_the_paragraph():
    assert blocks("# T\nIntro [1].\n\n## A\nOne [2].\nstill one\n## B\nTwo [3].\n\n- x\n- y") == [
        "# T",
        "Intro [1].",
        "## A",
        "One [2].\nstill one",
        "## B",
        "Two [3].",
        "- x\n- y",
    ]
    assert blocks("Plain.\n\nSecond.") == ["Plain.", "Second."]


@pytest.mark.parametrize("style", REPORT_STYLES)
def test_a_paragraph_glued_to_its_heading_is_checked_in_every_style(settings, style):
    _, out = run(settings, GLUED, report_style=style)
    assert out["status"] == "ready", out["error"]
    units = out["content"]["units"]
    assert [u["text"] for u in units] == [
        "The sky is blue on a clear day. [1]",
        "Grass is green in spring. [1]",
    ]
    assert [u["support"] for u in units] == ["supported", "supported"]
    assert out["provenance"]["check"]["supported"] == 2


def test_a_text_that_cites_but_yields_no_unit_fails_after_one_more_try(settings):
    store, out = run(settings, "## The sky is blue [1]\n## Grass is green [1]")
    assert out["status"] == "failed"
    assert out["error"].startswith(
        "the document cites its sources but could not be split into parts to check, 2 attempts"
    )
    assert [a["attempt"] for a in store.outputs[out["id"]]["attempt_log"]] == [1, 2]


def test_few_units_for_many_markers_is_logged(settings, caplog):
    many = "# Sky\n\n" + " ".join(f"Fact {i} [1]." for i in range(9))
    _, out = run(settings, many)
    assert out["status"] == "ready"
    assert "1 checkable units from 9 citation markers" in caplog.text


def test_the_repair_resplits_stored_reports_once_and_keeps_judged_units(settings):
    store, out = run(settings, GLUED)
    row = store.outputs[out["id"]]
    # as stored before the fix: a glued paragraph dropped, the other judged
    kept = {"text": "Grass is green in spring. [1]", "judge": {"verdict": "supported"}}
    row["content"] = {"markdown": GLUED, "units": [kept]}
    row["provenance"]["check"] = {"supported": 0}
    lines: list[str] = []
    found = repair_reports(store, apply=False, say=lines.append)
    assert [(f.output_id, f.units_before, f.units_after) for f in found] == [(out["id"], 1, 2)]
    assert lines == [f"{out['id']}: would re-split: 1 → 2 units"]
    assert row["content"]["units"] == [kept]  # a dry run writes nothing

    repair_reports(store, apply=True, say=lines.append)
    units = row["content"]["units"]
    assert [u["support"] for u in units] == ["supported", "supported"]
    # a unit whose text stays keeps its verdict
    assert "judge" not in units[0] and units[1]["judge"] == {"verdict": "supported"}
    assert row["provenance"]["check"]["supported"] == 2
    assert repair_reports(store, apply=True, say=lines.append) == []  # idempotent
