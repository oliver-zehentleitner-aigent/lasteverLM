from lasteverlm_core import Citation

from lasteverlm_rag.citations import language_of
from lasteverlm_rag.provenance import check_answer

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


def citation(n: int, quote: str) -> Citation:
    return Citation(
        n=n,
        source_id="00000000-0000-0000-0000-000000000001",
        source_name="doc.pdf",
        source_kind="pdf",
        chunk_id="00000000-0000-0000-0000-000000000002",
        quote=quote,
    )


def test_an_answer_is_checked_paragraph_by_paragraph_and_stored(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "doc1.pdf")
    retriever = FakeRetriever(
        [chunk(1, "The sky is blue on a clear day."), chunk(2, "Grass grows in spring.")]
    )
    llm = FakeLLM("The sky is blue on clear days [1].\n\nMountains are made of cheese [2].")
    client = make_client(settings, store, retriever, llm)
    r = client.post(ASK, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH)
    body = r.json()
    assert [u["support"] for u in body["units"]] == ["supported", "unsupported"]
    assert body["units"][0] == {
        "text": "The sky is blue on clear days [1].",
        "refs": [1],
        "support": "supported",
    }
    assert body["check"] == {
        "method": "lexical-overlap-v1",
        "threshold": 0.5,
        "supported": 1,
        "unsupported": 1,
        "unverified": 0,
    }
    messages = client.get(f"/api/rag/conversations/{CONVERSATION}/messages", headers=AUTH).json()
    assert messages[0]["units"] is None and messages[0]["check"] is None  # the question
    assert messages[1]["units"] == body["units"] and messages[1]["check"] == body["check"]


def test_an_answer_without_citations_is_not_checked(settings):
    store = FakeStore()
    store.add_source(NOTEBOOK, "doc1.pdf")
    client = make_client(settings, store, FakeRetriever([]), FakeLLM("You have one PDF."))
    body = client.post(
        ASK, json={"question": "?", "conversation_id": CONVERSATION}, headers=AUTH
    ).json()
    assert (body["units"], body["check"]) == (None, None)


def test_an_uncited_paragraph_of_a_cited_answer_is_unsupported():
    support = check_answer("In short:\n\nThe sky is blue [1].", [citation(1, "The sky is blue.")])
    assert support is not None
    assert [u["support"] for u in support["units"]] == ["unsupported", "supported"]


def test_a_translated_answer_with_low_overlap_is_unverified():
    quote = "The river is the longest in the country and it flows to the sea."
    support = check_answer(
        "Der Fluss ist der längste im Land und er mündet in das Meer [1].", [citation(1, quote)]
    )
    assert support is not None and support["units"][0]["support"] == "unverified"
    assert support["check"]["unverified"] == 1
    # the same answer in the passage's language is unsupported, not unverified
    same = check_answer(
        "It is the oldest bridge in the city and it is made of stone [1].", [citation(1, quote)]
    )
    assert same is not None and same["units"][0]["support"] == "unsupported"


def test_language_of_tells_english_from_german_or_says_unknown():
    assert language_of("The cat is on the mat and it is happy with that.") == "en"
    assert language_of("Die Katze ist auf der Matte und sie ist nicht traurig.") == "de"
    assert language_of("Vi und VNC") is None
