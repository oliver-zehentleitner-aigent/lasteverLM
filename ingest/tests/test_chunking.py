import pytest

from lasteverlm_ingest.chunking import _TOKEN, TokenWindowChunker
from lasteverlm_ingest.loaders import Passage


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_empty_input_gives_no_chunks():
    assert TokenWindowChunker(10, 2).chunk([]) == []
    assert TokenWindowChunker(10, 2).chunk([Passage("   \n ")]) == []


def test_short_text_is_one_chunk():
    chunks = TokenWindowChunker(10, 2).chunk([Passage("Hello, world.", page=3)])
    assert len(chunks) == 1
    assert chunks[0].idx == 0
    assert chunks[0].page == 3
    assert chunks[0].text == "Hello, world."


def test_windows_have_size_and_overlap():
    text = words(100)
    chunks = TokenWindowChunker(30, 5).chunk([Passage(text)])
    sizes = [len(tokens(c.text)) for c in chunks]
    assert sizes[:-1] == [30, 30, 30]
    assert sizes[-1] == 100 - 3 * 25
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert tokens(a.text)[-5:] == tokens(b.text)[:5]
    assert [c.idx for c in chunks] == list(range(len(chunks)))


def test_every_token_is_covered():
    text = words(77)
    chunks = TokenWindowChunker(20, 4).chunk([Passage(text)])
    seen = []
    for c in chunks:
        for t in tokens(c.text):
            if t not in seen:
                seen.append(t)
    assert seen == tokens(text)


def test_window_spanning_pages_keeps_first_page_and_a_blank_line():
    passages = [Passage(words(6, "a"), page=1), Passage(words(6, "b"), page=2)]
    chunks = TokenWindowChunker(8, 4).chunk(passages)
    assert chunks[0].page == 1
    assert chunks[0].text == "a0 a1 a2 a3 a4 a5\n\nb0 b1"
    assert chunks[1].page == 1  # window starts with a4 a5, still on page 1
    assert chunks[1].text == "a4 a5\n\nb0 b1 b2 b3 b4 b5"
    assert len(chunks) == 2


def test_punctuation_counts_as_tokens_and_text_keeps_original_spacing():
    chunks = TokenWindowChunker(100, 0).chunk([Passage("Ja, genau.  Zwei  Leerzeichen.")])
    assert tokens(chunks[0].text) == ["Ja", ",", "genau", ".", "Zwei", "Leerzeichen", "."]
    assert chunks[0].text == "Ja, genau.  Zwei  Leerzeichen."


def test_invalid_parameters():
    with pytest.raises(ValueError):
        TokenWindowChunker(0, 0)
    with pytest.raises(ValueError):
        TokenWindowChunker(10, 10)
