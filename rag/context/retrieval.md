# Retrieval

## The chat knows the notebook's documents; generated chunks get bounded slots after the uploads

**Id:** a5d7a975-c0da-4ee4-91a9-d8a01adcecc1
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer's click-through, 2026-10-13 (the chat said it saw two PDFs and no mind map in a notebook with three generated documents); coordinator decision the same day
**Revisit when:** generated chunks again crowd out the uploads in citations, or generated documents carry content not derived from the uploads (e.g. user notes)

Two changes to an unscoped `/ask`. The system prompt lists the
notebook's ready documents by kind and title, uploads and generated, and
the model is called with that list even when no passage passes the
floor; only a notebook without a ready document gets the fixed refusal
without a model call. Retrieval searches the uploads and the generated
documents separately: the uploads fill the k slots by score, generated
chunks above the floor may take at most `RETRIEVAL_GENERATED_SLOTS`
(default 2) of them, replacing weaker uploads only, and the passages
list the uploads first. `scope.output_id` stays the way to focus on one
generated document.

**Reason:** the maintainer expects the chat to know the notebook's own
documents: a meta question ("which documents can you see", "the mind
map you made") was answered as if the generated documents did not
exist. The concern behind uploads-only still holds (a general question
answered with citations into a paraphrase instead of the passage it
came from); the slot cap keeps paraphrases a minority of the passages,
and the ordering plus a prompt rule to prefer the uploaded passage when
both say the same make the original the one cited. Calling the model
without passages trades the guarantee that an unmatched question never
reaches the model for answering questions about the notebook itself;
the rules still forbid facts from outside the passages.

**Rejected alternatives:** full inclusion (every ready source in one
top-k, as first designed), rejected because in the first live run four
of five citations went to generated documents; uploads-only (the
superseded entry), rejected because the chat then denies documents the
user can see in the notebook.

## An unscoped question is answered from the uploads; generated documents only on scope

**Id:** e7257950-3682-403f-8794-a2edd5331ad3
**Type:** decision
**Status:** superseded
**Superseded by:** a5d7a975-c0da-4ee4-91a9-d8a01adcecc1
**Evidence:** confirmed
**Source:** first live run on the platform, 2026-10-12; coordinator decision the same evening; confirmed by the maintainer 2026-10-13
**Revisit when:** generated documents carry content that is not derived from the uploads (e.g. user notes), or the maintainer decides otherwise

`/ask` without `scope.output_id` retrieves from sources of kind `pdf`,
`text`, `url` and `image` only; chunks of kind `generated` are left out
of the search. With `scope.output_id` the search is restricted to that
one generated source, as before. `RETRIEVAL_INCLUDE_GENERATED=true`
turns the old behaviour back on; the default is off.

**Reason:** in the first live run, an unscoped question asked after five
outputs existed was answered with four of five citations into generated
documents. Those documents restate the uploads, so citing them for a
general question is circular: the reader is sent to a paraphrase instead
of the passage it came from. "Ask about this" on a document remains the
way to question a generated document, and that path is unchanged.

**Rejected alternatives:** demoting generated chunks (a similarity
penalty or a secondary sort key) instead of excluding them, rejected
because a penalty needs tuning against real data and still cites the
paraphrase when the upload does not rank; keeping the behaviour as first
designed (every ready source retrievable, generated included), rejected
for the circularity above, kept reachable by the configuration switch in
case the maintainer prefers it.

## The user's source selection narrows chat and generation, by link id, per request

**Id:** fb02e210-b924-46d1-85d1-861b9f8ae11d
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer's walkthrough, 2026-10-13 (the notebook model of ticking which sources are active); coordinator decision the same day
**Revisit when:** generated documents become selectable in the sources list, or the selection has to persist across sessions or devices

`/ask` and `POST .../outputs` take optional `source_ids`; absent or empty
means all. They are link ids (the `sources.id` of this notebook), and only
uploads qualify; anything else is a 422. On `/ask` the uploads search is
filtered to the selection, the generated slots are not, and the document
list in the system prompt keeps every document but marks deselected
uploads `not in scope`. An output stores the selection in
`options.sources` and is generated from those sources' summaries and
chunks only, balanced over the selection.

**Reason:** the maintainer expects the user to decide which sources chat
and generation use (confirmed). Link ids, because they are the ids the
notebook's API hands out and the rest of rag already speaks: citations,
retrieval results and the generated-document scope are all link ids,
while the library id behind a link is shared by every notebook the file
is linked into (inferred, this entry's own reasoning). Generated
documents keep their slots because the sources list never shows them, so
a selection cannot include them; marking deselected uploads instead of
hiding them lets the chat explain why it does not see a document. The
selection travels with each request, so rag holds no selection state and
a stored output says what it was made from.

**Rejected alternatives:** library ids (they would need mapping back to
this notebook's link for every citation); filtering the generated slots
by the selection too (no generated id could ever be selected, so
generated documents would vanish from every filtered chat); leaving
deselected documents out of the document list (the chat would deny
documents the user can see). Whether a persisted selection (a flag on
the link) was considered is unknown.

## A scoped question retrieves without a similarity floor and with a larger k

**Id:** 0208ab91-804b-4d29-b35e-43bd89695b7c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** frontend click-through on the first deploy, 2026-10-12; coordinator decision the same evening

With `scope.output_id`, retrieval runs over that one generated source
with no similarity floor and k=12 (all of its chunks when it has fewer).
Unscoped questions keep the configured floor and k.

**Reason:** "Summarize this document in one sentence" on a report was
answered with the refusal: a summary-type question matches no chunk
strongly, so every chunk fell under the floor. The scope already bounds
the context to one document, which is what the floor protects against
elsewhere; without it the question is answered from the whole document.

**Rejected alternative:** a lower floor for scoped questions, rejected
because any floor can still drop every chunk of a short document for a
question that resembles none of them.

## Incident: an uploaded PDF was ready but never retrieved (resolved, cause not proven)

**Id:** 54626e80-33da-49e5-8bfd-2a92673a654a
**Type:** incident
**Status:** active
**Evidence:** inferred
**Source:** maintainer's click-through, 2026-10-13, and his re-test on 0.7.1; diagnosis session the same day
**Revisit when:** a ready source is again missing from retrieval, or the rows of the original notebook become available

A notebook held two ready PDFs. Unscoped questions about the second one
("was ist vnc?") were refused or answered from the first PDF only; the
second was never among the retrieved passages, although a generated
report summarised it in detail. On 0.7.1 the same questions retrieve it,
reproducibly.

What was checked: the same setup with text files on the demo account
retrieved correctly, so German embeddings, the similarity floor and k
were not the cause; the report's detail came from the source summary
(written from the full extracted text), which proves extraction but not
searchable chunks; the write path cannot produce a ready source without
chunks, nor vectors of the wrong count, dimension or order. The live
rows were never read (production reads were not permitted in that
session), so the cause stays inferred. Two candidates fit: a worker that
claimed the source before its stored object was complete, so chunks and
embeddings were written from a missing or partial download (fixed by
ingest's claim change, #182); or the per-library re-keying of chunks in
the 0.5.0 source-library change, which rewrote how a notebook reaches
its chunks.

The lesson that stays: a source must not become ready unless its chunks
carry usable embeddings. A vector with a zero norm or a non-finite
component makes the cosine distance NaN, which the similarity floor
drops without a trace. The guard belongs in core's embedder, which
every service goes through: rejecting such a vector as a provider error
makes ingest fail the source loudly and makes rag's question and output
embeddings fail visibly, instead of a source sitting ready and
unsearchable.
