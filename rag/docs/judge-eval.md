# Judge evaluation

A small, reproducible experiment. It asks how well each candidate judge
model tells a claim its cited passages support from one they contradict
or do not contain, and it compares that with the deterministic word check
that outputs and chat run today. The level-to-model mapping of the judge
is chosen from it.

## Method

- **Fixture** (`evals/judge/fixture.json`). Seven passages are copied
  verbatim from the demo set (`ingest/src/lasteverlm_ingest/demo/field-notes.txt`).
  On them sit 24 hand-written claims, four per category. Each claim cites
  passages by key and carries the verdict a correct judge gives:

  | Category | The claim | Expected |
  |---|---|---|
  | `supported` | states a fact of the passage, close to its wording | supported |
  | `paraphrase` | states a fact of the passage in other words | supported |
  | `negated` | says the opposite of the passage | contradicted |
  | `swapped` | gives two facts of the passage to the wrong things | contradicted |
  | `off_by_one` | has a number or year of the passage off by one | contradicted |
  | `not_in_source` | is plausible, but the passage does not state it | not_in_source |

- **Judge** (`lasteverlm_rag/judge.py`, prompt `judge-v1`). It is the code
  the service will run: one call per claim with the claim and its numbered
  passages. A strict JSON answer is parsed deterministically, temperature
  is 0, thinking is off, and the limit is 1500 output tokens.
- **Runs**: every claim three times (N=3) at every level, against the
  platform, with the models of `JUDGE_MODELS`. A hit is the expected
  verdict. A malformed answer counts as a miss.
- **Baseline**: the word check (`lexical-overlap-v1`, threshold 0.5) on
  the same claims. It only says `supported` or `unsupported`. It hits a
  supported claim when it says `supported`, and any other claim when it
  says `unsupported`.
- **Cost**: tokens times the catalogue prices in `evals/judge/prices.json`
  (USD per million tokens). Latency is the wall time of one call.

## Result, 2026-10-14

The full report is `evals/judge/results/2026-10-14.md`, and every call is
in `2026-10-14.json`.

| Category | Word check | `glm-5.3-flash` | `deepseek-v4.1-flash` | `glm-5.3` |
|---|---|---|---|---|
| supported | 4/4 | 12/12 | 12/12 | 12/12 |
| paraphrase | 3/4 | 12/12 | 9/12 | 12/12 |
| negated | 0/4 | 12/12 | 12/12 | 12/12 |
| swapped | 0/4 | 12/12 | 12/12 | 12/12 |
| off_by_one | 0/4 | 12/12 | 12/12 | 12/12 |
| not_in_source | 3/4 | 12/12 | 12/12 | 12/12 |
| **all** | **10/24 (42%)** | **72/72 (100%)** | **69/72 (96%)** | **72/72 (100%)** |

| Model | Malformed | Latency median / max | Output tokens (mean) | Cost per call |
|---|---|---|---|---|
| `deepseek-v4.1-flash` | 0 | 0.61 s / 0.85 s | 55 | 0.000087 USD |
| `glm-5.3-flash` | 0 | 0.96 s / 4.59 s | 198 | 0.000106 USD |
| `glm-5.3` | 0 | 1.30 s / 51.55 s | 172 | 0.000791 USD |

What it shows:

- **The word check is blind to meaning.** It passes every negated,
  swapped and off-by-one claim, because those share almost all their
  words with the passage. This is the gap the judge exists for. Every
  candidate closed it, 36/36 on those three categories.
- **`deepseek-v4.1-flash`** missed one paraphrase all three times. It
  reads "less than a quarter mile" against "within a quarter mile" as a
  contradiction. The miss is on the safe side: in generation it would
  cause one unnecessary revision, never a wrong claim passing.
- **The GLM models reason before answering even with thinking off.**
  They spend 3–4 times the output tokens of `deepseek-v4.1-flash`, so
  `glm-5.3-flash` costs more per call than `deepseek-v4.1-flash`
  despite its lower list price. An early run with a 400-token limit cut
  two of its answers off, which is why the limit is 1500.

## Mapping chosen

| Level | Model | Why |
|---|---|---|
| `low` | `deepseek-v4.1-flash` | cheapest and fastest per call; 96%, and its misses fail safe |
| `medium` | `glm-5.3-flash` | 100% here, at about 1.2× the cost of `low` |
| `high` | `glm-5.3` | 100% here; the strongest candidate, kept for claims harder than this fixture, at about 9× the cost of `low`, with a slow outlier (51 s) |

This swaps `low` and `medium` relative to the first proposal. With the
proposal, `low` would have cost more than `medium`. No candidate failed
the negation cases, so none was replaced. All three are of another family
than the author model (`qwen3.8-27b`).

## Limits

- **Small, hand-written fixture.** 24 claims written by the same person
  who wrote the prompt, so they may fit it. The categories are clear-cut
  on purpose; real output units are longer and mix several facts.
- **One domain, one language.** Short English expedition notes. Nothing
  here measures German, tables or long passages.
- **Nondeterminism.** Temperature 0 does not make the platform's models
  deterministic. N=3 shows stability on these claims, not a rate with a
  useful confidence interval.
- **Saturated.** Two levels score 100%, so this fixture cannot rank them
  above each other. `high` is chosen for strength on harder material,
  which this experiment does not show.
- **List prices.** Costs use the catalogue prices, not billed amounts.

## Rerun

```sh
cd rag
set -a; . /path/to/env-with-INFERENCE_API_KEY; set +a
make judge-eval                          # all levels, N=3
make judge-eval ARGS="--n 1 --levels low"
```

The models come from `JUDGE_MODELS` (core's defaults otherwise). The
results go to `evals/judge/results/<date>.json` and `.md`. The key is read
from the environment and never written anywhere. A rerun on the same day
overwrites that day's files.
