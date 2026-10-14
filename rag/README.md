# rag

[![CI](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://img.shields.io/badge/Keep_the_Why-context%2F-2b6cb0)](https://keepthewhy.com)

The rag service of lasteverLM: retrieval over one notebook's chunks,
answers with citations mapped back to source and passage, the chat
conversations, and the generated documents (report, quiz, table, mind map,
infographic, audio). The API contract and the data model live
in the repository root, [`docs/architecture.md`](../docs/architecture.md);
this directory implements the `/api/rag` prefix.

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/rag/notebooks/{id}/ask` | `{"question", "conversation_id", "scope": {"output_id"}?, "source_ids"?}` | `Answer` |
| GET | `/api/rag/notebooks/{id}/conversations` | | `[Conversation]`, oldest first |
| POST | `/api/rag/notebooks/{id}/conversations` | `{"title"?}` | 201 `Conversation`; title defaults to `Chat N` |
| PATCH | `/api/rag/conversations/{id}` | `{"title"}` | `Conversation`; title trimmed, 1–80 chars, else 422 |
| DELETE | `/api/rag/conversations/{id}` | | 204, the conversation and its messages |
| GET | `/api/rag/conversations/{id}/messages` | | `[Message]`, oldest first |
| GET | `/api/rag/chunks/{chunk_id}` | | `ChunkView`: the verbatim chunk, its page, position and source |
| POST | `/api/rag/notebooks/{id}/outputs` | `{"kind", "options"?, "source_ids"?}` | 202 `Output`, status `waiting` or `processing` |
| GET | `/api/rag/outputs/options` | | the options catalogue, see below |
| POST | `/api/rag/outputs/voice-sample` | `{"voice", "speed"?, "language"?}` | `{"url", "cached"}`: a short MP3 preview of a voice |
| GET | `/api/rag/notebooks/{id}/outputs` | | `[Output]` made in that notebook, not in the trash |
| DELETE | `/api/rag/notebooks/{id}/outputs` | | 204, every output made in that notebook into the trash |
| GET | `/api/rag/library/outputs?kind=&trash=` | `kind` optional, `trash` default false | `[Output]`, the caller's outputs from every notebook, newest first; with `trash=true` the trashed ones |
| GET | `/api/rag/outputs/{id}` | | `Output`; 404 when trashed |
| DELETE | `/api/rag/outputs/{id}` | | 204, into the trash |
| POST | `/api/rag/outputs/{id}/restore` | | 204, out of the trash |
| DELETE | `/api/rag/outputs/{id}/purge` | | 204, deleted for good; 409 unless in the trash |
| POST | `/api/rag/outputs/{id}/share` | | `{"share_token"}` |
| DELETE | `/api/rag/outputs/{id}/share` | | 204 |
| GET | `/api/rag/shared/{token}` | no auth | the document without ids |
| GET | `/api/rag/admin/stats` | viewers and admins | `AdminStats`, see below |
| GET | `/api/rag/admin/stats/daily?days=` | viewers and admins; `days` 1–365, default 30 | `DailyStats`, see below |
| DELETE | `/api/rag/admin/users/{id}` | admins only | 204, see below |
| GET | `/healthz`, `/api/rag/healthz` | no auth | core's `Health`: `{"status": "ok", "version", "commit", "dependencies": {"postgres", "storage", "inference"}}`, each `ok` or `down` (core's `DependencyProbe`: 2 s per check, cached 15 s; `storage` only with object storage configured); a dependency that is down never fails the probe |

Every other endpoint takes `Authorization: Bearer <token>`. Errors are
`{"error": "<message>"}`: 401 unauthenticated, 402 credit exhausted,
403 admin only, 404 not yours or missing, 409 asking about an output that
is not ready, 422 an invalid body (an ask without `conversation_id`).

**Conversations.** A notebook has any number of conversations, one per
chat tab: `{"id", "notebook_id", "title", "created_at"}`. Every message
belongs to one; closing a tab is `DELETE`, which removes its messages
too. A new conversation without a title is `Chat N`, one above the
highest `Chat n` still open. `ask` requires `conversation_id` (no default
conversation); both messages are written into it, a scoped question
(`scope.output_id`) included. The model sees the newest six messages of
that conversation (each cut to 1000 characters, citation markers
removed) to resolve what a follow-up refers to; the answer still comes
from the retrieved passages only, and retrieval uses the question alone.

**Admin overview.** `GET /api/rag/admin/stats` counts across all users,
read only, with every key present (zeros included):
`{"notebooks": {"total"}, "messages": {"total", "last_24h"}, "outputs":
{"by_kind": {<each kind>}, "by_status": {<each status>}}, "jobs":
{"pending", "running", "failed"}, "shared": {"outputs"}}`. A job is
`pending` while waiting or processing without a live claim, `running`
while processing under a claim younger than ten minutes (the worker's
stale-claim limit), `failed` once failed; `shared.outputs` counts the
outputs that have a share token now. Views of shared outputs are in
account's visitor log (`/admin/visits`, path `/s/`).
`GET /api/rag/admin/stats/daily` feeds the charts:
`{"days": [{"day", "messages", "outputs", "outputs_by_kind": {<each kind>}}]}`,
one entry per UTC day for the last `days` days, oldest first and ending
today, every day and every kind present; `messages` counts questions and
answers written that day, `outputs` the outputs created that day in any
status. One query, read only. Both only read, so
the check is core's `admin_read` over `users.role` (`admin_role`):
admins and viewers pass, anyone else gets 403 `admin only`. A viewer is a
plain user everywhere else in rag, credit included.

**Deleting a user.** `DELETE /api/rag/admin/users/{id}` is account's
first step when an admin deletes a user (core's `admin_only`, admins
only), before ingest deletes the notebooks. It deletes the stored files
of the user's outputs (the audio MP3s), then, in one transaction, the
user's generated sources with their chunks, the user's outputs (also
those of deleted notebooks and in the trash), and the messages and
conversations of the user's notebooks. Notebooks and uploads stay for
ingest. Always 204, also when nothing is left or the user never
existed, so account can retry. A file that cannot be deleted is a 502
`could not delete stored object <key>` and no row is touched.

**Ask.** `answer` cites inline as single `[n]` markers, numbered 1..n in
order of first appearance; `n` maps to an entry in `citations` (`source_id`, `source_name`, `source_kind`, `chunk_id`,
`page`, `quote`, `similarity`, `chunk_index`, `chunk_count`). A citation
carries its provenance: `quote` is the verbatim text of the chunk
(never trimmed), `similarity` the cosine similarity the search
gave that chunk for this question (3 decimals), `chunk_index` (0-based)
and `chunk_count` its position in its source ("chunk 12 of 43"). The
stored assistant message keeps the same fields; messages written before
they existed have them as `null`. `GET /api/rag/chunks/{chunk_id}`
returns one chunk for its owner (`{"chunk_id", "source_id",
"source_name", "source_kind", "page", "chunk_index", "chunk_count",
"text"}`, 404 otherwise), so a reader can open the exact passage.
An answer that cites goes through the same support check as a generated
output (see Provenance): `units` holds one `{"text", "refs", "support"}`
per paragraph (its text as in `answer`, markers included) and `check`
the counts; both are stored with the assistant message and are `null`
for an answer without citations (one from the document list, the
refusal) and for messages from before. An answer in another language
than its cited passages (told apart by frequent English and German
words) is "translated": a paragraph with low overlap there is
`unverified`, not `unsupported`.
Text from the user's files is data in every prompt: both system prompts
say so, a name (file, document, notebook) is one line of at most 120
characters, and marker-shaped text in sources and summaries (`[2]`,
`[1, 3]`) reaches the model as `(2)`, `(1, 3)`, so a source cannot open a
fake passage or pass for a citation; the stored chunk and the quote stay
verbatim.
Retrieval is top-k by cosine similarity over the
notebook's ready sources with a similarity floor. An unscoped question
searches the uploads and the generated documents separately: the uploads
fill the k slots by score, and generated chunks above the floor may take
at most `RETRIEVAL_GENERATED_SLOTS` of them (default 2); the passages list
the uploads first, so an original precedes its paraphrase. The system
prompt lists the notebook's ready documents by kind and title (uploads and
generated), so a question about the notebook itself is answered even when
no passage matches; only a notebook without any ready document gets the
fixed refusal without a model call. `scope.output_id` restricts retrieval
to one generated document, without a similarity floor and with a larger
k, since the scope bounds the context.

**Source selection.** `source_ids` on `ask` and on `POST .../outputs` are
the sources the user ticked: link ids (the `id` of ingest's `Source` in
this notebook), uploads only. Absent or empty means all; an id that is not
an uploaded source of the notebook is a 422 (`source_ids: <id> is not a
source of this notebook`). On `ask` the uploads search is filtered to the
selection; the generated slots are unchanged, and the document list in
the system prompt still names every document but marks the uploads
outside the selection `not in scope`, so "why don't you see X" is
answered. A `scope.output_id` wins over the selection. On an output the
selection is stored as `options.sources` (the ids, deduplicated) and the
generator reads only those sources' summaries and chunks, balanced over
the selection; if none of them is ready when the job runs, the output
fails with `none of the selected sources is ready`. The shared view
(`/shared/{token}`) leaves `options.sources` out: it names the owner's ids.

**Outputs.** `POST /outputs` inserts the job and answers at once. The
worker entrypoint (`lasteverlm-rag-worker`) claims jobs from the
`outputs` table with `SELECT ... FOR UPDATE SKIP LOCKED` (a `waiting` row
once none of the uploads it reads, its selection or all, is still processing; a claim counts as an attempt, three
attempts fail the job, a claim older than ten minutes is abandoned), generates the document from the source
summaries plus the chunks retrieved for the kind's focus query, and
indexes the result as a source of kind `generated` in the same notebook
(chunked with core's token-window chunker, the same one ingest uses),
so the chat can cite it; `Output.source_id` names that source.

**Provenance.** Every kind cites the numbered passages of its prompt,
the same discipline as a chat answer: every unit (a report paragraph
that is not a heading, an infographic fact or section, an audio
paragraph or turn, a table row, a quiz question, a mind-map node below
the root) carries `refs` (passage numbers) and
`support`, the result of a deterministic check after generation, with no
second model call. A unit is `supported` when every ref names a passage
of the prompt and at least half (`OVERLAP_THRESHOLD = 0.5`) of its
content words occur in its cited passages together (method
`lexical-overlap-v1`: lowercased words of three or more characters or
with a digit, common English and German function words left out, cut to
five characters); `unsupported` without refs, with a ref no passage has,
or below the threshold; `unverified` when the refs are valid but the
overlap is low and the output was written in a chosen `language`, where
word overlap cannot tell. An interviewer's question without refs is no
claim and gets no `support`, nor does the mind map's root (it names the
whole map) unless it cites. A failing unit is kept and marked, never
dropped, and never fails the output. The report keeps `[n]` markers in
`content.markdown` (unknown numbers are removed) and lists
`content.units: [{"text", "refs", "support"}]`; infographic facts and
sections, the audio transcript entries, quiz questions and mind-map
nodes carry the two fields themselves; a table keeps `rows` as lists of
cells and adds `row_refs: [{"refs", "support"}]`, one per row (a quiz
question is checked with its answer and explanation). `Output.provenance` is the generation log, written when the
output is ready, for every kind (`null` for outputs from before): `{"version", "prompt_version", "model", "options",
"focus_query", "retrieval": {"k", "floor", "candidates": [{"chunk_id",
"source_id", "source_name", "page", "similarity", "in_prompt"}]},
"passages": [{"n", "chunk_id", "source_id", "source_name",
"source_kind", "page", "chunk_index", "chunk_count", "similarity",
"quote"}], "usage": {"llm": {"tokens_in", "tokens_out"}, "embedding":
{"tokens_in"}, "tts": {"seconds"}}, "started_at", "finished_at",
"check": {"method", "threshold", "supported", "unsupported",
"unverified"}}`. The shared view carries it too, without `chunk_id`,
`source_id` and the source selection, so a shared document can be
checked without logging in.

**Library and trash.** An output belongs to the user, not the notebook:
`Output.notebook_id` is the notebook it was made in and turns `null`
when ingest deletes that notebook (the foreign key sets it), while
`origin_title` keeps the notebook's title from the moment the output was
created. `GET /library/outputs` lists the caller's outputs from every
notebook. Its generated source is a library row of the user's, so ingest's
library picker can link it into another notebook, where the chat searches
and cites it without reprocessing. Deleting an output moves it to the
trash (`deleted_at`, `purge_at`): it and its generated source leave every
notebook, its share link answers 404, and its file stays. Restoring
links the source into the origin notebook again if it still exists;
links into other notebooks are not restored, as with ingest's library
trash. `DELETE /notebooks/{id}/outputs` trashes every output made in
that notebook, for the web's "delete the outputs too" before ingest
deletes the notebook. The worker purges a trashed output once the
owner's `trash_days` preference (default 14) has passed, at start and
then hourly; `DELETE /outputs/{id}/purge` does it at once. A purge
deletes the stored file first, then the generated source with its chunks
and links, then the row; a file that cannot be deleted is logged (the
sweep) or a 502 naming its key (the endpoint), and the rows stay for the
next try. A job whose notebook is deleted before it ran fails with "the
notebook was deleted".
`Output.error` is a public text: rag's own reasons (no ready source,
none of the selected sources ready, an answer that did not match the
document format, audio unavailable) as they are, otherwise a fixed text
per class (model provider, storage, internal); the exception's own
message, which can name endpoints or quote model output, goes to the log
only. A text-to-speech answer without audio is a provider failure, billed
like any other synthesis.

The focus-query chunks are balanced across sources: every ready upload
contributes its best two chunks whatever their score, the rest of the
budget (at least `RETRIEVAL_K`, two per source, at most 24 passages) goes
by score, so one large or very relevant source cannot fill the input on
its own. Every generator prompt says to cover all listed sources; the
mind map's root spans them, with a branch per source when they are on
distinct topics. After generation, a source whose distinctive file-name
words (words no other source's name has) appear nowhere in the document
is logged as a warning with the output id; the document is kept.

**Options.** `options` on `POST .../outputs` is `{"language"?, "voice"?,
"speed"?, "audio_style"?, "audio_voice_2"?}`: `language` (one of ten
codes, `de`, `en`, `fr`, ...) for every kind, the others for audio only.
`audio_style` is `overview` (default), `story` or `conversation`;
`audio_voice_2` is the expert's voice and only valid for `conversation`,
where it defaults to the next voice with the same native language as
`voice` in catalogue order (`ryan` → `aiden`, `vivian` → `serena`), or
`ryan` when there is none. An option the kind does not take, an unknown
key, code, style or voice, a second voice equal to the first, or a speed
off the offered range (0.75–1.5 in steps of 0.25) is a 422. Without `language` the document
follows the language of its sources; with it the generator is told to
write everything, the title included, in that language. Audio defaults
to `TTS_VOICE` and speed 1.0. The resolved options are stored on the
output (`outputs.options`) and returned as `Output.options` and on the
shared view. `GET /api/rag/outputs/options` lists the languages, the
voices (`id`, `label`, `gender`, native `language`, from the Qwen3-TTS
model card), the default voice, the styles and the default style, the
speed range and which options each kind takes, so clients hardcode nothing; the language preference itself
lives in account and the web sends it explicitly.

**Voice previews.** `POST /api/rag/outputs/voice-sample` speaks one or
two fixed sentences in the requested language (default `en`) with that
voice and speed (default 1.0), validated against the same catalogue
(422 otherwise). The file is stored at
`samples/<voice>/<speed>/<language>.mp3`; the first request synthesizes
it (one `tts` usage row for the caller, about one cent, 402 without
credit), every later one, from any user, gets the stored file
(`"cached": true`) without a model call. The URL is presigned for one
hour. 503 when the deployment has no text-to-speech.

`decision`: a question answered from the sources, by two independent
calls over the same numbered passages, retrieved with the question as
the focus query. Options: `question` (required, at most 500
characters), `decision_type` `yes_no` (default), `choice` with `choices`
(2–8 distinct labels) or `scale` with `levels` (3–7 ordered labels,
lowest first). The platform's decision model (`DECISION_MODEL`, core's
`OpenAICompatibleDecision`, one `decision` usage row) gets the question
and the passages and gives `model_answer`: `{"probability_yes",
"answer"}`, `{"choice", "distribution", "confidence"}` or `{"level",
"score" (probability-weighted level index, 0 = lowest), "legend",
"distribution", "confidence"}`, every value in 0..1 except `score`. The
LLM gets the same passages and the question but never that answer and
writes `verdict_text` (plain, one or two sentences), `evidence_for` and
`evidence_against` (`[{"text", "refs", "support"}]`, checked like every
unit), `gaps` (what the sources do not say) and, for a choice or a
scale, `llm_choice`, the option its evidence argues about. `agreement`
compares the two: `consistent`, `conflicting` (shown, never hidden) or
`unclear`, with `agreement_note`; for yes/no, a probability of at least
0.6 with more supported evidence for than against is consistent, at most
0.4 with more against too, the mirror cases conflict; for a choice or
scale, the same pick with more supported for is consistent, a different
pick with more supported for, or the same with more against, conflicts.
Without supported evidence on either side `agreement` is `undecided` and
`verdict_text` is "The sources do not decide this." whatever the number;
the LLM's own sentence goes into `provenance.llm_verdict_text`.
`provenance.calls` lists both calls (`role` `decision` with the state's
size, `role` `evidence`), `provenance.usage.decision` the decision
model's input tokens.

`audio`: the model writes a spoken-word script (three to five minutes)
in the chosen style, with a prompt and a JSON schema per style:
`overview` and `story` are `{"title", "paragraphs": [{"text", "refs"}]}`
read by one narrator (the story frames the material as a narrative but
invents nothing), `conversation` is `{"title", "turns": [{"speaker":
"interviewer" | "expert", "text", "refs"}]}`, where the expert
answers only from the material and both must speak (at most 6000
characters in all). The worker reads the turns with `TTS_MODEL`, the
narrator and the interviewer with `voice`, the expert with
`audio_voice_2`, consecutive turns of one voice as one stretch, in
segments of at most 1500 characters that end at a sentence, one `tts`
usage row per segment priced per second of generated audio as the
platform reports it, and stores the joined MP3 at
`<notebook_id>/<output_id>/audio.mp3` in object storage. The row keeps
`{"key", "transcript": [{"speaker", "text"}]}` (`speaker` is
`narrator`, `interviewer` or `expert`; audio outputs from before have
no transcript); every read (the output, the list, the shared view)
returns `{"url", "transcript"}`, `url` a presigned GET URL valid for
one hour. The script, with `Interviewer:` / `Expert:` labels for a
conversation, is the indexed text, so the chat can cite what the audio
says. Without
`TTS_MODEL` an audio output fails at once with a clear error, before
any model call.

## Configuration

Read from the environment; startup fails when a required value is
missing or a configured model has no price.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL with the `vector` extension, shared with the other services |
| `INFERENCE_API_KEY`, `INFERENCE_BASE_URL` | key yes, URL defaults to Vultr Serverless Inference | OpenAI-compatible inference API |
| `LLM_MODEL`, `LLM_MAX_TOKENS` | model yes, budget default 1024 | chat model for answers and documents; called with thinking disabled, so the budget goes to content |
| `LLM_TIMEOUT_SECONDS` | no; default 60 | seconds per inference request (core); the worker uses at least 180, since a document is one long completion |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | yes / default 1536 | query and chunk embedding, requested at that width (`dimensions`); identical to the ingest service |
| `MODEL_PRICES` | yes | JSON `{"<model>": {"in": cents, "out": cents}}` per million tokens; every configured model needs an entry |
| `AUTH_JWT_SECRET` or `DEMO_TOKEN` | one of them | bearer token scheme; both set means JWT first, demo token second |
| `DECISION_MODEL` | no; default `clef` (core) | the platform's decision model for the decision kind, used by the worker; it needs a `MODEL_PRICES` entry, `in` per million input tokens, or startup refuses |
| `TTS_MODEL`, `TTS_VOICE` | no; voice default `ryan` | enables the audio kind; the voice is the default for audio outputs and must be one of the platform's (`vivian`, `serena`, `ryan`, ...; startup refuses any other), not an OpenAI name; the model needs a `MODEL_PRICES` entry, `in` per million seconds of generated audio |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | for audio | object storage for audio files, through core's storage client |
| `RETRIEVAL_K` | no | chunks per question, default 8 |
| `RETRIEVAL_GENERATED_SLOTS` | no; default `2` | how many of an unscoped question's k passages may come from generated documents (above the floor, listed after the uploads); `0` leaves them out |
| `SIMILARITY_FLOOR` | no | minimum cosine similarity, default 0.3 |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, ... | no | core's rate-limit middleware, defaults 120 / 15 / 3; see `core/README.md` |
| `LOG_LEVEL` | no | default `INFO` |
| `APP_VERSION`, `APP_COMMIT` | no | the build reported on `/healthz`; `unknown` when unset |

Auth, inference, prices and rate limiting are loaded by `lasteverlm_core`;
only the rest is rag's own. Before any model call the service runs core's credit
check (`has_credit`: a positive balance of ledger credits minus priced usage, for
admins as for everyone else) and answers 402 otherwise. Every
embedding and LLM call writes one priced row to the `usage` table.

## Run locally

```bash
make venv           # uv venv + editable install of ../core and this package with dev extras
make check          # ruff, mypy --strict, pytest; creates .venv on first run
make run            # API: uvicorn on :8000 with reload; needs the variables above
make worker         # worker: claims and runs output jobs; same variables
make build          # docker image lasteverlm-rag:<git sha>, built with the repository root as context
```

The tests need no database and no inference provider: the store, the
retriever, the embedder, the LLM and the rate-limit store are faked
through `create_app`.

## Database

`db/migrations/0001_rag.sql` creates `messages` and `outputs`;
`0002_rag_conversations.sql` adds `conversations` and
`messages.conversation_id` and moves each notebook's existing messages
into one conversation `Chat 1`; `0003_rag_output_options.sql` adds
`outputs.options`; `0004_rag_outputs_library.sql` gives outputs an
`owner`, `origin_title` and `deleted_at`, makes `notebook_id` nullable
(set to null when the notebook is deleted) and points `source_id` at the
generated library row instead of its link (expand only: `owner` stays
nullable for pods of the previous release, and reads fall back to the
notebook's owner); `0005_rag_output_provenance.sql` adds
`outputs.provenance`, the generation log; `0006_rag_message_support.sql`
adds `messages.support` (`{"units", "check"}` of an answer);
`0007_rag_decision_kind.sql` allows the kind `decision`. The
migrations runner applies them after
core, account and ingest. The
service reads ingest's `notebooks`, `library_sources`, `sources` and
`chunks`. A library source is a file, text, URL or image processed once
for its owner; `sources` links it into a notebook, and the link's id is
the source id the API and citations use. Chunks belong to the library
source, so search goes notebook → links → library sources (status, kind,
name, summary) → chunks. For a generated output rag writes a hidden
library row of kind `generated`, owned by the user, plus its link into
the notebook under one id, in one transaction, and the chunks on that
row. Ingest lists such rows only in its picker and never trashes or
purges them; rag trashes, restores and purges them with their output.

## Deployment

One image per Git SHA, built by `docker.yml` with the repository root as
context so `core/` is installed next to `rag/`, run as a non-root user in
the `lasteverlm` namespace. Two Deployments of the same image: the API
(default command, port 8000, behind ingress-nginx at `/api/rag`) and the
worker (`lasteverlm-rag-worker`), which scale independently; the API
stays stateless. Charts and secrets live in `infra/`.

## Layout

```text
lasteverlm_rag/
├── main.py         FastAPI app, routes, error shape
├── service.py      ask flow and output lifecycle (API side and worker side)
├── worker.py       worker entrypoint: claim jobs, run them, release or finish
├── citations.py    pure marker-to-citation mapping
├── coverage.py     balanced generator input and the uncovered-source check
├── options.py      output options catalogue (languages, voices, speeds) and validation
├── speech.py       splitting an audio script into synthesis segments
├── voice_samples.py cached voice previews
├── admin.py        admin statistics (totals, daily series)
├── outputs/        OutputGenerator interface, one module per kind
├── store.py        Retriever and Store interfaces + PostgreSQL/pgvector adapters
├── models.py       request bodies and internal data shapes (shared models come from core)
└── config.py       settings from the environment
db/migrations/      the service's own tables
```
