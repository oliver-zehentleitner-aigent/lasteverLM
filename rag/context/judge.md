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

## The judge is opt-in; the deterministic word check stays the default

**Id:** 5af3cb49-03f5-41b3-abe5-daaa4d6a6d6b
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer design relayed by the coordinator, 2026-10-14 (`judge` off by default, supersedes nothing); the measurements in `docs/judge-eval.md`; the reasons and leaving charts out are rag's
**Revisit when:** judge calls become cheap and fast enough to run on every output unnoticed, or users turn the judge on for most outputs anyway

`options.judge` is `off` unless the user picks `low`, `medium` or `high`.
Every output still gets the word check
(2ee513ba-066a-41a3-a9c7-5e906e31c52b), which marks and never blocks. The
judge comes on top of it, never instead of it. It is not offered for a
chart, whose values already have the exact number check.

**Reason:** the word check is free, deterministic and instant, so it can
run on everything. The judge costs a model call per claim unit, plus
revisions, adds seconds, and its verdicts vary between runs (the
evaluation's limits). The evaluation shows what the word check cannot
see (negation, swapped facts, a number off by one: 0 of 12) and that the
judge sees it, so the judge is worth offering. Whether it is worth its
price for a given output is the user's call. Keeping the word check
underneath gives every output, judged or not, the same reproducible
baseline. A chart is left out because its only claims are numbers: an
exact match is already stricter than a model's opinion.

**Rejected alternatives:**
- The judge always on: cost and latency on every output, including ones
  nobody checks.
- The judge replacing the word check: it would lose the free,
  reproducible baseline.
- Judging chart values: nothing to add to an exact match.

## A judged output gets at most three rounds of revision; what still fails is removed and listed

**Id:** 2377f9c1-81c9-4d10-8f5d-4567d2b42d7d
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer design relayed by the coordinator, 2026-10-14 (revise only the failing units in one call, judge only the revised ones again, at most 3 rounds, remove and list what still fails); the reasons are rag's
**Revisit when:** many outputs lose a large share of their units to removal, or revisions start passing by turning vague

With a judge level set, the units judged `contradicted` or
`not_in_source` go to one call of the author model. The call gets only
those units, the judge's reasons and their passages, and must correct
each unit in its own form or drop it. Only revised units are judged
again, for at most three rounds in all. A unit that still fails after the
last round, or that the reviser dropped, is removed from the output and
listed in `provenance.judge.removed` with its text, verdict, reason and
round. Removal happens once, at the end, so unit positions hold through
the rounds.

**Reason:** a bound makes the cost and the wait predictable: one round
when everything passes, three at most, which is also the range an
estimate can show. Rewriting until a unit passes has no bound and pushes
the text towards whatever the judge accepts, which can be vaguer rather
than truer. A unit two revisions could not support most likely has no
support in its passages. Removing it differs from the default "mark,
never block" (2ee513ba-066a-41a3-a9c7-5e906e31c52b) on purpose: the user
asked for the stricter mode. Listing every removal keeps it visible, so
nothing is dropped silently. Sending only the failing units keeps the
revision cheap and leaves the units that passed untouched.

**Rejected alternatives:**
- Rewriting until every unit passes: no bound on cost, and drift
  towards vagueness.
- Keeping failing units, marked: that is the default without the judge;
  the judged mode exists to go further.
- Regenerating the whole document per round: the passed units would
  need judging again, and the cost scales with the document, not with
  its failures.
- Removing silently: hides what the output lost.
