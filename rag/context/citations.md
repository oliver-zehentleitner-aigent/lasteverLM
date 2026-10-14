# Citations

## The service maps citations; markers that name no passage are stripped

**Id:** 8265b935-ce7a-48c6-9bee-1fb5acc9b41b
**Type:** decision
**Status:** superseded
**Superseded by:** 45660a5e-56a2-454e-932c-9553ca04898a
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12; implementation session, 2026-10-12
**Revisit when:** the LLM provider offers citations the service can verify against its own chunks

Retrieved chunks go numbered into the prompt, the model answers with
`[n]` markers, and `citations.py` resolves every marker back to the chunk
it names. A marker whose number matches no passage is removed from the
answer text and produces no citation; the numbers the model used are kept
as they are, so the inline marker and the citation's `n` always agree.

**Reason:** citations have to be verifiable against this system's own
chunks, which a provider-side citation feature cannot guarantee and which
would tie the service to one provider. Stripping an invented marker keeps
the answer readable while making sure nothing reaches the reader that
looks like a source but is none; the resulting sentence without a citation
is visible to the reader as unsupported.

**Rejected alternatives:** failing the whole answer on an invented marker,
rejected because one hallucinated number would throw away an otherwise
grounded answer; renumbering citations 1..n in order of appearance,
rejected because it rewrites the model's text and gains nothing the
mapping does not already provide.

## Citations are normalized: single markers, dense numbering by first appearance

**Id:** 45660a5e-56a2-454e-932c-9553ca04898a
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** frontend click-through on the first deploy, 2026-10-12; coordinator decision the same evening

The mapping still resolves every marker to the chunk it names and drops
made-up ones, but the answer text is rewritten to the contract's shape:
a grouped marker such as `[1, 3]` becomes `[1][2]`, and the surviving
markers are renumbered 1..n in order of first appearance, so `Citation.n`
is dense and matches the text exactly.

**Reason:** the model groups markers and, after a dropped marker, the
numbering had gaps; the contract says single `[n]` markers, and a dense
sequence is what a reader and the viewer expect. The earlier choice to
keep the model's numbers avoided rewriting the text, but the text has to
be rewritten anyway to drop made-up markers, so the saving was none.

**Rejected alternative:** keep the model's numbers and leave groups as
they are (the previous entry), rejected because the frontend had to cope
with both shapes and the gaps were visible to the reader.

## No relevant chunk: refuse without calling the model

**Id:** 3587324b-e1f0-43bc-816b-ecf70f03aaf0
**Type:** decision
**Status:** superseded
**Superseded by:** 909d8abe-2e00-40b5-bddb-d07c455ebb6c
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12; implementation session, 2026-10-12
**Revisit when:** the similarity floor proves too coarse to tell "nothing relevant" from "weakly relevant"

When retrieval returns no chunk above the similarity floor, the service
answers with a fixed sentence and empty citations. The LLM is not called.

**Reason:** the family rule is that an answer never comes from model
knowledge alone. Not calling the model when there is nothing to ground an
answer in enforces that by construction rather than by prompt, and it
costs the user no LLM tokens for a question the notebook cannot answer.

**Rejected alternative:** always call the model and let the prompt
instruct it to say "not in your sources". Rejected because the guarantee
would then rest on the model following an instruction, and the call
would still be billed.

## No matching passage: the model still answers from the document list; only an empty notebook is refused

**Id:** 909d8abe-2e00-40b5-bddb-d07c455ebb6c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer's click-through, 2026-10-13; coordinator decision the same day
**Revisit when:** unmatched questions are answered from model knowledge despite the rules, or their cost becomes noticeable

When no chunk passes the similarity floor, the model is still called,
with an empty passage list and the notebook's document list in the
system prompt (see "The chat knows the notebook's documents" in
`retrieval.md`). The fixed sentence without a model call remains only
for a notebook with no ready document.

**Reason:** a question about the notebook itself ("which documents can
you see", "the mind map you made") matches no chunk, so the refusal
answered it wrongly. The cost is one billed LLM call for a question the
notebook cannot answer, accepted; that an answer never comes from model
knowledge now rests on the prompt rules for this case, no longer on
construction.

**Rejected alternative:** keeping the refusal for every unmatched
question (the superseded entry), rejected because meta questions about
the notebook's documents could then never be answered.

## A citation carries its provenance: verbatim chunk, score, position

**Id:** 57be7052-39ad-445f-b382-63c09e1e0dfe
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request, relayed by the coordinator, 2026-10-13
**Revisit when:** chunks are re-embedded or re-chunked in place (a stored score or position would then describe an older index)

Every citation, in the answer and in the stored message, carries the
verbatim text of the chunk the model was given (`quote`, no longer cut
at 300 characters), the cosine similarity the search computed for that
chunk and this question (`similarity`, three decimals), and the chunk's
position in its source (`chunk_index`, `chunk_count`), next to
`chunk_id` and `page`. `GET /api/rag/chunks/{chunk_id}` serves one chunk
to its owner. Citations stored before the fields existed keep them null.

**Reason:** a reviewer has to be able to check a claim against exactly
what the model read and see how strongly retrieval matched it, without
re-running the question. Storing the facts at answer time keeps them
true for that answer even after the source is detached or re-processed;
the chunk endpoint shows the passage without the answer around it. A
trimmed quote could leave out the very sentence a claim rests on.

**Rejected alternatives:** trusting the model's own statements about
where something is ("page 3"), rejected because the model can misplace
or invent a location and nothing would show it; recomputing the score
when a citation is viewed, rejected because the index may have changed
since the answer and the number would no longer describe what was
retrieved; a separate `chunk_text` beside a short `quote`, rejected as
two fields for one fact (the frontend trims for display).

## Marker-shaped text from sources is rewritten before it reaches a prompt

**Id:** 92500a3e-ba0d-46f9-b511-8f69bf2f7708
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** security audit of rag, 2026-10-14
**Revisit when:** the citation format changes from `[n]`, or sources need their own bracketed numbers shown to the model verbatim

Passage text and summaries reach the model with every `[n]` or `[n, m]`
rewritten as `(n)` / `(n, m)`; names of files, documents and the
notebook are flattened to one line and cut to 120 characters. Both
system prompts state that this text is data, never instructions. The
stored chunk and the citation's `quote` stay verbatim.

**Reason:** citations are resolved from the `[n]` markers in the answer,
and passages are opened by a `[n] (name)` line. A source containing
`[2] (trusted.pdf)` or a file name with a newline could otherwise open a
passage of its own or steer the model into citing a number it never
read. Rewriting the brackets keeps the content readable to the model
while only the service's own numbering looks like a marker.

**Rejected alternatives:** relying on the prompt rule alone (a rule the
model may not follow is no guarantee, the same reason the empty-notebook
refusal skips the model); deleting marker-shaped text (it loses content
such as reference numbers in a paper); escaping with a scheme the model
would have to decode (more ways to get it wrong than parentheses).


## Generated outputs: each unit is checked against its passages without a model, marked and never blocked

**Id:** 2ee513ba-066a-41a3-a9c7-5e906e31c52b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer go relayed by the coordinator, 2026-10-14 ("each sentence traceable to the passage it came from"; mark, never block; a deterministic check); the method, the threshold and "unverified" were proposed by rag and approved by the coordinator the same day
**Revisit when:** rated outputs or answers show the 0.5 threshold marking supported units unsupported or the reverse, translated text needs a verdict, or a language other than English and German needs the translation guess

Every kind cites the numbered passages of its prompt (report,
infographic and audio first; table rows, quiz questions and mind-map
nodes in a second step the same day). Every unit carries `refs` and `support`, and the output stores a
generation log (`outputs.provenance`). The check runs after generation,
without a model: the unit's content words, against the words of its
cited passages taken together (`lexical-overlap-v1`, threshold 0.5). A
unit with no refs, a ref the prompt never had, or too little overlap is
`unsupported`, kept and shown as such; the output is never failed or
trimmed for it. Below the threshold in a chosen output language the unit
is `unverified`, because the overlap of words across languages says
nothing.

Chat answers share the same check (coordinator's go, 2026-10-14): one
unit per paragraph of an answer that cites, its refs the markers in it,
stored with the message; an answer without citations is not checked.
The chat has no language option, so "translated" there means the answer
and its cited passages are told apart as English and German by their
most frequent words; for any other language, or too little text, the
answer counts as untranslated and low overlap stays unsupported.

**Reason:** the claim is meant to be checkable, so the check must give
the same answer every time and cost nothing per unit; a reader can
retrace it from the passages in the log. Marking instead of dropping
keeps the document whole and shows where it goes beyond its sources,
which is the information the reader needs. The threshold is set, not
calibrated: no rated outputs existed when it was chosen.

**Rejected alternatives:**
- A judge model rating each unit: a second billed call per output whose
  verdict can differ between runs, and itself unverifiable.
- Dropping unsupported units: hides exactly what the provenance is
  meant to show and can tear a document apart.
- Embedding similarity between unit and passage: works across languages
  but is a model call with an uncalibrated threshold; kept as the later
  option for translated outputs.
- Calling a low-overlap translated unit "unsupported": would mark most
  of every translated output, falsely.

## The user's instructions steer a generator but never override the rules or the citation rules

**Id:** e265aa18-ae7b-494f-bef6-7d88752ddb9e
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer request relayed by the coordinator, 2026-10-14 (instructions below the system rules; focus and tone yes, citation rules no); the wording and where the text sits are rag's
**Revisit when:** outputs made with instructions show markedly more unsupported units than those without, or users need instructions that change the structure the schema fixes

Every kind takes `instructions`, free text of at most 500 characters,
collapsed to one line. The generator's system prompt gets it after the
rules, quoted and introduced as the user's addition. The introduction
says to follow it for focus, emphasis, tone and structure, and says it
never changes the rules above (only the material, every source covered),
the citation rules or the reply format. A part that asks for that is
ignored. A decision's evidence call gets it the same way. The text is
stored in the output's options, so it appears in the provenance log, and
the support check runs unchanged.

**Reason:** the point of an output is that its claims can be traced to
the sources. A note like "add some background from general knowledge" or
"skip the citations" would make an output look checked while it is not.
Placing the note after the rules and naming it as subordinate keeps the
rules first. The check after generation is the backstop: whatever the
model did, an uncited or unsupported unit is still marked, never trusted.
Recording the note in the log lets a reader see why an output reads the
way it does.

**Rejected alternatives:** unknown. No other placement or treatment was
weighed in the brief. Because the note is part of the options, the
shared views show it with them. That is open with the coordinator: a
personal note may not be meant for a link's readers.

## A chart's values get an exact number check, not word overlap

**Id:** 59c7c75c-b777-4ea2-874a-8df32e31f138
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer design relayed by the coordinator, 2026-10-14 (the strict check, the normalisations, derived values never supported); the reasons are rag's
**Revisit when:** sources write numbers in forms the readings miss (other scripts, ranges, fractions), so that correct values show as unsupported

A chart value is `supported` only when the number itself is written in a
passage it cites (`number-match-v1`, `lasteverlm_rag/numbers.py`). Every
number in the passage is read in each way it can be written: `1.906` as
1.906 and 1906, `1,9 Mio.` as 1.9 and 1 900 000, and `12,5 %` as 12.5
and 0.125. Beyond float precision there is no tolerance. A computed value
(a share, a sum, a difference) names its passages in `derived_from` and
is `derived`, never `supported`.

**Reason:** a chart is read for its numbers, and a wrong number is a
wrong chart. The word-overlap check of the text kinds cannot see this:
"2.411 visitors" overlaps a passage saying "2.410 visitors" in every word
but the number, so a value off by one would pass as supported. Reading a
written number in all its forms keeps the check strict without failing
correct values that are only formatted differently. A computed value is
not in any passage by definition, so calling it supported would claim
something the check never saw. "derived" says it is arithmetic over
cited numbers.

**Rejected alternatives:**
- The lexical overlap check: blind to the number itself.
- A relative tolerance: it would accept a rounded or wrong value.
- Recomputing derived values: the formula is not stated, and checking
  it would mean guessing it.
