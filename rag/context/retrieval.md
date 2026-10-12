# Retrieval

## An unscoped question is answered from the uploads; generated documents only on scope

**Id:** e7257950-3682-403f-8794-a2edd5331ad3
**Type:** decision
**Status:** pending-confirmation
**Evidence:** confirmed
**Source:** first live run on the platform, 2026-10-12; coordinator decision the same evening, maintainer's confirmation outstanding
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
