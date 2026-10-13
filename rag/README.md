# rag

[![CI](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://img.shields.io/badge/Keep_the_Why-context%2F-2b6cb0)](https://keepthewhy.com)

The rag service of lasteverLM: retrieval over one notebook's chunks,
answers with citations mapped back to source and passage, the message
history, and the generated documents (report, quiz, table, mind map,
infographic, audio). The API contract and the data model live
in the repository root, [`docs/architecture.md`](../docs/architecture.md);
this directory implements the `/api/rag` prefix.

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/rag/notebooks/{id}/ask` | `{"question", "scope": {"output_id"}?}` | `Answer` |
| GET | `/api/rag/notebooks/{id}/messages` | | `[Message]` |
| POST | `/api/rag/notebooks/{id}/outputs` | `{"kind"}` | 202 `Output`, status `waiting` or `processing` |
| GET | `/api/rag/notebooks/{id}/outputs` | | `[Output]` |
| GET | `/api/rag/outputs/{id}` | | `Output` |
| DELETE | `/api/rag/outputs/{id}` | | 204 |
| POST | `/api/rag/outputs/{id}/share` | | `{"share_token"}` |
| DELETE | `/api/rag/outputs/{id}/share` | | 204 |
| GET | `/api/rag/shared/{token}` | no auth | the document without ids |
| GET | `/api/rag/admin/stats` | admins only | `AdminStats`, see below |
| GET | `/healthz`, `/api/rag/healthz` | no auth | `{"status": "ok"}` |

Every other endpoint takes `Authorization: Bearer <token>`. Errors are
`{"error": "<message>"}`: 401 unauthenticated, 402 credit exhausted,
403 admin only, 404 not yours or missing, 409 asking about an output that
is not ready.

**Admin overview.** `GET /api/rag/admin/stats` counts across all users,
read only, with every key present (zeros included):
`{"notebooks": {"total"}, "messages": {"total", "last_24h"}, "outputs":
{"by_kind": {<each kind>}, "by_status": {<each status>}}, "jobs":
{"pending", "running", "failed"}, "shared": {"outputs"}}`. A job is
`pending` while waiting or processing without a live claim, `running`
while processing under a claim younger than ten minutes (the worker's
stale-claim limit), `failed` once failed; `shared.outputs` counts the
outputs that have a share token now. Views of shared outputs are in
account's visitor log (`/admin/visits`, path `/s/`). The admin check is
core's `admin_only` over `users.is_admin`; anyone else gets 403.

**Ask.** `answer` cites inline as single `[n]` markers, numbered 1..n in
order of first appearance; `n` maps to an entry in `citations` (`source_id`, `source_name`, `source_kind`, `chunk_id`,
`page`, `quote`). Retrieval is top-k by cosine similarity over the
notebook's ready sources with a similarity floor; if nothing passes it,
the answer is a fixed refusal with empty citations and the model is not
called. An unscoped question retrieves from the uploaded sources only;
`scope.output_id` restricts retrieval to one generated document, without a
similarity floor and with a larger k, since the scope bounds the context.

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
| `TTS_MODEL`, `TTS_VOICE` | no; voice default `ryan` | enables the audio kind; the voice is one of the platform's (`vivian`, `serena`, `ryan`, ...), not an OpenAI name; the model needs a `MODEL_PRICES` entry, `in` per million characters |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | for audio | object storage for audio files, through core's storage client |
| `RETRIEVAL_K` | no | chunks per question, default 8 |
| `RETRIEVAL_INCLUDE_GENERATED` | no | default `false`: an unscoped question is answered from the uploads only; generated documents are reached through `scope.output_id` |
| `SIMILARITY_FLOOR` | no | minimum cosine similarity, default 0.3 |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, ... | no | core's rate-limit middleware, defaults 120 / 15 / 3; see `core/README.md` |
| `LOG_LEVEL` | no | default `INFO` |

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

`db/migrations/0001_rag.sql` creates `messages` and `outputs`. The
migrations runner applies it after core, account and ingest. The
service reads ingest's `notebooks`, `sources` and `chunks` and writes
`sources` and `chunks` only for kind `generated`.

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
