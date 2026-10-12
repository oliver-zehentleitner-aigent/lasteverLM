from lasteverlm_rag.citations import (
    QUOTE_MAX_CHARS,
    extract_markers,
    map_citations,
    number_passages,
)

from .conftest import chunk

PASSAGES = number_passages(
    [
        chunk(1, "Alpha text.", page=3),
        chunk(2, "Beta text.", source_kind="generated"),
        chunk(3, "Gamma."),
    ]
)


def test_number_passages_is_one_based_in_retrieval_order():
    assert [p.n for p in PASSAGES] == [1, 2, 3]
    assert PASSAGES[0].chunk_id == "chunk-1"


def test_extract_markers_handles_groups_and_duplicates():
    assert extract_markers("A [2]. B [1, 3] and [2] again [1][3].") == [2, 1, 3]
    assert extract_markers("no markers") == []


def test_map_citations_keeps_model_numbers_and_resolves_sources():
    answer, citations = map_citations("Alpha is first [1]. Beta is second [2].", PASSAGES)
    assert answer == "Alpha is first [1]. Beta is second [2]."
    assert [c.n for c in citations] == [1, 2]
    assert citations[0].source_id == "source-1"
    assert citations[0].source_name == "doc1.pdf"
    assert citations[0].source_kind == "pdf"
    assert citations[0].chunk_id == "chunk-1"
    assert citations[0].page == 3
    assert citations[0].quote == "Alpha text."
    assert citations[1].source_kind == "generated"
    assert citations[1].page is None


def test_map_citations_strips_markers_that_name_no_passage():
    answer, citations = map_citations("Made up [7]. Real [2]. Mixed [2, 9].", PASSAGES)
    assert answer == "Made up. Real [2]. Mixed [2]."
    assert [c.n for c in citations] == [2]


def test_map_citations_without_markers_yields_no_citations():
    answer, citations = map_citations("The passages do not say.", PASSAGES)
    assert answer == "The passages do not say."
    assert citations == []


def test_quote_is_whitespace_normalized_and_truncated_at_word_boundary():
    long_text = "word " * 100
    passages = number_passages([chunk(1, "  line one\n\nline   two  "), chunk(2, long_text)])
    _, citations = map_citations("[1] [2]", passages)
    assert citations[0].quote == "line one line two"
    assert citations[1].quote.endswith("…")
    assert len(citations[1].quote) <= QUOTE_MAX_CHARS + 1
    assert not citations[1].quote[:-1].endswith(" ")
