# Retrieval

## An unscoped question is answered from the uploads; generated documents only on scope

**Id:** e7257950-3682-403f-8794-a2edd5331ad3
**Type:** decision
**Status:** active
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
