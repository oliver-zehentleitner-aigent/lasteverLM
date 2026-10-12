# rag

[![CI](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://img.shields.io/badge/Keep_the_Why-context%2F-2b6cb0)](https://keepthewhy.com)

The rag service of lasteverLM: retrieval over one notebook's chunks,
answers with citations mapped back to source and passage, the message
history, and the generated documents (report, quiz, table, mind map,
infographic; audio prepared). The API contract and the data model live
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
| GET | `/healthz`, `/api/rag/healthz` | no auth | `{"status": "ok"}` |

Every other endpoint takes `Authorization: Bearer <token>`. Errors are
`{"error": "<message>"}`: 401 unauthenticated, 402 credit exhausted,
404 not yours or missing, 409 asking about an output that is not ready.

**Ask.** `answer` cites inline as `[n]`; `n` maps to an entry in
`citations` (`source_id`, `source_name`, `source_kind`, `chunk_id`,
`page`, `quote`). Retrieval is top-k by cosine similarity over the
notebook's ready sources with a similarity floor; if nothing passes it,
the answer is a fixed refusal with empty citations and the model is not
called. `scope.output_id` restricts retrieval to one generated document.

**Outputs.** `POST /outputs` inserts the job and answers at once. The
worker entrypoint (`lasteverlm-rag-worker`) claims jobs from the
`outputs` table with `SELECT ... FOR UPDATE SKIP LOCKED` (a `waiting` row
once no source is still processing; a claim counts as an attempt, three
attempts fail the job, a claim older than ten minutes is abandoned), generates the document from the source
summaries plus the chunks retrieved for the kind's focus query, and
indexes the result as a source of kind `generated` in the same notebook,
so the chat can cite it; `Output.source_id` names that source. Deleting
the output deletes the source. `audio` is registered but fails with a
clear error until the inference platform offers text-to-speech.

## Configuration

Read from the environment; startup fails when a required value is
missing or a configured model has no price.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL with the `vector` extension, shared with the other services |
| `INFERENCE_BASE_URL`, `INFERENCE_API_KEY` | yes | OpenAI-compatible inference API (Vultr Serverless Inference in production) |
| `LLM_MODEL` | yes | chat model for answers and documents |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | yes / default 1536 | query and chunk embedding; identical to the ingest service |
| `MODEL_PRICES` | yes | JSON `{"<model>": {"in": cents, "out": cents}}` per million tokens; every configured model needs an entry |
| `AUTH_JWT_SECRET` or `DEMO_TOKEN` | one of them | bearer token scheme; both set means JWT first, demo token second |
| `TTS_MODEL` | no | enables the audio kind once the platform offers speech synthesis |
| `RETRIEVAL_K` | no | chunks per question, default 8 |
| `SIMILARITY_FLOOR` | no | minimum cosine similarity, default 0.3 |
| `LOG_LEVEL` | no | default `INFO` |

Before any model call the service checks the caller's balance (ledger
credits minus priced usage) and answers 402 when it is zero. Every
embedding and LLM call writes one priced row to the `usage` table.

## Run locally

```bash
make check          # ruff, mypy --strict, pytest; creates .venv on first run
make run            # API: uvicorn on :8000 with reload; needs the variables above
make worker         # worker: claims and runs output jobs; same variables
make build          # docker image lasteverlm-rag:<git sha>, built with the repository root as context
```

The tests need no database and no inference provider: the store, the
retriever, the embedder and the LLM are faked through `create_app`.

## Database

`db/migrations/0001_rag.sql` creates `messages` and `outputs`. The
migrations runner applies it after core, account and ingest. The
service reads ingest's `notebooks`, `sources` and `chunks` and writes
`sources` and `chunks` only for kind `generated`.

## Deployment

One image per Git SHA, built by `docker.yml`, run as a non-root user in
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
├── chunking.py     token windows for generated documents
├── providers.py    LLM, embedder and TTS interfaces + OpenAI-compatible adapters
├── store.py        Retriever and Store interfaces + PostgreSQL/pgvector adapters
├── contracts.py    shared models, token verification, pricing (mirror of lasteverlm-core)
├── models.py       internal data shapes
└── config.py       settings from the environment
db/migrations/      the service's own tables
```
