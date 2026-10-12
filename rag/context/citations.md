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
**Status:** active
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
