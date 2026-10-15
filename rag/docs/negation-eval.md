# Negation check evaluation

The word check counts the words a unit shares with its cited passages, so
"the bridge is not open [1]" passes as supported over "the bridge is
open". The negation check (`lasteverlm_rag/negation.py`) catches that case
without a model call. This page reports how it was calibrated before it
was wired in.

## Method

- **Parse.** spaCy 3.8.7 with `en_core_web_sm` 3.8.0 and `de_core_news_sm`
  3.8.0, loaded once per process. Each sentence is split into clauses: a
  predicate with its own arguments. Each clause gets a polarity.
  - A negator is a token labelled `neg` (English) or `ng` (German), or one
    of a closed class of negative determiners, pronouns and prepositions
    that the small models leave unlabelled (no, none, nothing, nobody,
    never, without; kein, nichts, niemand, nie, ohne, weder).
  - The parse decides which clause the negator belongs to.
  - Coordinated negators ("keine A und keine B") count once. Two that are
    not coordinated ("nobody … without") cancel.
  - A negator attached to a focus particle is no negation ("not only … but
    also", "nicht nur … sondern").
  - A negated predicate with a negative prefix whose stem the other clause
    states ("not uncommon" over "common") is litotes.
- **Alignment.** Each unit sentence is paired with the passage sentence it
  overlaps most, at the word check's threshold of 0.5.
  - Within that pair, a unit clause is compared with the passage clause
    that has the same predicate (lemma or surface form) and a compatible
    subject (equal, one inside the other, or unknown or negative), and the
    most arguments in common.
  - A tie goes to the clause with the same polarity, so a negation
    elsewhere in the passage never outweighs the clause that matches.
  - Opposite polarity is a possible contradiction.
- **Language.** The output's language is told from all of its text. A
  translated pair is not compared.
- **Fixtures.** All cases are synthetic and contain no document text.
  - `evals/negation/fixture.json`: 60 pairs, 30 English and 30 German.
    Half are real contradictions: the unit negates what the passage
    states, or the reverse, across not/n't/never/no/without/nothing/nobody/
    cannot/no longer and nicht/nie/kein/ohne/nichts/niemand/nicht mehr.
    The other half are traps: not only/nicht nur, another clause or
    subject, litotes, double negation, both sides negated, and a negation
    elsewhere in the passage.
  - `evals/negation/heldout.json`: 20 more pairs in the same categories
    with other sentences. It was written and committed before any tuning,
    and run once at the end.
  - As a third probe, the judge fixture (`evals/judge/fixture.json`): 24
    longer claims over real demo passages.
- **Runner.** `python -m evals.negation.run` from `rag/` (`--write` saves
  `results/<date>.md`).

## Results (2026-10-15)

| Set | Contradictions flagged | Traps flagged (false positives) |
|---|---|---|
| fixture, first version | 17/30 (57%) | 11/30 (37%) |
| fixture, tuned | 29/30 (97%) | 0/30 (0%) |
| held-out, once | 10/10 (100%) | 0/10 (0%) |
| judge fixture | 1/4 `negated` claims | 0/20 other claims |

- The tuning changed the method, not the cases: clauses instead of whole
  sentences, the subject as part of the match, and the best counterpart
  instead of any. Every change was general (`results/2026-10-15.md`
  lists the remaining miss). The held-out set guards against having fit
  the 60 cases.
- The miss on the fixture is a parse error of the small model: in "the
  system stores user passwords" it reads "stores" as part of a noun
  phrase.
- Three of the judge fixture's four `negated` claims are antonyms ("thickly
  wooded" over "treeless", "too deep" over "shallow enough"), or a refusal
  in a relative clause. A negation check does not see these; they remain
  the judge's job.

## Limits

- Both synthetic sets were written by the same author, in short, clean
  sentences. Real outputs are longer and paraphrase more, so the rates
  above are an upper bound for recall. False positives on real text are
  not measured yet: the check marks a unit, it never removes one.
- Antonyms, numbers, "fails to", "lacks" and un-/in- adjectives without a
  "not" are out of reach.
- Quizzes and flashcards are not checked: their explanations negate wrong
  options on purpose.

## Cost

| | |
|---|---|
| image size (rag) | 356 MB → 802 MB (+446 MB: spaCy 124, numpy 70, blis 34, models 37) |
| import + model load | 0.9 s + 1.6 s, once per process, on first use |
| memory | about +270 MB RSS per process that loads the models |
| time | about 4 ms per unit/passage sentence pair |
