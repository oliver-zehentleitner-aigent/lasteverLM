"""The judge evaluation: every claim of the fixture, judged N times at every
level against the platform, beside the deterministic word check on the same
claims.

    make judge-eval                       # all levels, N=3
    make judge-eval ARGS="--n 1 --levels low"

Reads ``INFERENCE_API_KEY`` (and ``INFERENCE_BASE_URL``, ``JUDGE_MODELS``)
from the environment like the service; the key is never written anywhere.
Writes ``results/<date>.json`` (every call) and ``results/<date>.md`` (the
report).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lasteverlm_core import (
    JUDGE_LEVELS,
    InferenceSettings,
    OpenAICompatibleLLM,
    ProviderError,
    Usage,
)
from lasteverlm_core.providers.openai_compat import make_client

from lasteverlm_rag.citations import CHECK_METHOD, OVERLAP_THRESHOLD
from lasteverlm_rag.judge import JUDGE_MAX_TOKENS, JUDGE_PROMPT_VERSION, judge_unit
from lasteverlm_rag.models import Unit
from lasteverlm_rag.provenance import check_against

HERE = Path(__file__).parent
WORKERS = 4


def numbered(claim: dict[str, Any], passages: dict[str, str]) -> dict[int, str]:
    return {n: passages[key] for n, key in enumerate(claim["refs"], start=1)}


def word_check(claim: dict[str, Any], passages: dict[str, str]) -> str:
    """The deterministic check as outputs run it: ``supported`` or ``unsupported``."""
    texts = numbered(claim, passages)
    unit = Unit({}, claim["text"], list(texts))
    check_against([unit], texts, translated=False)
    return str(unit.target["support"])


def judge_once(
    llm: OpenAICompatibleLLM, claim: dict[str, Any], passages: dict[str, str]
) -> dict[str, Any]:
    texts = numbered(claim, passages)
    started = time.monotonic()
    record: dict[str, Any] = {"claim": claim["id"]}
    usage: Usage | None
    try:
        judgement, result = judge_unit(llm.complete, claim["text"], texts)
        usage = result.usage
        record.update(
            verdict=judgement.verdict,
            reason=judgement.reason,
            quote=judgement.quote,
            quote_verbatim=judgement.quote_verbatim,
        )
    except ProviderError as exc:
        usage = exc.usage
        record.update(verdict=None, error=str(exc)[:300])
    record["latency_s"] = round(time.monotonic() - started, 3)
    record["tokens_in"] = usage.tokens_in if usage else 0
    record["tokens_out"] = usage.tokens_out if usage else 0
    return record


def cost(record: dict[str, Any], price: dict[str, float]) -> float:
    return float(record["tokens_in"] * price["in"] + record["tokens_out"] * price["out"]) / 1e6


def run(levels: list[str], n: int) -> dict[str, Any]:
    fixture = json.loads((HERE / "fixture.json").read_text())
    prices = json.loads((HERE / "prices.json").read_text())
    settings = InferenceSettings.from_env()
    client = make_client(settings)
    passages, claims = fixture["passages"], fixture["claims"]
    results: dict[str, Any] = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "prompt_version": JUDGE_PROMPT_VERSION,
        "max_tokens": JUDGE_MAX_TOKENS,
        "n": n,
        "prices": prices,
        "baseline": {
            "method": CHECK_METHOD,
            "threshold": OVERLAP_THRESHOLD,
            "results": {c["id"]: word_check(c, passages) for c in claims},
        },
        "levels": {},
    }
    for level in levels:
        model = settings.judge_models[level]  # type: ignore[index]
        llm = OpenAICompatibleLLM(client, model, max_tokens=JUDGE_MAX_TOKENS)
        jobs = [c for c in claims for _ in range(n)]
        with ThreadPoolExecutor(WORKERS) as pool:
            records = list(pool.map(judge_once, [llm] * len(jobs), jobs, [passages] * len(jobs)))
        results["levels"][level] = {"model": model, "calls": records}
    return results


def pct(hit: int, total: int) -> str:
    return f"{hit}/{total} ({100 * hit / total:.0f}%)" if total else "–"


def report(results: dict[str, Any], fixture: dict[str, Any]) -> str:
    claims = {c["id"]: c for c in fixture["claims"]}
    categories = list(fixture["categories"])
    levels = results["levels"]
    lines = [
        f"# Judge evaluation, {results['date'][:10]}",
        "",
        f"Prompt `{results['prompt_version']}`, N={results['n']} calls per claim and level, "
        f"{len(claims)} claims from the demo set. A hit is the expected verdict. The baseline "
        f"is the deterministic word check (`{results['baseline']['method']}`, threshold "
        f"{results['baseline']['threshold']}): a hit when it says `supported` for a supported "
        "claim and `unsupported` for any other.",
        "",
        "## Hit rate per category",
        "",
        "| Category | Expected | Word check | "
        + " | ".join(f"{lv} (`{levels[lv]['model']}`)" for lv in levels)
        + " |",
        "|---|---|---|" + "---|" * len(levels),
    ]
    baseline = results["baseline"]["results"]
    for category in categories + ["all"]:
        ids = [i for i, c in claims.items() if category in ("all", c["category"])]
        expected = claims[ids[0]]["expected"] if category != "all" else "–"
        word_hits = sum(
            (baseline[i] == "supported") == (claims[i]["expected"] == "supported") for i in ids
        )
        row = [category, expected, pct(word_hits, len(ids))]
        for lv in levels:
            calls = [r for r in levels[lv]["calls"] if r["claim"] in ids]
            hits = sum(r["verdict"] == claims[r["claim"]]["expected"] for r in calls)
            row.append(pct(hits, len(calls)))
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "## Calls per level",
        "",
        "| Level | Model | Calls | Malformed | Quote verbatim | Latency median / max (s) "
        "| Tokens in / out (mean) | Cost per call (USD, mean) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for lv, data in levels.items():
        calls = data["calls"]
        price = results["prices"]["models"].get(data["model"])
        ok = [r for r in calls if r["verdict"] is not None]
        lat = [r["latency_s"] for r in calls]
        mean_cost = f"{statistics.mean(cost(r, price) for r in calls):.6f}" if price else "no price"
        lines.append(
            f"| {lv} | `{data['model']}` | {len(calls)} | {len(calls) - len(ok)} | "
            f"{pct(sum(r.get('quote_verbatim', False) for r in ok), len(ok))} | "
            f"{statistics.median(lat):.2f} / {max(lat):.2f} | "
            f"{statistics.mean(r['tokens_in'] for r in calls):.0f} / "
            f"{statistics.mean(r['tokens_out'] for r in calls):.0f} | {mean_cost} |"
        )
    lines += ["", "## Misses", ""]
    for lv, data in levels.items():
        wrong: Counter[tuple[str, str]] = Counter()
        for r in data["calls"]:
            if r["verdict"] != claims[r["claim"]]["expected"]:
                wrong[(r["claim"], str(r["verdict"]))] += 1
        if not wrong:
            lines.append(f"- {lv}: none")
            continue
        by_claim: dict[str, list[str]] = defaultdict(list)
        for (cid, verdict), count in sorted(wrong.items()):
            by_claim[cid].append(f"{verdict} ×{count}")
        for cid, got in by_claim.items():
            lines.append(
                f"- {lv}: `{cid}` \"{claims[cid]['text']}\" (expected "
                f"{claims[cid]['expected']}): {', '.join(got)}"
            )
    lines += ["", f"Prices: {results['prices']['source']}.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", default=",".join(JUDGE_LEVELS))
    parser.add_argument("--n", type=int, default=3)
    args = parser.parse_args()
    levels = [lv for lv in args.levels.split(",") if lv]
    results = run(levels, args.n)
    fixture = json.loads((HERE / "fixture.json").read_text())
    stamp = results["date"][:10]
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"{stamp}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    (out / f"{stamp}.md").write_text(report(results, fixture))
    print(f"wrote {out / stamp}.json and .md")


if __name__ == "__main__":
    main()
