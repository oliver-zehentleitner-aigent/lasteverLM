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
