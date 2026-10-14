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
**See:** outputs.md#outputs-belong-to-the-user-and-live-in-the-library-rag-owns-their-generated-rows — d9bf964d-ec53-4cd7-8bd1-adfc9a5772f2 — as of 2026-10-14

When generation succeeds, the service writes a `sources` row of kind
`generated` in the same notebook (name = the output's title, summary =
the start of its text), chunks the document with the same 800/100 token
windows ingest uses, embeds the chunks and inserts them. `outputs.source_id`
holds that source (since 2026-10-14 its library row, which follows the
output into the trash and is purged with it) and `scope.output_id` on
`/ask` can restrict retrieval to it. The column is this service's
addition to the family's data model.

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
**Source:** family coordination, 2026-10-13; platform probe, 2026-10-13; `GET /v1/models`, 2026-10-14 (`max_prompt_length` 6000 characters)
**Revisit when:** the platform lowers its input limit below the segment size, or offers long-form speech
**See:** https://github.com/oliver-zehentleitner/lasteverLM — b57ab97c-0eee-43b3-a7ee-06226e2d9714 — as of 2026-10-14

The audio generator only writes the script (title plus spoken text,
three to five minutes). The output service cuts the script into
segments of at most 1500 characters, ending at a sentence end where
possible, synthesizes each with `TTS_MODEL` and its speaker's voice (since the audio styles, 2026-10-14), writes one
`tts` usage row per segment (the seconds of speech the platform
billed, as `tokens_in`), and
stores the segments' bytes joined as one MP3 at
`<notebook_id>/<output_id>/audio.mp3`. The row keeps `{"key"}`; reads
return a presigned URL. The script is also the output's index text.

**Reason:** the probe against the platform (`qwen3-tts-12hz-1.7b`)
returned MP3, 24 kHz mono at 64 kbps, at about ten seconds of synthesis
per thousand characters, and documents no input limit. Segments keep
each request short and bounded, and a failure costs one segment, not
the script. The model catalog later named an input limit of 6000
characters (2026-10-14); 1500-character segments stay well inside it,
and the reasons above hold without it. MP3 is a stream of self-contained frames, so the segments
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

## A generator's passages are balanced across sources, not a global top-k

**Id:** cfe78834-7ea7-49b4-9491-9720f4703a40
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer's screenshot and coordinator's analysis, 2026-10-13; live mind-map run, 2026-10-13
**Revisit when:** notebooks routinely hold more than a dozen sources (the 24-passage cap then leaves one chunk per source), or a reranker replaces plain cosine ranking

The focus-query passages a generator sees are chosen per source first:
every ready upload contributes its two best chunks regardless of the
similarity floor, then the remaining budget (at least `RETRIEVAL_K`, two
per source, capped at 24 passages; above the cap one chunk per source,
round robin) is filled from the global ranking. The system rules require
every listed source to be covered, and the mind map's root must span
all sources with a branch per source on distinct topics. After
generation, a source whose distinctive file-name words never appear in
the document is logged as a warning with the output id.

**Reason:** a mind map of a notebook with a vi PDF and a VNC PDF came
out entirely about VNC: the global top-k for "main topics" was filled by
VNC chunks, the prompt asked for one root theme, and the model took the
dominant source. The summaries alone did not prevent it. With the vi
chunks guaranteed in the input and the coverage rule in the prompt, a
live run with the same two sources gave a root "Linux Tools: vi and
VNC" with one branch per source. The warning is deliberately light: a
heuristic over file names cannot decide coverage reliably enough to
fail or retry a generation, but it makes a gap visible in the log.

**Rejected alternatives:** the global top-k for the focus query (the
behaviour this incident showed); one generation per source merged
afterwards, rejected as several model calls per output and a merge step
that loses the cross-source structure; failing or retrying an output
that misses a source, rejected because the name-word check gives false
positives and a retry would charge the user again for the same input.

## A shared output is a capability URL; the token in the path reaches access logs

**Id:** d1dbeb71-399f-46c7-a4e7-980ef38c8836
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** share implementation, 2026-10-12; infrastructure security audit, 2026-10-14
**Revisit when:** access logs are kept longer or shipped to a third party, or a shared output may hold content that must not outlive a revocation in a log

Sharing an output creates a token (`secrets.token_urlsafe(24)`, 192
bits); anyone holding `/s/<token>` (web) or `/api/rag/shared/<token>`
(API) can read that one output, read only, without an account. The
token is part of the URL path, so it is written to the ingress access
log for every view. Query arguments are no longer logged (infra), but a
path is. This is a known property, kept without a change.

**Reason:** a capability URL is the sharing design: the link is the
permission, so it can be pasted anywhere and opened without a login.
What limits a token found in a log: it opens one output only, read
only, and shows no ids of the owner; `DELETE /outputs/{id}/share`
revokes it at once (the lookup then answers 404); 192 bits cannot be
guessed; the access logs are rotated, so a token does not stay there.

**Rejected alternatives:** unknown; no other transport for the token
(a header, a URL fragment read by the page) was weighed when sharing
was built.


## Deleting a user removes the output files before the rows

**Id:** e7a0ae3d-6e45-4f3d-b3fd-d369682df8a0
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request "delete a user in the admin panel", relayed by the coordinator with the order, 2026-10-14; account's call contract the same day
**Revisit when:** outputs store files somewhere other than `content.key`, or ingest's notebook delete starts removing rag's objects itself

`DELETE /api/rag/admin/users/{id}` deletes the stored files of the
user's outputs first and rag's rows afterwards, in one transaction: the
user's outputs and generated rows by owner (since outputs outlive their
notebook, 2026-10-14) and the messages and conversations of the user's
notebooks. Nothing else deletes the files, and nothing would point at
them once the rows are gone. So a failed file delete stops the request with the key
(502) and keeps every row, and account's retry finds the same keys
again. Missing keys are no error, which makes the retry safe.

**Rejected alternatives:** leaving everything to ingest's cascade
(orphaned every audio file, and outputs no longer cascade); rows first, then files (a failure in between
leaves files no row names).

**Known gap:** a worker that finishes an audio output while the user is
being deleted can store its file after the delete; that file is
orphaned. Not handled in this change; reported to the coordinator.

## Outputs belong to the user and live in the library; rag owns their generated rows

**Id:** d9bf964d-ec53-4cd7-8bd1-adfc9a5772f2
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the coordinator, 2026-10-14 (outputs in the library's "Outputs" tab, surviving the notebook, usable as a source elsewhere); contract settled with ingest and web the same day
**Revisit when:** the library needs an output linked into several notebooks to survive the trash with those links, or ingest takes over the lifecycle of generated rows

An output has an `owner`; `notebook_id` is only its origin and turns
null when ingest deletes that notebook (`on delete set null`), with
`origin_title` as a snapshot of the notebook's title. Its generated
source is a library row the user owns; ingest lists such rows in its
picker and links them into other notebooks, reusing the chunks.
`outputs.source_id` points at that library row rather than at its link,
because the link goes with the notebook and the row stays. Deleting an
output moves it to the trash: `deleted_at` on the output and on its
row, every link of the row removed, as ingest's library trash does.
Restore relinks only the origin notebook. Rag purges after the owner's
`trash_days`: the stored file first, then the library row (chunks and
links cascade), then the output. Ingest's trash, restore and purge keep
excluding kind `generated`.

**Reason:** the maintainer wants outputs to outlive their notebook and
to be reusable as sources. One service owning the whole lifecycle of an
output and its row keeps "files before rows" in one place, which a
purge split between two services could not guarantee. Migration 0004
is expand only: `owner` stays nullable and reads fall back to the
notebook's owner, so pods of the previous release can still insert
during the rolling deploy.

**Rejected alternatives:**
- Outputs as full library sources with many links, each surviving the
  trash: not needed by the maintainer.
- Ingest's purge sweeping the generated rows while rag deletes the audio
  file: rejected in favour of one owner. Ingest agreed.
- Keeping the notebook cascade (the previous behaviour): it deletes what
  the maintainer wants to keep.

## Audio has three styles; a conversation uses two voices

**Id:** ab14b49e-b37d-421b-b9c0-231abe1a1ed2
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer wish relayed by the coordinator, 2026-10-14 (the three styles, two hosts, one voice per speaker); `GET /v1/models` on 2026-10-14 for the speech model's parameters
**Revisit when:** the platform documents its `instructions` parameter for prosody, or listeners cannot tell the two voices apart

`audio_style` is `overview` (default, the earlier behaviour), `story`
(the material as a narrative, one narrator, nothing invented) or
`conversation` (an interviewer asking, an expert answering only from
the material), each with its own prompt and JSON schema. A conversation
is a list of turns, and each turn is read with its speaker's voice:
`voice` for the interviewer, `audio_voice_2` for the expert. The second
voice defaults to the next one with the same native language as the
first, so both read the material's language equally well (`ryan` →
`aiden`), and to `ryan` when the first voice has no partner. The
"citation discipline" of the written kinds becomes the grounding rules
in the prompt and, since provenance (2026-10-14), passage numbers in a
`refs` list beside each paragraph or turn, never `[n]` markers in the
text, which a voice would read aloud.

**Reason:** the maintainer asked for the set and for two voices; the
reasons below for two voices are this service's. A change of voice is
audible on its own, while the same voice with different prosody leaves
the listener to guess who is speaking. The platform documents its
speakers, and its `instructions` parameter, the only prosody control,
is listed without a type and was never probed. Switching voices per
turn costs nothing extra, because speech is billed per second.

**Rejected alternative:** one voice with different prosody per speaker
(see above); unknown whether anything else was weighed.

## A decision's number comes from the decision model, its evidence from the LLM independently, and their agreement is shown

**Id:** e384d814-56f5-4990-b4af-e9da3e8b8a18
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer go relayed by the coordinator, 2026-10-14 (the split, the independence and the rejected alternatives); the coordinator's approval the same day for the LLM's own pick in a choice or a scale and for keeping a replaced verdict in the log
**Revisit when:** agreement turns out "conflicting" or "unclear" for most decisions, the decision model's answers prove uncalibrated, or the platform's decision model changes its question types
**See:** https://github.com/oliver-zehentleitner/lasteverLM — cf7810ca-d96e-47b8-aeb3-5619cbb5a642 — as of 2026-10-14

A decision output asks the platform's decision model for the number (the
probability of yes, or a choice or a level with its distribution and
confidence) and, separately, the LLM for a verdict, evidence for and
against with cited passages, and gaps. Both get the same numbered
passages; the LLM never sees the model's answer. For a choice or a
scale, the LLM names its own pick (`llm_choice`), because evidence "for
the selected option" needs to know the selection. `agreement` compares
the number with the balance of supported evidence and is always shown,
a conflict included. Without supported evidence on either side the
verdict is the fixed "The sources do not decide this.", and the LLM's
own sentence is kept in the provenance log.

**Reason:** the coordinator's brief gave the split and the rejected
alternatives without reasons; the reasons here are rag's and therefore
inferred. An LLM alone gives no calibrated number; the decision model
alone gives a number with nothing a reader can check; an LLM shown the
number first would argue towards it, so agreement between the two would
prove nothing. Independent calls make agreement informative and a
conflict visible.

**Rejected alternatives:**
- An LLM-only verdict.
- A decision-model-only number.
- The LLM seeing the model's number before writing the evidence.
- Evidence for the model's selected option in a choice or scale: it
  breaks the independence.

## A report's style and length and a quiz's count, difficulty and audience are prompt variants with stored defaults

**Id:** 0ed4636e-c552-4bf8-963e-6925f6ccab29
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer request relayed by the coordinator, 2026-10-14 (the option sets and their defaults); the prompts, budgets and the count rule are rag's
**Revisit when:** quizzes of the larger counts fail on the count for small notebooks, or a long report hits the provider's output limit

A report takes `report_style` (briefing, detailed, executive_summary,
explainer, academic) and `length` (short, medium, long). A quiz takes
`question_count` (5–30), `difficulty` and `audience`. Each value is a
sentence in the generator's task, and the length is also a word target.
The answer's token budget follows the size: 8000 for a long report, 250
per question for a quiz (at least 4000). The defaults (briefing, medium;
10, medium, adults) are stored on the output like audio's. A quiz must
have the asked number of questions: fewer is a schema miss with the
corrective retry, and more are cut to the first ones. The log's prompt
version names the report style (`report-explainer-v3`).

**Reason:** these options change what the model is asked for, never the
pipeline. A variant of the same prompt keeps retrieval, the citation
rule and the check identical for every value. The defaults go on the row
for the reason in bd95d88e-3eb9-4ce9-ac07-510c6d9ce95f: the viewer shows
what an output was made with. A fixed 4000-token budget would cut off a
long report or a 30-question quiz mid-JSON, which is a failure the user
pays for. The count is the user's explicit choice, so silently
delivering seven of ten questions would hide that the request was not
met (fail loud). One retry fixes a model that miscounted.

**Rejected alternatives:**
- Accepting fewer questions than asked: it hides the miss.
- One fixed budget for every option: it cuts off long documents.

Further alternatives: unknown. The coordinator's brief named the option
sets but none that were turned down.

## A shared notebook shows its uploads by name and its ready outputs as their shared view

**Id:** 85dbc62d-1ee0-46eb-b0e4-fe7a6226a836
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer request relayed by the coordinator, 2026-10-14 (the endpoint, sources as names and kinds, outputs as SharedOutput without ids); ingest's token and its source rule, 2026-10-14; leaving out generated sources and unready outputs is rag's
**Revisit when:** a shared notebook should also show its chat, or outputs need to be shared from it one by one
**See:** https://github.com/oliver-zehentleitner/lasteverLM — 9eda5c9c-7673-4343-814b-0d42feea51e1 — as of 2026-10-14

`GET /api/rag/shared/notebooks/{token}` reads ingest's
`notebooks.share_token`. It returns the title, the ready uploads by name
and kind, and every ready output outside the trash. Each output goes
through the same function as a single shared output, so it never shows
more than one shared alone would. Generated sources are not listed among
the sources, since they are the outputs below. A waiting, processing or
failed output is not listed either.

**Reason:** one code path for "an output a stranger sees" keeps the
stripping of ids and the source selection in one place. A second shape
would be a second place for a leak. A generated source listed as a
source would show the same document twice under two names. An unready
output has nothing to read, and a failed one would show an internal
error to a stranger.

**Rejected alternatives:** unknown. The brief fixed the shape, and no
other was weighed.

## A chart is made in two steps, from candidates the client sends back and rag checks again

**Id:** 3c4b2d51-b170-4029-8e0b-ccfa72dc1776
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer design relayed by the coordinator, 2026-10-14 (two steps and their reason); the coordinator's approval the same day of stateless re-validation over a cache
**Revisit when:** proposals need to be reused across sessions or devices, or clients start editing candidates before creating

`POST /notebooks/{id}/charts/propose` returns candidate charts from one
LLM call and stores nothing. The user picks some, and `POST .../outputs`
with `{"kind": "chart", "options": {"charts": [...]}}` creates the output
from the picked objects, without a second extraction. Each candidate
carries the chunk ids of its passages. At creation every chunk must
belong to the notebook (else 422). The worker loads them again, numbers
them once for all picked charts, and checks every value anew; any
`support` the client sends is ignored.

**Reason:** the user decides what is drawn, and nothing is drawn that the
sources do not hold. Proposing first lets a person pick from what the
material really contains, with each value's support visible before
anything is made. Creating from the returned objects keeps both steps
stateless. The api pods and the worker share no memory, and a cache
would need its own table and expiry. The check reads the notebook's own
chunks, never the client's copy, so a changed value is simply marked
unsupported.

**Rejected alternatives:**
- One step that draws every series it finds: the user gets charts they
  did not choose.
- Caching the proposal for 30 minutes under its ids: server state and an
  expiry for no gain over re-validation.
