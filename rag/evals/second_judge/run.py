"""Which model can be bulletproof's second judge: every candidate (another
family than the author and the high judge) judges the judge fixture's 24
claims and the negation sets' 80 unit/passage pairs N times, beside the
high judge, with the service's own judge prompt.

    python -m evals.second_judge.run --models minimax-m3,mimo-v2.6-pro-rl --n 3

Reads INFERENCE_API_KEY (and INFERENCE_BASE_URL) from the environment; the
key is never written. Writes results/<date>.json (every call) and
results/<date>.md (the report). Bulletproof counts a unit supported only if
both judges say so; disagreement is "disputed".
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lasteverlm_core import InferenceSettings, OpenAICompatibleLLM, ProviderError
from lasteverlm_core.providers.openai_compat import make_client

from lasteverlm_rag.judge import JUDGE_MAX_TOKENS, judge_unit

HERE = Path(__file__).parent
EVALS = HERE.parent
HIGH = "glm-5.3"
WORKERS = 4


def cases() -> list[dict[str, Any]]:
    """Every claim with its passages and the verdict a correct judge gives."""
    found = []
    judge = json.loads((EVALS / "judge" / "fixture.json").read_text())
    for c in judge["claims"]:
        texts = {n: judge["passages"][k] for n, k in enumerate(c["refs"], start=1)}
        found.append(
            {
                "id": c["id"],
                "set": "judge",
                "category": c["category"],
                "text": c["text"],
                "passages": texts,
                "expected": c["expected"],
            }
        )
    for name in ("fixture", "heldout"):
        for c in json.loads((EVALS / "negation" / f"{name}.json").read_text())["cases"]:
            found.append(
                {
                    "id": c["id"],
                    "set": f"negation-{name}",
                    "category": c["category"],
                    "text": c["unit"],
                    "passages": {1: c["passage"]},
                    "expected": _negation_expected(c),
                }
            )
    return found


def _negation_expected(case: dict[str, Any]) -> str:
    """What a judge should say about a negation case: a contradiction is
    contradicted; a trap that states something about another subject than
    the passage ("other clause") is not in the source; the other traps hold."""
    if case["expected"] == "contradiction":
        return "contradicted"
    return "not_in_source" if case["category"] == "other clause" else "supported"


def judge_once(llm: OpenAICompatibleLLM, case: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    record: dict[str, Any] = {"case": case["id"]}
    try:
        judgement, result = judge_unit(llm.complete, case["text"], case["passages"])
        record.update(
            verdict=judgement.verdict,
            tokens_in=result.usage.tokens_in,
            tokens_out=result.usage.tokens_out,
        )
    except ProviderError as exc:
        record.update(
            verdict=None,
            error=str(exc)[:200],
            tokens_in=exc.usage.tokens_in if exc.usage else 0,
            tokens_out=exc.usage.tokens_out if exc.usage else 0,
        )
    record["latency_s"] = round(time.monotonic() - started, 2)
    return record


def run(models: list[str], n: int) -> dict[str, Any]:
    client = make_client(InferenceSettings.from_env(os.environ))
    all_cases = cases()
    out: dict[str, Any] = {"date": datetime.now(UTC).isoformat(), "n": n, "models": {}}
    for model in [HIGH, *models]:
        llm = OpenAICompatibleLLM(client, model, max_tokens=JUDGE_MAX_TOKENS)
        jobs = [c for c in all_cases for _ in range(n)]
        with ThreadPoolExecutor(WORKERS) as pool:
            calls = list(pool.map(judge_once, [llm] * len(jobs), jobs))
        out["models"][model] = calls
        print(f"{model}: {len(calls)} calls")
    return out


def _right(verdict: str | None, expected: str) -> bool:
    # not_in_source and contradicted both fail a unit; the fixture's expected
    # verdicts are what a correct judge says
    if expected == "supported":
        return verdict == "supported"
    return verdict in ("contradicted", "not_in_source")


def report(results: dict[str, Any]) -> str:
    by_id = {c["id"]: c for c in cases()}
    lines = [
        f"# Second judge evaluation, {results['date'][:10]}",
        "",
        f"N = {results['n']} per case; {len(by_id)} cases (24 judge-fixture claims, "
        "80 negation pairs). A hit: supported where the case holds, contradicted or "
        "not_in_source where it does not.",
        "",
        "| model | hits | false supported | false failed | no answer "
        "| tokens in/out per call | s per call |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, calls in results["models"].items():
        hits = sum(_right(r["verdict"], by_id[r["case"]]["expected"]) for r in calls)
        false_sup = sum(
            r["verdict"] == "supported" and by_id[r["case"]]["expected"] != "supported"
            for r in calls
        )
        false_fail = sum(
            r["verdict"] in ("contradicted", "not_in_source")
            and by_id[r["case"]]["expected"] == "supported"
            for r in calls
        )
        none = sum(r["verdict"] is None for r in calls)
        tin = sum(r["tokens_in"] for r in calls) / len(calls)
        tout = sum(r["tokens_out"] for r in calls) / len(calls)
        lat = sum(r["latency_s"] for r in calls) / len(calls)
        lines.append(
            f"| {model} | {hits}/{len(calls)} ({hits/len(calls):.0%}) | {false_sup} | "
            f"{false_fail} | {none} | {tin:.0f}/{tout:.0f} | {lat:.1f} |"
        )
    # bulletproof: the high judge and a candidate together, call by call
    lines += [
        "",
        "Paired with the high judge (supported only if both say so):",
        "",
        "| second judge | wrongly passed | disputed on true claims "
        "| disputed on false claims | both fail a true claim |",
        "|---|---|---|---|---|",
    ]
    high = results["models"][HIGH]
    for model, calls in results["models"].items():
        if model == HIGH:
            continue
        passed_wrong = disputed_true = disputed_false = both_fail_true = 0
        for a, b in zip(high, calls, strict=True):
            expected = by_id[a["case"]]["expected"]
            sa, sb = a["verdict"] == "supported", b["verdict"] == "supported"
            if sa and sb and expected != "supported":
                passed_wrong += 1
            if sa != sb:
                if expected == "supported":
                    disputed_true += 1
                else:
                    disputed_false += 1
            if not sa and not sb and expected == "supported":
                both_fail_true += 1
        lines.append(
            f"| {model} | {passed_wrong} | {disputed_true} | {disputed_false} | {both_fail_true} |"
        )
    misses: dict[str, Counter[str]] = defaultdict(Counter)
    for model, calls in results["models"].items():
        for r in calls:
            if not _right(r["verdict"], by_id[r["case"]]["expected"]):
                misses[model][f"{by_id[r['case']]['set']}/{by_id[r['case']]['category']}"] += 1
    lines += ["", "Misses by set and category:", ""]
    for model, counter in misses.items():
        lines.append(f"- {model}: " + ", ".join(f"{k} ×{v}" for k, v in counter.most_common()))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", required=True)
    parser.add_argument("--n", type=int, default=3)
    args = parser.parse_args()
    results = run([m for m in args.models.split(",") if m], args.n)
    stamp = results["date"][:10]
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"{stamp}.json").write_text(json.dumps(results, indent=1) + "\n")
    (out / f"{stamp}.md").write_text(report(results))
    print(report(results))


if __name__ == "__main__":
    main()
