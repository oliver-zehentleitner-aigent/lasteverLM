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
for the table; a decision's is the user's question, and a chart makes no
retrieval, it is drawn from the candidates picked for it). Sources of
kind `generated` are left out of both: their summaries are not fed back
in, and the retrieval leaves their chunks out explicitly. That holds
also for an output linked into another notebook from the library: it
counts as generated there too. Since 0.10.0 the input is limited to the
user's selected sources (fb02e210-b924-46d1-85d1-861b9f8ae11d in
`retrieval.md`).

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

When generation succeeds, the service writes a library row of kind
`generated` and links it into the same notebook (name = the output's
title, summary = the start of its text), chunks the document with the
same token windows ingest uses (core's chunker, 420/50 since core moved
them), embeds the chunks and inserts them. `outputs.source_id`
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
`<notebook_id>/<output_id>/audio.mp3`. The row keeps `{"key",
"transcript"}` (each entry with its `start` and `end` since
15b84a46-7085-4197-aaf1-3b68c01ae66b); reads return a presigned URL. The
script is also the output's index text. Since that entry each turn is
synthesized on its own, so a segment never spans two turns.

**Reason:** the probe against the platform (`qwen3-tts-12hz-1.7b`)
returned MP3, 24 kHz mono at 64 kbps, at about ten seconds of synthesis
per thousand characters, and documents no input limit. Segments keep
each request short and bounded, and a failure costs one segment, not
the script. The model catalog later named an input limit of 6000
characters (2026-10-14); 1500-character segments stay well inside it,
and the reasons above hold without it. MP3 is a stream of self-contained frames, so the segments
concatenate without re-encoding and without an audio library in the
image. Each segment's first frame is a Xing header for that segment
alone, though: the joined file keeps one, rewritten for the whole
stream, and drops the others (corrected 2026-10-15; until then a player
read the first segment's length as the file's and could not seek past
it). Cutting at sentence ends keeps the joins at natural pauses.

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
**Revisit when:** the platform changes its voices or speech limits, or an output option should default from a user preference

**Re-checked 2026-10-15:** the earlier condition (rag needing a user
preference it cannot get from the request) fired: rag reads two of
account's per-user preferences from the shared database, `judge_default`
for the agent's judge question and `trash_days` for the purge. Neither
is an output option; output options still come explicitly from the
client and are stored on the output. The decision holds.

`POST .../outputs` takes `options`: `language` for every kind but the
chart, `voice`
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
80 characters, the seconds spoken), charged as a `voice_sample` action
under the pricing rules; every later request for the same combination,
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
**Source:** a screenshot of a mind map that left out a source, and its analysis, 2026-10-13; live mind-map run, 2026-10-13
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

**Reason:** a mind map of a notebook with two PDFs on different tools
came out entirely about one of them: the global top-k for "main topics"
was filled by that PDF's chunks, the prompt asked for one root theme,
and the model took the dominant source. The summaries alone did not
prevent it. With the other PDF's chunks guaranteed in the input and the
coverage rule in the prompt, a live run with the same two sources gave
a root naming both tools, with one branch per source. The warning is deliberately light: a
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
**Source:** maintainer request to delete a user from the admin panel, relayed by the coordinator with the order, 2026-10-14; account's call contract the same day
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
orphaned. Since the library change the worker settles a job whose row
is gone (it deletes the file and the generated source), which narrows
the window; one remains when the worker writes the row as ready between
the delete's reading of the files and its deleting of the rows
(inferred from the code, not tested).

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
  file: rejected in favour of one owner of the generated rows.
- Keeping the notebook cascade (the previous behaviour): it deletes what
  the maintainer wants to keep.

## Audio has four styles; a conversation and an FAQ use two voices

**Id:** ab14b49e-b37d-421b-b9c0-231abe1a1ed2
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer wish relayed by the coordinator, 2026-10-14 (the three styles, two hosts, one voice per speaker); maintainer order relayed by the coordinator, 2026-10-14 (the fourth style, faq, with two voices); `GET /v1/models` on 2026-10-14 for the speech model's parameters
**Revisit when:** the platform documents its `instructions` parameter for prosody, or listeners cannot tell the two voices apart

`audio_style` is `overview` (default, the earlier behaviour), `story`
(the material as a narrative, one narrator, nothing invented),
`conversation` (an interviewer asking, an expert answering only from
the material) or `faq`, each with its own prompt and JSON schema. An FAQ
has 5 to 8 questions a listener would most likely ask about the material,
each answered from it. The interviewer asks and the expert answers, in
strict turn, and the questions carry no claim. A conversation
(or an FAQ) is a list of turns, and each turn is read with its speaker's voice:
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

**Rejected alternatives:**
- One voice with different prosody per speaker (see above).
- For the FAQ, one narrator reading "Question …, answer …": less clear to
  listen to than a change of voice between question and answer.

Unknown whether anything else was weighed.

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

**Reason:** the split and the rejected alternatives were set without
reasons; the reasons here are rag's and therefore inferred. An LLM alone gives no calibrated number; the decision model
alone gives a number with nothing a reader can check; an LLM shown the
number first would argue towards it, so agreement between the two would
prove nothing. Independent calls make agreement informative and a
conflict visible.

**Rejected alternatives:**
- An LLM-only verdict.
- A decision-model-only number.
- The LLM seeing the model's number before writing the evidence.

**Since 2026-10-15:** an undecided decision carries no number; see
8471f5a5-786d-4079-b5b1-a29cf2ab172e.
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

Further alternatives: unknown; none turned down is recorded.

**Since 2026-10-15:** a report's length is an upper bound, no longer a
word target, and the prompt version is `report-<style>-v4`; see 47ce2c17-0831-48ad-86c5-171b09cc9a74.

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

**Rejected alternatives:** unknown. The shape was set with the request,
and no other was weighed.

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
belong to an uploaded source of the notebook and, with a selection, to a
selected source (else 409 `chart_out_of_scope`); finding charts reads
and searches only the selected sources (corrected 2026-10-15: before,
it proposed from the whole notebook and a candidate from an earlier
selection was drawn). The worker loads them again, numbers them once for
all picked charts, and checks every value anew; any `support` the client
sends is ignored.

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

## A starter notebook's outputs are copied by rag's worker from a queue row ingest writes

**Id:** 10b15d37-d52b-46a7-b4ce-36460711e118
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer go relayed by the coordinator, 2026-10-14 (copy the outputs, remap ids, drop the unmappable, no share tokens, keep judge annotations, no charge, idempotent; the handover left to rag and ingest); agreed with ingest the same day
**Revisit when:** the starter grows large enough that copying in the worker delays a new user noticeably, or a copied output needs anything the queue row does not carry

Ingest copies the starter's uploads for a new user and, in the same
transaction, inserts an `output_copies` row with its id maps. rag's
worker claims the row (before output jobs, with attempts like them),
copies the ready outputs and deletes the row. `outputs.copied_from` with
a unique (notebook, copied_from) makes every copy happen once.

**Reason:** the row makes the handover atomic with ingest's copy, which
either commits both or neither, without ingest running rag's SQL or
importing rag's code. It also needs no new service-to-service auth,
which an HTTP call would. The audio files cannot be copied inside a
database transaction anyway. A queue the worker retries handles a storage
failure without rolling back the user's notebook. The outputs appear a
few seconds after the notebook, which a new user does not notice.

**Rejected alternatives:**
- A shared function in ingest's transaction: cross-service code, and a
  failed file copy would undo the user's notebook.
- An internal HTTP call from ingest: new auth between services, and not
  atomic with ingest's copy.

## A running job beats its claim; an output waiting for its sources fails after 30 minutes

**Id:** 33fc1c1f-8444-4f70-b597-b459ce000c78
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** a judged report that started on 0.19.4 at 17:22 CEST, kept "processing" and failed after the 0.19.5 rollout, reported by the maintainer and relayed by the coordinator, 2026-10-14; the coordinator's go the same day for the heartbeat, the waiting limit, refusing failed sources and the final error text; the pod logs of that run were gone with the rollout, so the run itself is inferred from the code
**Revisit when:** jobs routinely run longer than the stale-claim limit even with the heartbeat (a worker blocked in one call longer than 10 minutes), or sources routinely take longer than 30 minutes to read

A worker refreshes the claim of the job it runs (`claimed_at`) at most
once a minute, before every model call, judge call and speech segment.
Another worker takes over a job only after 10 minutes without a beat,
which means its worker died. An output that has waited 30 minutes for
its sources to be read fails, naming the source, uncharged and kept. A
selected source that could not be read is refused at creation, or fails
the output before its first model call, never skipped.

**Reason:** the stale-claim limit had two jobs: notice a dead worker, and
nothing else. With a judge at its high level, a report makes dozens of
calls of up to a minute each and outran the 10 minutes. A second worker
then took over a job that was still running. Both runs booked their
calls under the output's action, so the user paid twice. The fee is not
doubled, since it is once per action_id. A beat separates "slow" from
"dead" whatever the job's length, so the limit can stay short and a dead
worker's job is still picked up within minutes. The waiting limit
applies the same fail-loud rule to a source that never finishes: the
output stops with its reason, as an agent plan's output already did.

**Rejected alternatives:**
- A longer stale-claim limit: any fixed limit is outrun by some job, and
  a long one leaves a dead worker's job stuck for that long.
- Waiting for sources without a limit: a page that never reads holds the
  output in "waiting" forever.
- Skipping a failed source and generating from the rest: the output
  claims to cover a selection it did not read.

## A running output shows the step it is really in, written with the heartbeat

**Id:** 8eddb2f9-7744-4994-8982-187bd80b9246
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (a line under the generating view showing what really happens; a fake percentage and elapsed time alone rejected); the step names and writing them with the heartbeat are rag's
**Revisit when:** a step routinely takes so long that its line looks frozen (a counter would help), or the update rate of phases shows up in the database's load

While an output runs, `outputs.phase` holds the step the worker has
really begun, with the time it began and a counter where the step has
one (judge round n of 3, speech segment n of m, the next attempt n of
3). A waiting output's phase, the sources still being read, is computed
on read, because no worker runs it. The phase is written in the same
update as the claim's heartbeat. A new step is written at once; a
counter of the same step at most every 5 seconds. It is cleared when the
output is ready or failed.

**Reason:** a user watching "Generating…" for minutes cannot tell a slow
step from a stuck job. Naming the real step, such as "judging, round 2
of 3", makes the wait legible and makes a stuck job visible as a step
that does not move. Writing it with the heartbeat keeps it honest,
since a step is only shown once the code has entered it, and it costs
no extra updates beyond the step changes. Steps without a natural
counter get none, so nothing suggests a precision the worker does not
have.

**Rejected alternatives:**
- A progress percentage: the duration of each step depends on the
  material and the models, so any percentage would be invented.
- Only the elapsed time: it says that something takes long, not what.

## An audio's transcript times are measured from its MP3 frames, each turn spoken on its own

**Id:** 15b84a46-7085-4197-aaf1-3b68c01ae66b
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (highlight the text being read; measured duration preferred over provider seconds if cheap); a platform probe the same day (the same sentence at speed 1.0 gave 5.7 s of audio billed as 6 s, at speed 1.5 4.0 s billed as 7 s; mutagen agrees with the frame count within the encoder delay); choosing per-turn synthesis is rag's
**Revisit when:** the platform returns timestamps or word timings itself, or a format other than MP3

Each transcript entry gets `start` and `end`, its seconds in the final
file. They are the sum of its segments' durations, measured by walking
the MP3 frame headers (`mp3.py`, no decoder). A segment never spans
two turns, so every turn is synthesized on its own. Before, consecutive
turns of one voice were joined into one stretch. If a segment cannot be
measured, the audio stays as it is without times, and a warning is
logged.

**Reason:** the billed seconds are not the audio's length. They are
whole seconds, and at another speed they are not even close: in the
probe, 4.0 s of audio at speed 1.5 was billed as 7 s. Highlighting off
by seconds would be worse than none. Counting frames is exact for the
joined stream: each segment's silent encoder-delay frames are played
too, which a tool that reads one file on its own leaves out. It costs
one pass over bytes rag already holds. Joined stretches would hide where
one paragraph ends and the next begins. Synthesizing per turn makes the
boundaries real, at the price of more requests, each billed in whole
seconds.

**Rejected alternatives:**
- The provider's billed seconds: whole seconds, and wrong at other speeds.
- Estimating from the number of characters: invented, and wrong for
  every voice and speed.
- Keeping the joined stretches and splitting their time by characters:
  the boundaries inside a stretch would be guesses.
- A decoding library: a dependency for what the frame headers already say.

## A report's length is an upper bound, never a target, so short material is not filled with invention

**Id:** 47ce2c17-0831-48ad-86c5-171b09cc9a74
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (from a live report that added roles, approvals and processes its sources did not contain; the bound, the shorter length for thin material and the ban on added facts as the prompt now states them; rejected: fixed targets)
**Revisit when:** reports from rich material come out far shorter than their length asks, so that the bound is read as "write little"

A report's `length` sets the most words: 500 for short, 1200 for medium,
2500 for long. The prompt says "at most N words; shorter when the
material says less" and forbids adding facts, roles, steps or reasons
the material does not state, even to reach the length. The token budgets
are unchanged. The prompt version is `report-<style>-v4`.

**Reason:** a target such as "about 700 to 1200 words" asks the model to
reach a size whatever the material holds. With a few short sources the
only way to reach it is to invent: the model added roles, approvals and
processes that no source contained, each a plausible claim the reader
cannot tell from the cited ones. An upper bound keeps a long report
possible when the material supports it and lets a thin notebook give a
short one, which is the honest size.

**Rejected alternatives:**
- Fixed word targets per length: fill short material with invention.

## An output keeps every failed attempt on its row, and support finds it by its short id

**Id:** 3b920d95-1ecd-4d77-b292-bfc2a238edeb
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (store failed attempts in the database with core's attempt record, an admin search by id prefix, short ids in log lines; rejected: relying on pod logs); core's `AttemptRecord` and `short_id` the same day
**Revisit when:** an output can take far more than three attempts, so that its list grows without bound, or attempts need to be queried across outputs (a failure-rate report), which a list on the row makes awkward

Every failed attempt of an output is appended to `outputs.attempt_log` as
core's `AttemptRecord`: when, which attempt, the model in flight, the
kind of failure, the provider's HTTP status and core's own message,
never a prompt or source text. `outputs.finished_at` records when the
output became ready or failed. The owner sees the list on the output;
viewers and admins find outputs by the first six or more hex digits of
the id (`GET /api/rag/admin/outputs`), with the owner masked for
viewers. Log lines name an output by its short id, the same prefix.

**Reason:** twice an output failed and the pod logs of its run were gone
with the next rollout (33fc1c1f-8444-4f70-b597-b459ce000c78 and
755ed7ef-5d49-4d14-aec5-8cb96ec9f546 had to read the cause from the code).
A record on the row survives every deploy, is deleted with the output,
and needs no log access. A list on the row rather than a table: an output
has at most three attempts, they are always read with the output, and a
jsonb append needs no join or second lifecycle. The short id lets a user
or a log line hand support something to search for.

**Rejected alternatives:**
- Relying on pod logs: they vanish with every rollout.
- A separate attempts table: a join and its own cleanup for at most three
  rows that are only ever read with their output.

## An undecided decision carries no number

**Id:** 8471f5a5-786d-4079-b5b1-a29cf2ab172e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer report relayed by the coordinator, 2026-10-15 (a decision showed "77 % Yes" while its agreement said the sources do not decide it and no evidence was supported; a number without evidence is the model's prior, against "everything checkable")
**Revisit when:** the decision model can say itself that the material does not decide the question, or decisions with a single supported item turn out to need the same treatment

When no evidence item on either side is supported by its passages
(agreement `undecided`), the decision's content has no number:
`model_answer` is `null` and the verdict is "The sources do not decide
this.". The decision model's number and the LLM's own sentence go into
the generation log (`model_answer_without_evidence`,
`llm_verdict_text`), marked as not from the sources. The evidence, its
support and the gaps stay.

An item counts as supported by its judge's verdict when it was judged,
by the word check otherwise; a disputed item is not supported and is
named in the agreement note (corrected 2026-10-15: the count had used
the word check only, so a German decision over an English source showed
"no decision" although both judges supported its evidence).

**Reason:** the decision model answers every question, also one the
passages say nothing about; then its number is its prior, not a
decision from the sources. Shown next to "the sources do not decide
this", a reader still takes the number as the answer, and nothing in the
output lets them check it. Withholding it keeps every number in an
output backed by evidence a reader can follow; keeping it in the log
keeps it inspectable.

**Rejected alternatives:**
- Showing the number with a warning: a reader takes a number as an
  answer, whatever the note beside it says.

## A decision's number that little evidence stands behind is shown as a tendency, never hidden

**Id:** 33354271-3f3a-41ca-9352-b1c313a92dba
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** rag's proposal after the undecided fix, approved by the coordinator for the maintainer, 2026-10-15 (conflicting stays visible with its number; one supported item or an unclear balance shows the number as a tendency; nothing hidden)
**Revisit when:** users read a tendency as a firm answer anyway, or a threshold of two supported items turns out too low for the decisions people ask

A decided number carries `weight`: `tendency` when one supported
evidence item or an unclear balance stands behind it, `full` otherwise,
a conflict included. `supported_evidence` gives the count. The web
shows a tendency lighter, with the count; nothing is hidden.

**Reason:** one supported item is still evidence a reader can check, so
hiding the number would take away a result that can be followed.
Showing it as firmly as a number many items back would overstate it.
A conflict stays as it is, because there the reader needs both sides at
full strength to see that they disagree.

**Rejected alternatives:**
- Hiding the number below two supported items: removes a checkable
  result.
- Lightening a conflict too: it would hide the disagreement the agreement
  field exists to show.
