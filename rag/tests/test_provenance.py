from lasteverlm_rag.citations import content_words, keep_markers, overlap
from lasteverlm_rag.models import Passage, Unit
from lasteverlm_rag.provenance import check_units, shared_provenance


def passage(n: int, text: str) -> Passage:
    return Passage(n, f"c{n}", f"s{n}", f"doc{n}.pdf", "pdf", 1, text)


PASSAGES = [
    passage(1, "The Danube flows through Vienna and Budapest before it reaches the Black Sea."),
    passage(2, "Its length is 2850 kilometres."),
]


def check(text: str, refs: list[int], claim: bool = True):
    target: dict = {"text": text}
    summary = check_units([Unit(target, text, refs, claim)], PASSAGES)
    return target, summary


def test_a_unit_whose_words_its_passages_hold_is_supported():
    target, summary = check("The Danube flows through Vienna. [1]", [1])
    assert target == {
        "text": "The Danube flows through Vienna. [1]",
        "refs": [1],
        "support": "supported",
    }
    assert summary == {
        "method": "lexical-overlap-v2",
        "threshold": 0.5,
        "supported": 1,
        "unsupported": 0,
        "unverified": 0,
        "possible_contradiction": 0,
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


GERMAN = "Die Donau ist der Fluss, der durch die Stadt Wien und auch nach Budapest fließt."


def test_low_overlap_in_another_language_than_the_passages_is_unverified():
    target, summary = check(GERMAN, [1])
    assert target["support"] == "unverified" and summary["unverified"] == 1
    # a made-up ref stays unsupported in any language
    assert check(GERMAN, [9])[0]["support"] == "unsupported"
    # enough overlap is supported in any language
    assert check("Danube Vienna Budapest", [1])[0]["support"] == "supported"


def test_low_overlap_in_the_passages_own_language_is_unsupported():
    # an English unit over English passages, however the output's language was chosen
    target, summary = check("It is the oldest bridge in the city and it is made of stone.", [1])
    assert target["support"] == "unsupported" and summary["unverified"] == 0


def test_mixed_passages_are_told_per_unit():
    passages = [
        *PASSAGES,
        passage(3, "Die Brücke ist die älteste der Stadt und sie ist aus Stein gebaut."),
    ]
    english = {"text": "It is the oldest bridge in the city and it is made of stone."}
    german = {"text": GERMAN}
    units = [
        # English over the German passage: another language
        Unit(english, english["text"], [3]),
        # English over an English passage: the same language
        Unit({**english}, english["text"], [1]),
        # German over the German passage: the same language
        Unit(german, german["text"], [3]),
    ]
    check_units(units, passages)
    assert [u.target["support"] for u in units] == ["unverified", "unsupported", "unsupported"]


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


def test_table_rows_quiz_questions_and_mindmap_nodes_are_units():
    from lasteverlm_rag.outputs.mindmap import Mindmap, MindmapGenerator
    from lasteverlm_rag.outputs.quiz import Quiz, QuizGenerator
    from lasteverlm_rag.outputs.table import Table, TableGenerator

    table = TableGenerator().to_output(
        Table.model_validate(
            {
                "title": "Rivers",
                "columns": ["River", "Length"],
                "rows": [["Danube", "2850 km"], ["Rhine", "1230 km"]],
                "row_refs": [[2], []],
            }
        )
    )
    assert check_units(table.units, PASSAGES)["supported"] == 1
    assert table.content["row_refs"] == [
        {"refs": [2], "support": "supported"},
        {"refs": [], "support": "unsupported"},
    ]

    quiz = QuizGenerator().to_output(
        Quiz.model_validate(
            {
                "title": "Q",
                "questions": [
                    {
                        "question": "Where does the Danube end?",
                        "options": ["Black Sea", "North Sea"],
                        "answer": "Black Sea",
                        "explanation": "It reaches the Black Sea.",
                        "refs": [1],
                    }
                ],
            }
        )
    )
    check_units(quiz.units, PASSAGES)
    assert quiz.content["questions"][0]["support"] == "supported"
    assert quiz.content["questions"][0]["refs"] == [1]

    mindmap = MindmapGenerator().to_output(
        Mindmap.model_validate(
            {
                "title": "M",
                "root": {
                    "label": "European rivers",
                    "children": [{"label": "Danube to the Black Sea", "refs": [1]}],
                },
            }
        )
    )
    summary = check_units(mindmap.units, PASSAGES)
    root = mindmap.content["root"]
    assert "support" not in root and root["refs"] == []  # the root is no claim
    assert root["children"][0]["support"] == "supported"
    assert summary["supported"] == 1 and summary["unsupported"] == 0


def test_a_unit_that_negates_its_passage_is_a_possible_contradiction():
    passages = [passage(1, "The bridge over the Danube is open to traffic every day of the year.")]
    target = {"text": "The bridge over the Danube is not open to traffic. [1]"}
    summary = check_units([Unit(target, target["text"], [1])], passages, "report")
    assert target["support"] == "possible_contradiction"
    assert summary["possible_contradiction"] == 1 and summary["method"] == "lexical-overlap-v2"
    # the same words without the negation still pass
    same = {"text": "The bridge over the Danube is open to traffic. [1]"}
    check_units([Unit(same, same["text"], [1])], passages, "report")
    assert same["support"] == "supported"


def test_quizzes_and_flashcards_are_not_checked_for_negation():
    passages = [passage(1, "The bridge over the Danube is open to traffic every day of the year.")]
    for kind in ("quiz", "flashcards"):
        target = {"text": "The bridge over the Danube is not open to traffic. [1]"}
        check_units([Unit(target, target["text"], [1])], passages, kind)
        assert target["support"] == "supported"
