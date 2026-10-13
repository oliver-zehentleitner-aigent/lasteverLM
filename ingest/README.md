# lasteverLM-ingest

[![ci](https://github.com/oliver-zehentleitner/lasteverLM-ingest/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM-ingest/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM-ingest/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM-ingest/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

The ingest service of [lasteverLM](https://github.com/oliver-zehentleitner/lasteverLM),
a NotebookLM-style assistant. It owns notebooks and sources: a source is
uploaded (PDF, plain text, image) or given as a URL (web page, PDF or text
behind a link) and stored by the API; worker pods claim it from the
database, fetch and parse it, cut it into overlapping chunks, embed and
write them, and ask the language model for a one-paragraph summary. The
rag service retrieves the chunks and reads the summaries.

API prefix: `/api/ingest`. The contract is the ingest section of the
family's [architecture](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/architecture.md);
a change to it is a pull request there first.

- How to operate it in detail (endpoints, processing, migration): [`docs/README.md`](docs/README.md)
- What comes from the shared library (models, token resolution, usage accounting, model prices, providers, chunking, rate limiting): [`core/`](../core/README.md)
- Why it is built this way: [`context/index.md`](context/index.md)
- Family rules and standards: the parent's [AGENTS.md](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/AGENTS.md) and [repository standard](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/repository-standard.md)

## Configuration

Everything comes from the environment; the service fails at startup
naming the first missing or invalid value. `.env.example` is a template.

| Variable | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL DSN, `vector` extension installed |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | yes | object storage for uploads; `S3_REGION` optional, default `us-east-1` |
| `INFERENCE_API_KEY` | yes | key for the OpenAI-compatible inference API; `INFERENCE_BASE_URL` optional, default Vultr Serverless Inference |
| `EMBEDDING_MODEL` | yes | same model as the rag service uses for questions |
| `EMBEDDING_DIMENSION` | no | default 1536; requested from the embedding model on every call (`dimensions`) and must match the `chunks.embedding` column |
| `LLM_MODEL` | yes | writes the per-source summary; `LLM_MAX_TOKENS` optional, default 1024, the ceiling for one completion (the summary asks for 300) |
| `MODEL_PRICES` | until core ships defaults | JSON `{"<model>": {"in": <cents per million tokens>, "out": ...}}`; the service refuses to start when `EMBEDDING_MODEL` or `LLM_MODEL` has no price |
| `AUTH_JWT_SECRET`, `DEMO_TOKEN` | at least one | the HS256 secret the account service signs JWTs with (issuer `lasteverlm`), and/or the shared demo token; a JWT is checked first |
| `MAX_UPLOAD_BYTES` | no | default 20 MiB; larger uploads get 413 |
| `CHUNK_TOKENS`, `CHUNK_OVERLAP_TOKENS` | no | override core's chunker defaults for one deployment; unset means core decides |
| `EMBED_BATCH_SIZE` | no | texts per embedding request, default 64 |
| `WORKER_POLL_SECONDS` | no | how often an idle worker looks for work, default 2 |
| `CLAIM_TIMEOUT_SECONDS` | no | a claim older than this is taken over by another worker, default 600; after three attempts a source is `failed` |
| `SUMMARY_INPUT_TOKENS`, `SUMMARY_MAX_TOKENS` | no | how much of a source the summary prompt sees (6000) and how long the answer may be (300) |
| `IMAGE_MAX_TOKENS` | no | how long the model's transcription and description of an image source may be (2000) |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, `STRIKE_WINDOW_HOURS`, `ACCESS_LOG_HEALTHZ_SAMPLE` | no | core's rate-limit middleware, defaults 120 / 15 / 3 / 24 / 100 |
| `LOG_LEVEL` | no | default `INFO` |

## Run locally

Needs a reachable PostgreSQL with the migration applied, an S3 bucket and
an inference endpoint; without them the start fails with a clear error.

```bash
make install                   # .venv with core (installed from ../core) and the dev extras, idempotent
cp .env.example .env           # fill in the values
set -a; source .env; set +a
make run                       # API: uvicorn on :8000, reload on
make worker                    # in a second shell: processes uploaded sources
curl -s localhost:8000/healthz
```

The API only stores uploads and queues them; without a worker, sources
stay in `processing`.

## Test

```bash
make check                     # make install, then ruff check, black --check, mypy, pytest
```

`make check` installs first, so it works on a fresh checkout and is what CI runs.

The tests use in-memory stand-ins for the database, the bucket and the
inference API (`tests/fakes.py`); nothing touches the network.

## Build

```bash
make build                     # docker build -f ingest/Dockerfile <repo root>
```

The build context is the repository root, because `core/` is installed
from the same checkout (it is not published). Multi-stage image on
`python:3.13-slim`, runs as an unprivileged user.
The default command is the API on `PORT` (default 8000); the worker is
the same image with the command `lasteverlm-ingest-worker`. CI builds
the image on every push.

## Deploy

Deployment is owned by [lasteverLM-infra](https://github.com/oliver-zehentleitner/lasteverLM-infra):
two Deployments from this image in namespace `lasteverlm` — the API
with a Service and probes on `GET /healthz`, and the worker
(`lasteverlm-ingest-worker`, scaled by replicas, no Service, stops
after the current source on SIGTERM) — configuration from
the `lasteverlm-config` ConfigMap and the `lasteverlm-db`,
`lasteverlm-s3`, `lasteverlm-inference` and `lasteverlm-auth` Secrets.
The migrations in
`db/migrations/` are applied by infra's `make migrate`.

Status: live at https://lasteverlm.zehentleitner.co since 0.1.0.

## License

MIT, see [LICENSE](LICENSE).
