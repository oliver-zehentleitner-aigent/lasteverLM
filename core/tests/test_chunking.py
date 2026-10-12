from __future__ import annotations

import pytest

from lasteverlm_core import TOKEN, Chunk, Passage, TokenWindowChunker


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text)


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_empty_input_gives_no_chunks() -> None:
    assert TokenWindowChunker(10, 2).chunk([]) == []
    assert TokenWindowChunker(10, 2).chunk([Passage("   \n ")]) == []
    assert TokenWindowChunker(10, 2).chunk_text("") == []


def test_short_text_is_one_chunk() -> None:
    chunks = TokenWindowChunker(10, 2).chunk([Passage("Hello, world.", page=3)])
    assert chunks == [Chunk(idx=0, page=3, text="Hello, world.")]


def test_windows_have_size_and_overlap() -> None:
    text = words(100)
    chunks = TokenWindowChunker(30, 5).chunk([Passage(text)])
    sizes = [len(tokens(c.text)) for c in chunks]
    assert sizes[:-1] == [30, 30, 30]
    assert sizes[-1] == 100 - 3 * 25
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert tokens(a.text)[-5:] == tokens(b.text)[:5]
    assert [c.idx for c in chunks] == list(range(len(chunks)))


def test_every_token_is_covered() -> None:
    text = words(77)
    chunks = TokenWindowChunker(20, 4).chunk([Passage(text)])
    seen: list[str] = []
    for c in chunks:
        for t in tokens(c.text):
            if t not in seen:
                seen.append(t)
    assert seen == tokens(text)


def test_window_spanning_pages_keeps_first_page_and_a_blank_line() -> None:
    passages = [Passage(words(6, "a"), page=1), Passage(words(6, "b"), page=2)]
    chunks = TokenWindowChunker(8, 4).chunk(passages)
    assert chunks[0].page == 1
    assert chunks[0].text == "a0 a1 a2 a3 a4 a5\n\nb0 b1"
    assert chunks[1].page == 1  # window starts with a4 a5, still on page 1
    assert chunks[1].text == "a4 a5\n\nb0 b1 b2 b3 b4 b5"
    assert len(chunks) == 2


def test_punctuation_counts_as_tokens_and_text_keeps_original_spacing() -> None:
    chunks = TokenWindowChunker(100, 0).chunk([Passage("Ja, genau.  Zwei  Leerzeichen.")])
    assert tokens(chunks[0].text) == ["Ja", ",", "genau", ".", "Zwei", "Leerzeichen", "."]
    assert chunks[0].text == "Ja, genau.  Zwei  Leerzeichen."


def test_chunk_text_matches_single_passage_without_page() -> None:
    chunker = TokenWindowChunker(4, 1)
    text = words(10)
    assert chunker.chunk_text(text) == chunker.chunk([Passage(text)])
    assert all(c.page is None for c in chunker.chunk_text(text))


def test_defaults_are_the_contract() -> None:
    # 420 regex tokens are about 800 model tokens for German text (context/chunking.md)
    chunker = TokenWindowChunker()
    assert (chunker.size, chunker.overlap) == (420, 50)


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        TokenWindowChunker(0, 0)
    with pytest.raises(ValueError):
        TokenWindowChunker(10, 10)
