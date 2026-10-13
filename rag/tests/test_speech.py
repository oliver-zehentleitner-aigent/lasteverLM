from lasteverlm_rag.speech import split_for_speech


def test_short_text_is_one_segment():
    assert split_for_speech("Hello there.  How are you?") == ["Hello there. How are you?"]


def test_segments_end_at_sentence_boundaries_and_respect_the_limit():
    text = " ".join(f"Sentence number {i} says something." for i in range(100))
    segments = split_for_speech(text, max_chars=200)
    assert all(len(s) <= 200 for s in segments)
    assert all(s.endswith(".") for s in segments)
    assert " ".join(segments) == text


def test_an_overlong_sentence_is_cut_at_spaces_then_hard():
    words = "word " * 100
    segments = split_for_speech(words.strip() + ".", max_chars=50)
    assert all(len(s) <= 50 for s in segments)
    assert " ".join(segments) == words.strip() + "."
    assert split_for_speech("x" * 120, max_chars=50) == ["x" * 50, "x" * 50, "x" * 20]


def test_empty_text_has_no_segments():
    assert split_for_speech("   ") == []
