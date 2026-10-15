import json
import logging

from lasteverlm_rag.coverage import (
    MAX_GENERATOR_PASSAGES,
    balance,
    per_source_quota,
    uncovered_sources,
)
from lasteverlm_rag.models import RetrievedChunk, SourceSummary

from .conftest import AUTH, NOTEBOOK, FakeLLM, FakeRetriever, FakeStore, make_client

OUTPUTS = f"/api/rag/notebooks/{NOTEBOOK}/outputs"


def hit(source_id: str, n: int, similarity: float, name: str = "doc.pdf") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{source_id}-{n}",
        source_id=source_id,
        source_name=name,
        source_kind="pdf",
        page=n,
        text=f"{name} chunk {n}",
        similarity=similarity,
    )


def summary(source_id: str, name: str) -> SourceSummary:
    return SourceSummary(source_id, name, "pdf", f"About {name}.")


def test_quota_guarantees_two_per_source_within_the_cap():
    assert per_source_quota(1, 8) == (2, 8)
    assert per_source_quota(6, 8) == (2, 12)
    assert per_source_quota(20, 8) == (1, MAX_GENERATOR_PASSAGES)
    assert per_source_quota(0, 8) == (0, 8)


def test_one_source_cannot_fill_the_input_alone():
    vnc = [hit("vnc", i, 0.9 - i / 100, "vnc.pdf") for i in range(8)]
    vi = [hit("vi", i, 0.4 - i / 100, "vi.pdf") for i in range(2)]
    picked = balance([vnc[:2], vi], ranked=vnc, total=8)
    assert len(picked) == 8
    assert [c.chunk_id for c in picked if c.source_id == "vi"] == ["vi-0", "vi-1"]
    assert [c.similarity for c in picked] == sorted((c.similarity for c in picked), reverse=True)


def test_over_the_cap_every_source_keeps_its_best_chunk_first():
    sources = [[hit(f"s{i}", 0, 0.5), hit(f"s{i}", 1, 0.4)] for i in range(5)]
    picked = balance(sources, ranked=[], total=6)
    assert {c.source_id for c in picked} == {f"s{i}" for i in range(5)}
    assert len(picked) == 6


def test_uncovered_sources_use_the_words_only_one_name_has():
    summaries = [summary("vi", "linux_-_vi.pdf"), summary("vnc", "linux_-_VNC-Server.pdf")]
    passages = [hit("vi", 0, 0.5), hit("vnc", 0, 0.9)]
    vnc_only = "Linux VNC Server Setup Guide: install x11vnc, port 5900"
    assert uncovered_sources(vnc_only, summaries, passages) == ["linux_-_vi.pdf"]
    both = "Linux administration: vi and VNC"
    assert uncovered_sources(both, summaries, passages) == []
    # a name without a word of its own ("linux" is shared, "pdf" is the extension) is not checked
    plain = [summary("a", "linux.pdf"), summary("b", "linux_notes.pdf")]
    assert uncovered_sources("notes", plain, []) == []


def test_a_mind_map_gets_both_sources_and_a_gap_is_logged(settings, caplog):
    store = FakeStore()
    vi = store.add_source(NOTEBOOK, "linux_-_vi.pdf", summary="The vi editor.")
    vnc = store.add_source(NOTEBOOK, "linux_-_VNC-Server.pdf", summary="Setting up VNC.")
    chunks = [hit(vnc, i, 0.9 - i / 100, "linux_-_VNC-Server.pdf") for i in range(8)]
    chunks += [hit(vi, i, 0.35 - i / 100, "linux_-_vi.pdf") for i in range(3)]
    vnc_only = json.dumps(
        {"title": "Linux VNC Server Setup Guide", "root": {"label": "VNC", "children": []}}
    )
    llm = FakeLLM(vnc_only)
    client = make_client(settings, store, FakeRetriever(chunks), llm)

    output_id = client.post(OUTPUTS, json={"kind": "mindmap"}, headers=AUTH).json()["id"]
    with caplog.at_level(logging.WARNING, logger="lasteverlm_rag.service"):
        client.worker.run_once()

    system, prompt = llm.calls[0]
    assert "Use every source listed" in system and "unused_sources" in system
    assert "linux_-_vi.pdf chunk 0" in prompt and "linux_-_vi.pdf chunk 1" in prompt
    assert "one branch per source" in prompt
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [
        f"output {output_id[:8]} (mindmap) does not mention source 'linux_-_vi.pdf' of its input"
    ]
    # the document is kept: a gap is logged, not failed
    assert client.get(f"/api/rag/outputs/{output_id}", headers=AUTH).json()["status"] == "ready"
