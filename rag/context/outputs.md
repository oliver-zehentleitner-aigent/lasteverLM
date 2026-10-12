# Outputs

## Generator input is the source summaries plus focus-query chunks; generated sources are excluded

**Id:** de9869b4-2e6c-4662-a2bd-fcf3b18dd0d0
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12; implementation session, 2026-10-12
**Revisit when:** a notebook's summaries alone no longer fit the model's context, or outputs should build on each other

Every generator receives the summaries ingest wrote for the notebook's
ready sources, plus the top-k chunks retrieved for the generator's own
focus query (a fixed phrase per kind, e.g. "figures, dates, comparisons"
for the table). Sources of kind `generated` are left out of both: their
summaries are not fed back in and the focus-query retrieval is unscoped
but their chunks only exist after a previous output.

**Reason:** summaries keep large notebooks inside the context window
(family rule); the focus query adds the concrete passages the kind needs
beyond a summary. Excluding generated sources from a generator's input
keeps every document derived from the user's own material: a report
generated from a quiz generated from a report would compound the model's
paraphrases with no new ground truth.

**Rejected alternative:** feed all chunks of the notebook. Rejected
because it does not scale past a few sources and spends tokens on
passages the kind does not need.

## A ready output is indexed as a source of kind generated; outputs carry the source id

**Id:** 9aaa23c6-c59e-4c9d-9467-9bdd5fd9e7af
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12; implementation session, 2026-10-12
**Revisit when:** the schema gains a generic link table or ingest takes over indexing

When generation succeeds, the service writes a `sources` row of kind
`generated` in the same notebook (name = the output's title, summary =
the start of its text), chunks the document with the same 800/100 token
windows ingest uses, embeds the chunks and inserts them. `outputs.source_id`
holds that source so deleting the output deletes the source (and its
chunks by cascade) and `scope.output_id` on `/ask` can restrict retrieval
to it. The column is this service's addition to the family's data model.

**Reason:** indexing the document as an ordinary source lets the chat
answer about and cite generated documents with the same retrieval and
citation path as uploads; nothing special-cases them except the
`source_kind` label the frontend renders. A stored link beats finding
the source by name or a convention in `storage_path`, which would break
on the first renamed title.

**Rejected alternative:** keep the generated text in `outputs.content`
only and search it separately. Rejected because it would need a second
retrieval path and citations of a second shape.

## The outputs table is the job queue; a worker entrypoint runs generation

**Id:** d267457e-de59-49d3-90fd-0e6bf81dbaf3
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12; implementation session, 2026-10-12
**Revisit when:** job volume or latency asks for a broker, or a second service needs a queue

The API inserts an `outputs` row (`waiting` while a source is still
processing, else `processing`) and answers 202. A separate entrypoint of
the same package, `lasteverlm-rag-worker`, claims one unclaimed row at a
time with `SELECT ... FOR UPDATE SKIP LOCKED`, stamping `claimed_at` and
`claimed_by` and counting the attempt. A `waiting` row is claimable only
once no uploaded source of its notebook is still processing; the claim
query checks that, so a worker never holds a job it cannot run. A claim
older than ten minutes is taken over, which is how a job survives a
worker that died mid-run. A transient failure (provider, database)
gives the job back with its error; the third attempt fails it. A
`GenerationFailed` (no ready source, a model that cannot follow the
schema after one correction round, a kind that is not available) fails
the job at once, because a retry would spend the user's credit on the
same outcome. A half-indexed generated source is deleted on failure.

**Reason:** the family rule is horizontal scaling with stateless API
pods: workers scale independently and a restart of either side loses no
job. Postgres already holds the rows and gives the claim semantics for
free, so no broker is needed for this volume. The claim, the stale
limit and the attempt cap are the family's shape (ingest's worker uses
the same); splitting final from transient failures on top of it is this
service's choice, since its failures are mostly model behaviour that no
retry changes. One JSON correction round turns the most common model
failure (stray prose, a missing field) into a success for one extra
call.

**Rejected alternatives:** an in-process background task after the 202
(the first draft), rejected because a pod restart lost the job and
generation load could not scale separately from request load; a message
broker, rejected as a second stateful component for a queue of this size.

## Audio is registered and fails clearly instead of being hidden

**Id:** 471b245e-a056-4680-ac70-ad8818489be8
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12
**Revisit when:** the inference platform offers a speech endpoint

The `audio` kind is accepted by the API and the generator module exists,
but every audio output fails with "text-to-speech is not available on
this deployment" until `TTS_MODEL` is set and a speech endpoint exists.

**Reason:** the family wants the extension point visible (the tile is
shown in the wizard) and the module prepared; a kind that is accepted
and then produces nothing silently would be worse than one that fails
with a reason the frontend can show.
