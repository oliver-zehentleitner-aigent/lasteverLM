from lasteverlm_rag.citations import (
    extract_markers,
    map_citations,
    number_passages,
)

from .conftest import CHUNK_1, SOURCE_1, chunk, chunk_uuid

PASSAGES = number_passages(
    [
        chunk(1, "Alpha text.", page=3),
        chunk(2, "Beta text.", source_kind="generated"),
        chunk(3, "Gamma."),
    ]
)


def test_number_passages_is_one_based_in_retrieval_order():
    assert [p.n for p in PASSAGES] == [1, 2, 3]
    assert PASSAGES[0].chunk_id == CHUNK_1


def test_extract_markers_handles_groups_and_duplicates():
    assert extract_markers("A [2]. B [1, 3] and [2] again [1][3].") == [2, 1, 3]
    assert extract_markers("no markers") == []


def test_map_citations_resolves_sources_in_order_of_first_appearance():
    answer, citations = map_citations("Alpha is first [1]. Beta is second [2].", PASSAGES)
    assert answer == "Alpha is first [1]. Beta is second [2]."
    assert [c.n for c in citations] == [1, 2]
    assert str(citations[0].source_id) == SOURCE_1
    assert citations[0].source_name == "doc1.pdf"
    assert citations[0].source_kind == "pdf"
    assert str(citations[0].chunk_id) == CHUNK_1
    assert citations[0].page == 3
    assert citations[0].quote == "Alpha text."
    assert citations[1].source_kind == "generated"
    assert citations[1].page is None


def test_map_citations_strips_made_up_markers_and_renumbers_densely():
    answer, citations = map_citations("Made up [7]. Real [3]. Mixed [3, 9].", PASSAGES)
    assert answer == "Made up. Real [1]. Mixed [1]."
    assert [(c.n, str(c.chunk_id)) for c in citations] == [(1, chunk_uuid(3))]


def test_map_citations_splits_grouped_markers_and_numbers_by_first_appearance():
    answer, citations = map_citations("Claim [3, 1]. More [2] and [3].", PASSAGES)
    assert answer == "Claim [1][2]. More [3] and [1]."
    assert [(c.n, str(c.chunk_id)) for c in citations] == [
        (1, chunk_uuid(3)),
        (2, chunk_uuid(1)),
        (3, chunk_uuid(2)),
    ]


def test_map_citations_without_markers_yields_no_citations():
    answer, citations = map_citations("The passages do not say.", PASSAGES)
    assert answer == "The passages do not say."
    assert citations == []


def test_citation_carries_the_verbatim_chunk_score_and_position():
    long_text = "  line one\n\nline   two  " + "word " * 100
    passages = number_passages(
        [
            chunk(1, long_text, similarity=0.73456, chunk_index=11, chunk_count=43),
            chunk(2, "short"),
        ]
    )
    _, citations = map_citations("[1] [2]", passages)
    first = citations[0]
    assert first.quote == long_text  # verbatim: whitespace and length untouched
    assert (first.similarity, first.chunk_index, first.chunk_count) == (0.735, 11, 43)
    assert citations[1].chunk_index is None and citations[1].similarity == 0.9
