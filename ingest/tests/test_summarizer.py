from lasteverlm_ingest.loaders import Passage
from lasteverlm_ingest.summarizer import head_text


def test_head_text_keeps_whole_short_input():
    assert head_text([Passage("Hello world.", 1), Passage("Second page.", 2)], 100) == (
        "Hello world.\n\nSecond page."
    )


def test_head_text_cuts_on_a_token_boundary():
    text = " ".join(f"w{i}" for i in range(50))
    assert head_text([Passage(text)], 7) == "w0 w1 w2 w3 w4 w5 w6"


def test_head_text_spans_passages_until_the_budget_is_used():
    passages = [Passage("a b c", 1), Passage("d e f", 2), Passage("g h i", 3)]
    assert head_text(passages, 5) == "a b c\n\nd e"
    assert head_text(passages, 0) == ""
    assert head_text([], 10) == ""
