"""The chat names every document of the notebook by its kind: every output
kind and source kind has a label, and an unknown kind never fails the
question (0.22.21: a notebook with a chart answered every question with 500)."""

import json
import logging
from typing import get_args

from lasteverlm_core import OutputKind, SourceKind

from lasteverlm_rag.models import NotebookDocument
from lasteverlm_rag.options import KIND_OPTIONS
from lasteverlm_rag.service import _OUTPUT_KINDS, _SOURCE_KINDS, _document_line

from .conftest import (
    AUTH,
    CONVERSATION,
    NOTEBOOK,
    FakeLLM,
    FakeRetriever,
    FakeStore,
    chunk,
    make_client,
)

ASK = f"/api/rag/notebooks/{NOTEBOOK}/ask"


def test_every_output_and_source_kind_has_a_label():
    assert set(get_args(OutputKind)) <= set(_OUTPUT_KINDS)
    assert set(KIND_OPTIONS) <= set(_OUTPUT_KINDS)
    assert set(get_args(SourceKind)) <= set(_SOURCE_KINDS)


def test_an_unknown_kind_is_shown_by_its_name_and_logged(caplog):
    future = NotebookDocument(source_id="s", name="Plan", kind="generated", output_kind="podcast")
    with caplog.at_level(logging.WARNING, logger="lasteverlm_rag.service"):
        assert _document_line(future, None) == "podcast (generated): Plan"
    assert "no label for kind 'podcast'" in caplog.text


def test_a_question_in_a_notebook_with_a_chart_is_answered(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "languages.pdf", summary="Languages by share.")
    chart = store.add_source(NOTEBOOK, "Languages by share", kind="generated")
    output = store.create_output(NOTEBOOK, "chart", "ready")
    store.outputs[output.id].update(source_id=chart, title="Languages by share")
    llm = FakeLLM("Python leads [1].")
    client = make_client(settings, store, FakeRetriever([chunk(1, "Python 40 %")]), llm)
    r = client.post(
        ASK, json={"question": "Which language leads?", "conversation_id": CONVERSATION},
        headers=AUTH,
    )  # fmt: skip
    assert r.status_code == 200, r.text
    system, _ = llm.calls[-1]
    assert "chart (generated): Languages by share" in system + json.dumps(llm.calls)
