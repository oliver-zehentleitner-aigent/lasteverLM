import json

import pytest
from lasteverlm_core import CompletionResult, ProviderError, Usage

from evals.judge.run import report, word_check
from lasteverlm_rag.judge import JUDGE_SYSTEM, judge_unit, judge_user_prompt, parse_judgement

from .conftest import FakeLLM

PASSAGES = {1: "The Margarethe went aground in 1879.\n Three wrecks lie inside it."}
USAGE = Usage("llm", "judge-model", 300, 40)


def answer(**fields):
    return CompletionResult(json.dumps(fields), USAGE)


def test_the_prompt_has_the_statement_without_markers_and_numbered_passages():
    user = judge_user_prompt("It sank in 1879. [1]", PASSAGES)
    assert user.startswith("Statement:\nIt sank in 1879.\n\nPassages:\n[1] The Margarethe")
    assert judge_user_prompt("x", {}).endswith("Passages:\n(none)")
    assert "never from your own knowledge" in JUDGE_SYSTEM


def test_a_judgement_is_parsed_and_its_quote_located():
    j = parse_judgement(
        answer(verdict="contradicted", reason=" The year  is 1879. ", quote="went aground in 1879"),
        PASSAGES,
    )
    assert (j.verdict, j.reason, j.quote, j.quote_verbatim) == (
        "contradicted",
        "The year is 1879.",
        "went aground in 1879",
        True,
    )
    loose = parse_judgement(answer(verdict="supported", reason="r", quote="sank in 1879"), PASSAGES)
    assert loose.quote_verbatim is False
    fenced = CompletionResult('```json\n{"verdict": "not_in_source", "reason": "r"}\n```', USAGE)
    assert parse_judgement(fenced, PASSAGES).quote == ""


@pytest.mark.parametrize(
    "text",
    [
        "no json at all",
        json.dumps({"verdict": "maybe", "reason": "r"}),
        json.dumps({"verdict": "supported", "reason": "  "}),
        json.dumps({"verdict": "supported", "reason": "r", "quote": 3}),
        json.dumps(["supported"]),
    ],
)
def test_a_malformed_answer_is_a_billed_provider_error(text):
    with pytest.raises(ProviderError) as caught:
        parse_judgement(CompletionResult(text, USAGE), PASSAGES)
    assert caught.value.usage == USAGE


def test_judge_unit_makes_one_call_with_the_judge_prompt():
    llm = FakeLLM(json.dumps({"verdict": "supported", "reason": "r", "quote": ""}))
    judgement, result = judge_unit(llm.complete, "Three wrecks lie inside it.", PASSAGES)
    assert judgement.verdict == "supported" and result.text
    assert llm.calls[0][0] == JUDGE_SYSTEM and llm.budgets == [4000]


def test_the_eval_baseline_is_the_word_check_and_the_report_counts_hits():
    passages = {"reef": PASSAGES[1]}
    claims = [
        {"id": "s", "category": "supported", "expected": "supported", "refs": ["reef"],
         "text": "The Margarethe went aground in 1879."},
        {"id": "o", "category": "off_by_one", "expected": "contradicted", "refs": ["reef"],
         "text": "The Margarethe went aground in 1880."},
    ]  # fmt: skip
    # the word check cannot see the year: both pass as supported
    assert [word_check(c, passages) for c in claims] == ["supported", "supported"]
    fixture = {"categories": {"supported": "", "off_by_one": ""}, "claims": claims}
    results = {
        "date": "2026-10-14T00:00:00+00:00",
        "prompt_version": "judge-v1",
        "n": 1,
        "prices": {"source": "test", "models": {"m": {"in": 1.0, "out": 2.0}}},
        "baseline": {
            "method": "lexical-overlap-v1",
            "threshold": 0.5,
            "results": {"s": "supported", "o": "supported"},
        },
        "levels": {
            "low": {
                "model": "m",
                "calls": [
                    {"claim": "s", "verdict": "supported", "quote_verbatim": True,
                     "latency_s": 1.0, "tokens_in": 100, "tokens_out": 10},
                    {"claim": "o", "verdict": None, "latency_s": 2.0,
                     "tokens_in": 100, "tokens_out": 1500},
                ],
            }
        },
    }  # fmt: skip
    text = report(results, fixture)
    assert "| off_by_one | contradicted | 0/1 (0%) | 0/1 (0%) |" in text
    assert "| all | – | 1/2 (50%) | 1/2 (50%) |" in text
    assert "| low | `m` | 2 | 1 | 1/1 (100%) |" in text
    assert '`o` "The Margarethe went aground in 1880." (expected contradicted): None ×1' in text
