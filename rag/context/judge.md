# Judge

## The judge runs on another model family, and its level-to-model mapping comes from a measured experiment

**Id:** fda0071d-05c0-4a5a-9253-6a35dc7d137a
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer design relayed by the coordinator, 2026-10-14 (another family, three levels, the candidate models, measure before fixing the mapping, replace a candidate that fails negation); the evaluation `evals/judge/results/2026-10-14.md` and `docs/judge-eval.md`; the reason for another family is rag's
**Revisit when:** the platform's models or prices change, the fixture grows beyond saturation (two levels at 100%), or the author model changes family

The judge checks a claim against its cited passages with a model of
another family than the author (`qwen3.8-27b`). There are three levels.
The mapping was chosen from a reproducible experiment: 24 hand-written
claims on demo-set passages in six categories, N=3 per level, beside the
word check. It is `low` → `deepseek-v4.1-flash`, `medium` →
`glm-5.3-flash`, `high` → `glm-5.3`. That swaps low and medium against
the first proposal, because the GLM models reason before answering even
with thinking off, so `glm-5.3-flash` cost more per call than
`deepseek-v4.1-flash`. Every candidate caught every negated, swapped and
off-by-one claim, so none was replaced. The word check caught none of
them.

**Reason:** a judge of the author's family shares its blind spots: a
claim the author misread, its sibling tends to read the same way, so
agreement would prove little. That reason is inferred; the brief gave
the rule without one. The mapping is measured rather than set by list
price, because the list price misled here: hidden reasoning tokens made
the "cheap" model the dearer one. A level should mean more cost for more
care, and that holds only with low cheapest. `low`'s misses (a
paraphrase read as a contradiction) fail safe: they cause a revision,
never let a wrong claim pass.

**Rejected alternatives:**
- The first proposal's mapping (glm-5.3-flash as low): `low` would cost
  more than `medium`.
- A judge of the author's family: shared blind spots.
- Fixing the mapping without measuring: the brief ruled it out.

The fixture saturates: two levels score 100%. So `high` over `medium` is
a bet on harder material, not something this experiment shows
(`docs/judge-eval.md`, Limits).
