# Second judge evaluation

Bulletproof verification counts a unit as supported only if two judges of
different model families both say so. Where they disagree, the unit is
marked `disputed`, never silently passed. This page reports how the second
judge was chosen. The first is the high judge, `glm-5.3`; the author model
is `qwen3.8-27b`.

## Method

- **Candidates.** Every text model on the platform outside the GLM and
  Qwen families: `deepseek-v4.1-flash`, `mimo-v2.6-pro-rl`, `minimax-m3`
  and `nemotron-3-nano-omni-30b-a3b-reasoning`. Embedding, speech, image,
  safety, reranker and decision models are left out.
- **Cases.** 104 cases:
  - The judge fixture's 24 claims (`evals/judge/fixture.json`).
  - The negation check's 60 + 20 unit/passage pairs (`evals/negation/`).
  - Expected verdicts for the negation pairs: a contradiction is
    `contradicted`. A trap about another subject than the passage ("other
    clause") is `not_in_source`, because the claim is not in the source;
    the other traps hold.
- **Judge.** The service's own prompt and parser (`judge_unit`, 4000
  output tokens).
- **Runs.** A screening of all candidates with N=1, then the two best and
  the high judge with N=3. Runner: `python -m evals.second_judge.run
  --models … --n 3`. Results are in `evals/second_judge/results/`.

## Results (2026-10-15)

Screening, N=1: `minimax-m3` passed 3 false claims on its own and
`nemotron-3-nano-omni-30b-a3b-reasoning` passed 1, so both were dropped.

N=3, alone:

| model | hits | false supported | false failed | tokens in/out per call | s per call |
|---|---|---|---|---|---|
| glm-5.3 (high) | 308/312 (99%) | 0 | 3 | 300/201 | 7.8 |
| deepseek-v4.1-flash | 288/312 (92%) | 1 | 23 | 293/52 | 1.2 |
| mimo-v2.6-pro-rl | 285/312 (91%) | 0 | 27 | 301/54 | 1.6 |

N=3, paired with the high judge (supported only if both say so):

| second judge | wrongly passed | disputed on true claims | disputed on false claims | both fail a true claim |
|---|---|---|---|---|
| deepseek-v4.1-flash | 0 | 27 of 120 | 1 | 0 |
| mimo-v2.6-pro-rl | 0 | 29 of 120 | 0 | 1 |

- **No false claim passes either pair.** `deepseek-v4.1-flash` passed one
  false claim on its own (an off-by-one year), and the high judge caught it.
- **The cost of strictness is disputes on true claims, about one in
  five.** Almost all are litotes ("not uncommon" over "common"), double
  negation and both-negated pairs, which the second judges read more
  strictly than the high judge. Paraphrases account for a few.
- **Recommendation: `deepseek-v4.1-flash`.** It has slightly fewer
  disputes than `mimo-v2.6-pro-rl`, never fails a true claim together with
  the high judge, and is the fastest. Its price is known: about $0.00008
  per call, against $0.00083 for `glm-5.3`, so it adds about 9% to a
  bulletproof unit's judge cost. It is already the low judge, which does
  not matter here: a level picks the model, and bulletproof pairs the high
  judge with another family.

## Limits

- The cases are short and synthetic or demo text, so the dispute rate on
  real outputs is not measured. A disputed unit is shown, not removed, so
  its cost is the reader's attention.
- Prices for `mimo-v2.6-pro-rl` are not in the price table.
- The whole evaluation cost about $0.28 for the priced models.
