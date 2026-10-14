# lasteverLM-ingest

[![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

The ingest service of [lasteverLM](https://github.com/oliver-zehentleitner/lasteverLM),
a NotebookLM-style assistant. It owns notebooks and each user's source
library: a source is uploaded (PDF, plain text, image, recording: MP3, WAV, M4A, AAC, Ogg/Opus, FLAC, WebM, the audio of an MP4) or given as a URL
(web page, PDF or text behind a link) once, stored in the user's library
and linked into any number of notebooks; worker pods claim it from the
database once, fetch and parse it, cut it into overlapping chunks, embed and
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
| `MODEL_PRICES` | until core ships defaults | JSON `{"<model>": {"in": <cents per million tokens>, "out": ...}}`; the service refuses to start when `EMBEDDING_MODEL`, `LLM_MODEL` or `STT_MODEL` has no price |
| `AUTH_JWT_SECRET`, `DEMO_TOKEN` | at least one | the HS256 secret the account service signs JWTs with (issuer `lasteverlm`), and/or the shared demo token; a JWT is checked first |
| `MAX_UPLOAD_BYTES` | no | default 20 MiB; larger uploads get 413; audio has its own cap |
| `MAX_AUDIO_UPLOAD_BYTES` | no | default 60 MiB, the uploaded recording; an MP3/WAV must also be within core's 25 MiB, a converted recording's MP3 likewise |
| `STT_MODEL` | no | transcribes MP3/WAV sources, core's default `whisper-large-v3-turbo`; needs a `MODEL_PRICES` entry (`in` in cents per million seconds) or the service refuses to start |
| `STT_TIMEOUT_SECONDS` | no | one transcription call, default 300, no SDK retries; must be below `CLAIM_TIMEOUT_SECONDS` |
| `CHUNK_TOKENS`, `CHUNK_OVERLAP_TOKENS` | no | override core's chunker defaults for one deployment; unset means core decides |
| `EMBED_BATCH_SIZE` | no | texts per embedding request, default 64 |
| `WORKER_POLL_SECONDS` | no | how often an idle worker looks for work, default 2 |
| `CLAIM_TIMEOUT_SECONDS` | no | a claim not refreshed for this long (a job refreshes it with every model call and embedding batch) is taken over by another worker, default 600; after three attempts a source is `failed`, also when its worker died or hung each time |
| `SUMMARY_INPUT_TOKENS`, `SUMMARY_MAX_TOKENS` | no | how much of a source the summary prompt sees (6000) and how long the answer may be (300) |
| `IMAGE_MAX_TOKENS` | no | how long the model's transcription and description of an image source or a PDF page may be (2000) |
| `PDF_VISION_MAX_PAGES` | no | most pages of one PDF the vision model reads (`vision`/`auto` capture); more fail the source before any call (100) |
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
make test-postgres             # the repository's SQL against a throwaway pgvector container
```

`make check` installs first, so it works on a fresh checkout and is what CI runs.

The tests use in-memory stand-ins for the database, the bucket and the
inference API (`tests/fakes.py`); nothing touches the network.
`make test-postgres` runs `tests/test_postgres.py` against a real
PostgreSQL with the family's migrations applied (the library and its
dedupe conflict, ownership, the trash and its retention, the queue under
concurrent claims, the starter copy, the admin counts); it is skipped
without Docker, and `make check` deselects it.

## Build

```bash
make build                     # docker build -f ingest/Dockerfile <repo root>
```

The build context is the repository root, because `core/` is installed
from the same checkout (it is not published). Multi-stage image on
`python:3.13-slim`, runs as an unprivileged user. A first stage builds
a minimal ffmpeg (audio conversion) from a pinned, checksum-verified
source tarball. To bump ffmpeg: take the version from
<https://ffmpeg.org/releases/>, check its `.asc` against the FFmpeg
release signing key, and set `FFMPEG_VERSION` and `FFMPEG_SHA256` in the
Dockerfile.
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
