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
| GET | `/api/rag/notebooks/{id}/outputs` | | `[Output]` |
| GET | `/api/rag/outputs/{id}` | | `Output` |
| DELETE | `/api/rag/outputs/{id}` | | 204 |
| POST | `/api/rag/outputs/{id}/share` | | `{"share_token"}` |
| DELETE | `/api/rag/outputs/{id}/share` | | 204 |
| GET | `/api/rag/shared/{token}` | no auth | the document without ids |
| GET | `/api/rag/admin/stats` | admins only | `AdminStats`, see below |
| GET | `/api/rag/admin/stats/daily?days=` | admins only; `days` 1–365, default 30 | `DailyStats`, see below |
| GET | `/healthz`, `/api/rag/healthz` | no auth | core's `Health`: `{"status": "ok", "version", "commit"}` |

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
status. One query, read only. The admin check is
core's `admin_only` over `users.is_admin`; anyone else gets 403.

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
once no source is still processing; a claim counts as an attempt, three
attempts fail the job, a claim older than ten minutes is abandoned), generates the document from the source
summaries plus the chunks retrieved for the kind's focus query, and
indexes the result as a source of kind `generated` in the same notebook
(chunked with core's token-window chunker, the same one ingest uses),
so the chat can cite it; `Output.source_id` names that source. Deleting
the output deletes the source and its stored files.

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
"speed"?}`: `language` (one of ten codes, `de`, `en`, `fr`, ...) for every
kind, `voice` and `speed` for audio only. An option the kind does not
take, an unknown key, code or voice, or a speed off the offered range
(0.75–1.5 in steps of 0.25) is a 422. Without `language` the document
follows the language of its sources; with it the generator is told to
write everything, the title included, in that language. Audio defaults
to `TTS_VOICE` and speed 1.0. The resolved options are stored on the
output (`outputs.options`) and returned as `Output.options` and on the
shared view. `GET /api/rag/outputs/options` lists the languages, the
voices (`id`, `label`, `gender`, native `language`, from the Qwen3-TTS
model card), the default voice, the speed range and which options each
kind takes, so clients hardcode nothing; the language preference itself
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

`audio`: the model writes a spoken-word script (three to five minutes);
the worker reads it with `TTS_MODEL` and `TTS_VOICE` in segments of at
most 1500 characters that end at a sentence, one `tts` usage row per
segment priced per input character, and stores the joined MP3 at
`<notebook_id>/<output_id>/audio.mp3` in object storage. The row keeps
`{"key"}`; every read (the output, the list, the shared view) returns
`{"url"}`, a presigned GET URL valid for one hour. The script is the
indexed text, so the chat can cite what the audio says. Without
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
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | yes / default 1536 | query and chunk embedding, requested at that width (`dimensions`); identical to the ingest service |
| `MODEL_PRICES` | yes | JSON `{"<model>": {"in": cents, "out": cents}}` per million tokens; every configured model needs an entry |
| `AUTH_JWT_SECRET` or `DEMO_TOKEN` | one of them | bearer token scheme; both set means JWT first, demo token second |
| `TTS_MODEL`, `TTS_VOICE` | no; voice default `ryan` | enables the audio kind; the voice is the default for audio outputs and must be one of the platform's (`vivian`, `serena`, `ryan`, ...; startup refuses any other), not an OpenAI name; the model needs a `MODEL_PRICES` entry, `in` per million characters |
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
`outputs.options`. The migrations runner applies them after
core, account and ingest. The
service reads ingest's `notebooks`, `library_sources`, `sources` and
`chunks`. A library source is a file, text, URL or image processed once
for its owner; `sources` links it into a notebook, and the link's id is
the source id the API and citations use. Chunks belong to the library
source, so search goes notebook → links → library sources (status, kind,
name, summary) → chunks. For a generated output rag writes a hidden
library row of kind `generated` (never listed in the library) plus its
link under one id, in one transaction, and the chunks on that row;
deleting the output deletes the library row, and the link and chunks go
with it.

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
├── outputs/        OutputGenerator interface, one module per kind
├── store.py        Retriever and Store interfaces + PostgreSQL/pgvector adapters
├── models.py       request bodies and internal data shapes (shared models come from core)
└── config.py       settings from the environment
db/migrations/      the service's own tables
```
