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
**Status:** superseded
**Superseded by:** b8b85840-a958-42e9-90b4-a9205d5b6f40
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

## Audio is read in sentence-boundary segments whose MP3 frames are concatenated

**Id:** b8b85840-a958-42e9-90b4-a9205d5b6f40
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-13; platform probe, 2026-10-13
**Revisit when:** the platform documents an input limit or offers streaming or long-form speech

The audio generator only writes the script (title plus spoken text,
three to five minutes). The output service cuts the script into
segments of at most 1500 characters, ending at a sentence end where
possible, synthesizes each with `TTS_MODEL` and `TTS_VOICE`, writes one
`tts` usage row per segment (input characters as `tokens_in`), and
stores the segments' bytes joined as one MP3 at
`<notebook_id>/<output_id>/audio.mp3`. The row keeps `{"key"}`; reads
return a presigned URL. The script is also the output's index text.

**Reason:** the probe against the platform (`qwen3-tts-12hz-1.7b`)
returned MP3, 24 kHz mono at 64 kbps, at about ten seconds of synthesis
per thousand characters, and documents no input limit. Segments keep
each request short and bounded, and a failure costs one segment, not
the script. MP3 is a stream of self-contained frames, so the segments
concatenate without re-encoding and without an audio library in the
image. Cutting at sentence ends keeps the joins at natural pauses.

**Rejected alternatives:** one request for the whole script, rejected
because the input limit is unknown and a five-minute script would be
one fifty-second request with nothing to retry but all of it;
re-encoding the joined audio, rejected because it adds a codec
dependency for no audible gain.


## Output options are validated per kind, sent explicitly by the client, and stored on the output

**Id:** bd95d88e-3eb9-4ce9-ac07-510c6d9ce95f
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request, relayed by the coordinator, 2026-10-13; platform probe and the Qwen3-TTS model card, 2026-10-13
**Revisit when:** the platform changes its voices or speech limits, or rag needs a user preference it cannot get from the request

`POST .../outputs` takes `options`: `language` for every kind, `voice`
and `speed` for audio. They are checked against one catalogue
(`lasteverlm_rag/options.py`, served at `GET /api/rag/outputs/options`
with which options each kind takes), resolved with audio's defaults
(`TTS_VOICE`, speed 1.0), stored in `outputs.options` and returned on
the output and the shared view. A missing `language` keeps the old
behaviour: the document follows the language of its sources. The user's
preferred language lives in account; the web resolves it and sends it.

**Reason:** the viewer must show what an output was made with, and a
later default change must not rewrite history, so the resolved values
go on the row. The catalogue in one place lets the web render the
options without a release per voice. Voices, genders and the ten
languages are the speech model's own (model card); the speed range is
inside the 0.25–4 the endpoint accepted in the probe, and a speed of 0.5
or 2.0 did change the audio length, so the option is real. The
generator prompt names the language explicitly, title included: a live
run turned an English source into a German and a French report.

**Rejected alternatives:** rag reading the preference from account's API
with the user's token, rejected because it adds a call between services
that the family's design keeps apart and a failure path to every
generation; silently ignoring unknown or misplaced options, rejected
because a client bug would produce a document in the wrong language
without any sign; the full 0.25–4 speed range in the UI, rejected
because the extremes are not usable for listening.

## Voice previews are cached under a key derived from the request

**Id:** 84738122-4e67-4aa0-96ec-e45e56f41120
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request, relayed by the coordinator, 2026-10-13; live synthesis of the sample texts, 2026-10-13
**Revisit when:** the platform's voices change their sound (a new model version), or the sample texts change

A preview is a fixed sentence pair per language spoken by one voice at
one speed. It is stored at `samples/<voice>/<speed>/<language>.mp3`; a
request first checks whether that object exists and only synthesizes
when it does not. The first requester pays one `tts` usage row (45 to
80 characters, one cent); every later request for the same combination,
from any user, is served from storage without a model call or charge.

**Reason:** previews are the same bytes for everyone, so a key built
from the request alone makes the cache need no table, no lookup and no
invalidation logic: the object either exists or not. Users click
through voices repeatedly in Settings and in the options panel; without
the cache each click would be a paid model call and a one-to-two-second
wait. The existence check fails loud on storage errors instead of
treating them as "not cached", so a broken bucket cannot turn into
repeated paid syntheses.

**Rejected alternatives:** synthesizing on every request, rejected for
cost and latency; pre-generating all combinations at deploy time,
rejected because nine voices by four speeds by ten languages are 360
files nobody may ever play; shipping recorded samples in the image,
rejected because they would drift from what the configured model really
sounds like; a database table of generated samples, rejected as a
second record of what the object store already knows.
