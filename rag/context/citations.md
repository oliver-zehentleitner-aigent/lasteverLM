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
