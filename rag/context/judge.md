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
agreement would prove little. That reason is inferred; the rule was set
without one. The mapping is measured rather than set by list
price, because the list price misled here: hidden reasoning tokens made
the "cheap" model the dearer one. A level should mean more cost for more
care, and that holds only with low cheapest. `low`'s misses (a
paraphrase read as a contradiction) fail safe: they cause a revision,
never let a wrong claim pass.

**Rejected alternatives:**
- The first proposal's mapping (glm-5.3-flash as low): `low` would cost
  more than `medium`.
- A judge of the author's family: shared blind spots.
- Fixing the mapping without measuring: list prices had already
  misled once (hidden reasoning tokens), so an unmeasured mapping could
  make a higher level cheaper than a lower one.

The fixture saturates: two levels score 100%. So `high` over `medium` is
a bet on harder material, not something this experiment shows
(`docs/judge-eval.md`, Limits).

## The judge is opt-in; the deterministic word check stays the default

**Id:** 5af3cb49-03f5-41b3-abe5-daaa4d6a6d6b
**Type:** decision
**Status:** superseded
**Superseded by:** 2567fcf4-09b1-4bc9-80e7-759bce4c3326
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

## A judge without a usable answer leaves its unit marked, never failing the output

**Id:** 755ed7ef-5d49-4d14-aec5-8cb96ec9f546
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** a judged audio on 0.20.0 that failed with "the model provider failed 3 times (glm-5.3: ProviderError)", reported by the maintainer and relayed by the coordinator, 2026-10-15; its logs were gone with the rollout, so the cause is read from the code (no SDK cause, therefore not a timeout or an HTTP status, so an empty or unusable judge answer); the coordinator's go the same day for the retry, the marked unit, the larger budget and the failure kinds
**Revisit when:** many units end without a verdict (a judge model unfit for its level), or a judge model's reasoning outgrows 6000 tokens

A judge call that brings no usable answer (empty, unparseable, an
unknown verdict, or an SDK error after the client's own retries) is
tried once more. If that fails too, the unit keeps its text and gets
`judge: {"verdict": null, "reason": "the judge gave no usable answer:
<kind>"}`, counted as `no_usable_answer`. It is neither revised nor
removed, and the output goes on. The judge may use up to 6000 output
tokens. The failure kinds also name what failed in the output's error
and the worker's log, and an unusable answer's structure (its keys, the
reason's type and length, why the model stopped, how long it ran; never
its text) goes on the unit and into the log.

**Re-checked 2026-10-15:** the revisit condition (a judge's reasoning
outgrowing 4000 tokens) nearly fired: on long production-like passages
glm-5.3-flash used up to 3507. The limit went to 6000; only used tokens
are billed. Reports of "answer without a reason" could not be reproduced
in 295 calls, so the structure is now recorded to tell a cut-off answer
from an empty reason. The decision holds.

This is the one place an empty or unusable answer does not fail the
call: everywhere else it is a provider failure (866cf948-6745-40f1-8a82-a8e20c19b5a7
in `providers.md`), because a judgement is an annotation the output can
stand without.

**Reason:** the judge checks an output; it is not the output. Before,
one unusable judge answer among dozens failed the whole job. The retry
then paid again for retrieval, writing and every judge call already
made, and after three attempts the user had paid three times for
nothing. A unit without a verdict is visible as such, like any other
status, so nothing is hidden. The larger budget addresses the likely
cause: the GLM judges reason before answering even with thinking off.
glm-5.3-flash used up to ~500 tokens in the evaluation, and under load
a glm-5.3 answer can run out at 1500. Unused room costs nothing.

**Rejected alternatives:**
- Failing the output, as before: recharges everything for an add-on's
  hiccup.
- Treating a missing verdict as "supported": claims a check that never
  happened.
- Treating it as failing (revise, then remove): removes text no one
  judged wrong.
- A shared per-model concurrency limit across workers: nothing shows a
  rate limit (a 429 would read "HTTP 429"), and it needs state shared by
  all workers.

## A judgement on request only annotates; revising is for the judge chosen at generation

**Id:** d6795a59-2ad9-4f16-8c35-2094d1b4ae99
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** the code and README since the judge was added, 2026-10-14 (`judge_stored_output` and `judge_message`: "annotate only, nothing is revised or removed"); the reason is read from the code, not stated anywhere
**Revisit when:** users ask to have a judged output corrected after the fact, or the web offers to regenerate from a judgement

`POST …/outputs/{id}/judge` and `POST …/messages/{id}/judge` judge an
existing output's or chat answer's claims in one round. Each claim gets
its `judge` (one retry, then a unit without a verdict, as in
755ed7ef-5d49-4d14-aec5-8cb96ec9f546), and nothing is revised or
removed. Revising and judging again, up to three rounds with what still
fails removed (2377f9c1-81c9-4d10-8f5d-4567d2b42d7d), happens only when
the judge is chosen at generation (`options.judge`). A judgement on
request is its own `judge` action.

**Reason:** inferred from the code. An output or an answer that exists has already
been read, shared or used as a source; rewriting it in place would
change what the reader saw without a trace, and a revision needs the
generation's own prompt and passages in the generator's form. Marking
its claims tells the reader which ones hold without changing the
document. A corrected version is a new generation with the judge on.

**Rejected alternatives:** unknown.

## Verification levels: how much checking an output gets is one setting, from free to a judge on everything

**Id:** 2567fcf4-09b1-4bc9-80e7-759bce4c3326
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the coordinator, 2026-10-15 (a verification level in the settings, preselected in the output form and changeable per output, asked by the chat when unclear; its price shown before Create; a "bulletproof" level that may cost but checks reliably; a unit the word check cannot check is judged from standard up; translate-then-compare rejected); rag's plan checked against the code and confirmed the same day (thorough keeps today's three rounds, standard includes unsupported units, chat not capped, judge_default high maps to bulletproof)
**Revisit when:** most users pick the same level (the choice then costs attention for nothing), or standard's judge rarely changes a doubted unit's reading

An output's `verification` is `basic`, `standard` or `thorough`
(and `bulletproof`, below).
Basic is the word check and the negation check, free. Standard also
judges, once at the low judge and annotate only, every unit that check
doubts: unsupported, unverified (another language) and
possible_contradiction, so each of them ends with a real verdict.
Thorough is the judge at medium with up to three rounds of revision, as
the judge option did before. The estimate prices every level before
Create; the form preselects the user's `verification_level`; the agent
asks for the level when the message does not say and the user's level is
above basic. Chat answers follow the user's level, annotate only. The
older `judge` option and `judge_default` keep working, read as their
level.

**Reason:** a user cares how reliable a document is and what it costs,
not which judge model at which level runs. One setting from free to
thorough says that directly, and showing every level's price before
Create lets the user decide per output. Standard spends a judge only
where the free check has a doubt, which is where a verdict changes what
a reader can trust; a unit in another language or with too little word
overlap otherwise stays without any verdict. Thorough keeps the existing
three rounds rather than one, so no level is weaker than the judge it
replaces.

**Re-checked 2026-10-15:** its revisit condition (the second judge for
bulletproof chosen) fired; `bulletproof` now exists (873eac12-9c2e-4764-a906-cc503bc98ff2).
The levels decision holds; the revisit condition now reads without it.

**Rejected alternatives:**
- A judge on or off with a model level (the setting before): it asks
  for a technical choice and leaves doubted units of an unjudged output
  without a verdict.
- Translating a unit in another language and comparing words again: an
  LLM call anyway, and a worse one than the judge.
- Thorough with one revision round: weaker than the medium judge it
  replaces.

## Bulletproof pairs the high judge with a second judge of another family; their disagreement is shown as disputed

**Id:** 873eac12-9c2e-4764-a906-cc503bc98ff2
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (a level that may cost but checks safely and reliably; supported only if both judges agree; disagreement marked disputed and never silently passed; the second judge chosen by evaluation; the UI text "the two judges disagree, read the passage yourself"; the measured dispute rate stated); `docs/second-judge-eval.md` (N=3, 104 cases)
**Revisit when:** the dispute rate on real outputs is far from one in five, the second judge passes a false claim the high judge also passes, or the platform's model list changes

At `bulletproof` every unit is judged by the high judge (`glm-5.3`) and,
at the same time, by a second judge of another family
(`deepseek-v4.1-flash`, `SECOND_JUDGE_MODEL`). A unit is supported only
if both say so. If both fail it, it is revised and removed as at
thorough. If they disagree, it is `disputed`: revised like a failing
unit and, still disputed after the third round, kept and marked "the two
judges disagree; read the passage yourself". It is never removed for it
and never passed. In chat answers the same pair annotates each
paragraph.

**Reason:** a level the user picks for safety must not pass a claim one
competent judge rejects. Two judges of different families share fewer
blind spots, and requiring both to agree turns a single judge's miss
into a visible dispute. In the evaluation neither pair passed a false
claim, while one candidate alone did. Disputes are the price: on the
synthetic cases about one in five true claims ended disputed, mostly
litotes, double negations and paraphrases the second judge read more
strictly. Showing a dispute, rather than removing or passing the unit,
leaves that judgement to the reader with the passage at hand.
`deepseek-v4.1-flash` disputed slightly fewer true claims than
`mimo-v2.6-pro-rl`, never failed a true claim together with the high
judge, is the fastest, and adds about 9% to the judge cost.

**Rejected alternatives:**
- `minimax-m3` and `nemotron-3-nano-omni-30b-a3b-reasoning` as the second
  judge: each passed false claims on its own in the screening.
- `mimo-v2.6-pro-rl`: slightly more disputes, and once both judges
  failed a true claim; its price is not in the price table.
- Removing disputed units: a true claim would vanish on one judge's
  stricter reading.
- Passing them: a false claim one judge caught would pass.
