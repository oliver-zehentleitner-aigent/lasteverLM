from lasteverlm_rag.citations import content_words, keep_markers, overlap
from lasteverlm_rag.models import Passage, Unit
from lasteverlm_rag.provenance import check_units, shared_provenance


def passage(n: int, text: str) -> Passage:
    return Passage(n, f"c{n}", f"s{n}", f"doc{n}.pdf", "pdf", 1, text)


PASSAGES = [
    passage(1, "The Danube flows through Vienna and Budapest before it reaches the Black Sea."),
    passage(2, "Its length is 2850 kilometres."),
]


def check(text: str, refs: list[int], claim: bool = True, translated: bool = False):
    target: dict = {"text": text}
    summary = check_units([Unit(target, text, refs, claim)], PASSAGES, translated)
    return target, summary


def test_a_unit_whose_words_its_passages_hold_is_supported():
    target, summary = check("The Danube flows through Vienna. [1]", [1])
    assert target == {
        "text": "The Danube flows through Vienna. [1]",
        "refs": [1],
        "support": "supported",
    }
    assert summary == {
        "method": "lexical-overlap-v1",
        "threshold": 0.5,
        "supported": 1,
        "unsupported": 0,
        "unverified": 0,
    }


def test_the_cited_passages_count_together():
    target, _ = check("The Danube reaches the Black Sea after 2850 kilometres.", [1, 2])
    assert target["support"] == "supported"
    target, _ = check("The Danube reaches the Black Sea after 2850 kilometres.", [2])
    assert target["support"] == "unsupported"


def test_no_refs_a_made_up_ref_or_other_words_are_unsupported_and_kept():
    assert check("The Danube flows through Vienna.", [])[0]["support"] == "unsupported"
    target, _ = check("The Danube flows through Vienna.", [1, 9])
    assert (target["refs"], target["support"]) == ([1], "unsupported")
    target, _ = check("Paris has many museums and cafés.", [1])
    assert target["support"] == "unsupported"


def test_low_overlap_in_a_chosen_language_is_unverified_not_unsupported():
    target, summary = check("Die Donau fließt durch Wien.", [1], translated=True)
    assert target["support"] == "unverified" and summary["unverified"] == 1
    # a made-up ref stays unsupported in any language
    assert check("Die Donau fließt durch Wien.", [9], translated=True)[0]["support"] == (
        "unsupported"
    )
    # enough overlap is supported in any language
    assert check("Danube Vienna Budapest", [1], translated=True)[0]["support"] == "supported"


def test_a_question_without_refs_is_not_a_claim():
    target, summary = check("What is the Danube?", [], claim=False)
    assert target == {"text": "What is the Danube?", "refs": []}
    assert summary["supported"] + summary["unsupported"] + summary["unverified"] == 0
    assert check("What about Vienna?", [1], claim=False)[0]["support"] == "supported"


def test_words_are_compared_without_case_markers_function_words_or_plural_endings():
    assert content_words("The Clouds [3] and THE cloud of 2024") == {"cloud", "2024"}
    assert content_words("rivers") == content_words("river") == {"river"}
    assert overlap("Clouds over Vienna", ["A cloud over vienna."]) == 1.0
    assert overlap("and the of", []) == 1.0


def test_keep_markers_drops_only_unknown_numbers():
    assert keep_markers("A [1, 7]. B [7]. C [2]", {1, 2}) == "A [1]. B. C [2]"


def test_the_shared_log_has_no_ids_and_no_source_selection():
    log = {
        "options": {"language": "de", "sources": ["s1"]},
        "retrieval": {"k": 8, "candidates": [{"chunk_id": "c1", "source_id": "s1", "page": 1}]},
        "passages": [{"n": 1, "chunk_id": "c1", "source_id": "s1", "quote": "q"}],
        "check": {"supported": 1},
    }
    shared = shared_provenance(log)
    assert shared == {
        "options": {"language": "de"},
        "retrieval": {"k": 8, "candidates": [{"page": 1}]},
        "passages": [{"n": 1, "quote": "q"}],
        "check": {"supported": 1},
    }
    assert shared_provenance(None) is None
