"""A deterministic check for a claim whose negation differs from its passage.

The word check counts shared words, so "the bridge is not open [1]" passes
over "the bridge is open". This module parses both with spaCy's small
English and German models, splits each sentence into clauses (a predicate
with its own arguments, not those of clauses below it), gives each clause
a polarity, and flags a unit clause whose best-matching passage clause has
the same predicate, a matching subject and the opposite polarity.

The parse decides the scope. What negates is the dependency label (``neg``
in English, ``ng`` in German) plus the closed class of negative
determiners, pronouns and prepositions the small models leave unlabeled
(``NEGATORS``); each counts on the clause it belongs to. Negators that are
coordinated ("no tea and no coffee") count once; two that are not ("nobody
… without") cancel. "not only … but also" and "nicht nur … sondern" are no
negation: the parser attaches the negator to the focus particle. A negated
adjective with a negative prefix whose stem the other clause states
("not uncommon" over "common") is litotes, not a contradiction.

The models load once per process, on first use. A language other than
English or German, or a pair in two languages, is not checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any

from .citations import language_of, overlap

# below this word overlap a passage sentence is about something else
ALIGN_THRESHOLD = 0.5
MODELS = {"en": "en_core_web_sm", "de": "de_core_news_sm"}
# negators the small models leave unlabeled, by lemma (a closed class)
NEGATORS = {
    "en": frozenset(
        {"no", "none", "nothing", "nobody", "nowhere", "neither", "nor", "never", "without"}
    ),
    "de": frozenset(
        {"kein", "keine", "nichts", "niemand", "nie", "niemals", "nirgends", "weder", "ohne"}
    ),
}
# a negator on one of these ("not only", "nicht nur") scopes the particle
FOCUS = frozenset({"only", "just", "merely", "nur", "bloß", "lediglich"})
NEGATION_DEPS = frozenset({"neg", "ng"})
PREDICATE_DEPS = frozenset({"acomp", "attr", "pd", "oc", "xcomp"})
SUBJECT_DEPS = frozenset({"nsubj", "nsubjpass", "sb", "csubj"})
CONTENT_POS = frozenset({"NOUN", "PROPN", "VERB", "ADJ", "ADV", "NUM"})
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@cache
def _nlp(language: str) -> Any:
    import spacy  # loaded once per process, on first use

    return spacy.load(MODELS[language], disable=["ner"])


@dataclass(frozen=True)
class Clause:
    predicate: str  # the lemma of the verb, or of the complement after a copula
    form: str  # its surface form: the lemmatizer is not always consistent
    subject: frozenset[str]  # the subject's content lemmas; empty when none or negative
    words: frozenset[str]  # the content lemmas of its other arguments
    negated: bool
    prefixed: str | None  # "uncommon" → "common": a negated prefixed predicate's stem


def _is_negator(token: Any, language: str) -> bool:
    if token.dep_ in NEGATION_DEPS:
        return token.head.lemma_.lower() not in FOCUS and token.dep_ != "preconj"
    if token.dep_ == "preconj":
        return False
    return token.lower_ in NEGATORS[language] or str(token.lemma_.lower()) in NEGATORS[language]


def _clause_of(token: Any) -> Any:
    """The predicate a token belongs to: the nearest verb, auxiliary or root;
    an auxiliary and its main verb ("can not export", "hat … unterschrieben")
    are one clause, keyed by the main verb."""
    while token.pos_ not in ("VERB", "AUX") and token.dep_ != "ROOT" and token.head is not token:
        token = token.head
    if token.pos_ == "AUX" and token.dep_ in ("aux", "auxpass") and token.head.pos_ == "VERB":
        return token.head
    if token.pos_ == "AUX":
        main = next(
            (c for c in token.children if c.dep_ in ("oc", "xcomp", "pd") and c.pos_ == "VERB"),
            None,
        )
        if main is not None:
            return main
    return token


def _subject(head: Any) -> Any:
    """The clause's subject: on the verb, on the auxiliary above it (German
    "Niemand hat … unterschrieben"), or, for a coordinated verb, on the first."""
    for candidate in (head, head.head):
        # English passives put it on the auxiliary below: "the bridge is closed"
        around = [candidate, *(c for c in candidate.children if c.dep_ in ("aux", "auxpass"))]
        found = next((c for t in around for c in t.children if c.dep_ in SUBJECT_DEPS), None)
        if found is not None:
            return found
        if not (candidate is head and (head.dep_ in ("conj", "cj", "oc", "xcomp", "pd"))):
            break
    return None


def _coordination_root(token: Any) -> Any:
    # German coordinates through the conjunction: B (cj) → und (cd) → A
    while token.dep_ in ("conj", "cj", "cd") and token.head is not token:
        token = token.head
    return token


_PREFIXES = ("un", "in", "im", "ir", "il", "non")


def _stem(lemma: str) -> str | None:
    for prefix in _PREFIXES:
        if lemma.startswith(prefix) and len(lemma) > len(prefix) + 3:
            return lemma[len(prefix) :]
    return None


def clauses(sentence: str, language: str) -> list[Clause]:
    doc = _nlp(language)(sentence)
    heads: dict[int, Any] = {}
    for token in doc:
        if token.pos_ in ("VERB", "AUX") or token.dep_ == "ROOT":
            clause = _clause_of(token)
            heads[clause.i] = clause
    groups: dict[int, set[int]] = {i: set() for i in heads}
    words: dict[int, set[str]] = {i: set() for i in heads}
    for token in doc:
        clause = _clause_of(token)
        if clause.i not in heads:
            continue
        negator = _is_negator(token, language)
        # a negator and what it modifies ("no longer") are not arguments
        if (
            token.pos_ in CONTENT_POS
            and not negator
            and not any(_is_negator(c, language) for c in token.children if token.pos_ == "ADV")
        ):
            words[clause.i].add(token.lemma_.lower())
        if negator:
            # coordinated negators ("keine A und keine B") are one negation
            # a determiner negates its noun ("keine A und keine B" share A's root);
            # any other negator stands for itself ("nobody … without" are two)
            anchor = token.head if token.pos_ == "DET" else token
            groups[clause.i].add(_coordination_root(anchor).i)
    found = []
    for i, head in heads.items():
        complements = [c for c in head.children if c.dep_ in PREDICATE_DEPS]
        predicate_token = complements[0] if head.pos_ == "AUX" and complements else head
        predicate = predicate_token.lemma_.lower()
        subject_token = _subject(head)
        subject = frozenset(
            t.lemma_.lower()
            for t in (subject_token.subtree if subject_token is not None else [])
            if t.pos_ in CONTENT_POS and not _is_negator(t, language)
        )
        negated = len(groups[i]) % 2 == 1
        prefixed = _stem(predicate) if negated else None
        # the clause's own arguments, without the predicate and the subject
        arguments = frozenset(words[i] - subject - {predicate, head.lemma_.lower()})
        found.append(
            Clause(predicate, predicate_token.lower_, subject, arguments, negated, prefixed)
        )
    return found


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text.strip()) if s.strip()]


def contradicts(unit: str, passages: list[str], language: str | None = None) -> bool:
    """True when a clause of ``unit`` and the passage clause it matches
    state the same predicate of the same subject with opposite polarity.
    ``language`` is the output's (told from all its text); without it the
    unit and its passages together tell it. A translated pair is not
    compared."""
    language = language or language_of(" ".join([unit, *passages]))
    if language not in MODELS:
        return False
    for claim in sentences(unit):
        best = max(
            (s for p in passages for s in sentences(p)),
            key=lambda s: overlap(claim, [s]),
            default=None,
        )
        if best is None or overlap(claim, [best]) < ALIGN_THRESHOLD:
            continue
        aligned = clauses(best, language)
        for mine in clauses(claim, language):
            match = _counterpart(mine, aligned)
            if match is not None and match.negated != mine.negated and not _litotes(mine, match):
                return True
    return False


def _counterpart(mine: Clause, theirs: list[Clause]) -> Clause | None:
    """The passage clause stating the same predicate of the same subject with
    the most arguments in common; a tie with the same polarity wins, so a
    negation elsewhere in the passage ("… and does not stop in Wels") never
    outweighs the clause that matches."""
    candidates = []
    for other in theirs:
        same = mine.predicate == other.predicate or mine.form == other.form or _litotes(mine, other)
        if not same or not _same_subject(mine, other):
            continue
        if mine.words and other.words:
            shared = len(mine.words & other.words) / min(len(mine.words), len(other.words))
            if shared < ALIGN_THRESHOLD:
                continue  # the same predicate about something else
        else:
            shared = 0.0
        candidates.append((shared, other.negated == mine.negated, other))
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


def _same_subject(a: Clause, b: Clause) -> bool:
    """Equal, one within the other ("the bridge", "the old bridge"), or one
    unknown or negative ("nobody")."""
    if not a.subject or not b.subject:
        return True
    common = a.subject & b.subject
    return common == a.subject or common == b.subject


def _litotes(a: Clause, b: Clause) -> bool:
    """ "not uncommon" over "common": a negated prefixed predicate whose stem
    the other clause states."""
    return (a.prefixed is not None and a.prefixed == b.predicate) or (
        b.prefixed is not None and b.prefixed == a.predicate
    )
