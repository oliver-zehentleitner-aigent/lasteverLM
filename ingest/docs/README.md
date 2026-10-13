# Operating lasteverLM-ingest

Endpoints, processing and the database in detail. Configuration, run,
test, build and deploy are in the [README](../README.md); why it is
built this way is in [`../context/`](../context/index.md); the API it
implements is the ingest section of the family's
[architecture](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/architecture.md).

## Database

The service owns `notebooks`, `sources` and `chunks`. Two values in
`sources` are written by others: `kind = 'generated'` rows are created
by the rag service when it indexes a finished output, and this service
lists and deletes them like any other source but never loads them. The
migration is
[`db/migrations/0001_ingest.sql`](../db/migrations/0001_ingest.sql), plain
SQL for psql, applied by infra's `make migrate` after infra's extensions
migration and core's migration; the runner wraps each file in one
transaction, so the file has no `begin`/`commit` of its own. An applied
file is never edited; a change is a new numbered file. The embedding dimension
is a psql variable:

```bash
psql "$DATABASE_URL" -v EMBEDDING_DIMENSION="$EMBEDDING_DIMENSION" -f db/migrations/0001_ingest.sql
```

## Endpoints

Prefix `/api/ingest`, bearer token on everything except `/healthz`,
which also answers at the root (`GET /healthz`) for the Kubernetes probes.
The token is resolved by core's `current_user` (session JWT from the
account service first, demo token second). Core's `RateLimitMiddleware`
sits outermost: 429 when a client IP exceeds `RATE_LIMIT_PER_MINUTE`,
403 for a banned IP, one `access_log` row per request.

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/notebooks` | 200 | the caller's notebooks |
| POST | `/notebooks` | 201 | `{"title"}` |
| DELETE | `/notebooks/{id}` | 204 | removes sources, chunks and stored files |
| GET | `/notebooks/{id}/sources` | 200 | poll this for `status` |
| POST | `/notebooks/{id}/sources` | 202 | multipart `file` (PDF, `.txt`, `.md`, PNG, JPEG, WebP, GIF), or JSON `{"url"}` (`http`/`https`, no credentials in the URL) |
| DELETE | `/sources/{id}` | 204 | |
| GET | `/healthz` | 200 | liveness and readiness probe |

Errors are `{"error": "<message>"}`: 400 bad upload, 401 token, 402
credit exhausted, 404 not yours or missing, 413 too large, 415
unsupported type, 422 invalid body.

## Processing

`POST /sources` checks the caller's credit, writes the source row with
`status: processing`, uploads the file to the bucket at
`<notebook_id>/<source_id>/<name>` and returns. For a URL source the
stored object is the URL itself (`<notebook_id>/<source_id>/url`) and the
source's `name` is the URL; the API opens no connection to it. That row is now in the
queue: the queue is the `sources` table, a `processing` row that no
worker holds. Worker processes (`lasteverlm-ingest-worker`, any number
of them) claim one row at a time with `UPDATE ... WHERE id = (SELECT ...
FOR UPDATE SKIP LOCKED)`, oldest first, writing `claimed_at` and
`claimed_by`; a claim older than `CLAIM_TIMEOUT_SECONDS` is treated as
abandoned and taken over. An idle worker polls every
`WORKER_POLL_SECONDS`. The pipeline
(`lasteverlm_ingest.worker.process_source`) loads the file from the
bucket, parses it, chunks it, embeds the chunks in batches, writes them
and records one `usage` row of kind `embedding`. It then asks the
language model for a one-paragraph summary in the language of the
source (the first `SUMMARY_INPUT_TOKENS` tokens go into the prompt),
records a second `usage` row of kind `llm`, stores the summary in
`sources.summary` for the output generators, and sets `ready`. A failure
that a retry cannot change (unreadable file, no text, credit exhausted)
sets `failed` at once. A failure that may pass next time (object
storage, the embedding or summary request, an unexpected error) leaves
the row `processing` with the error text, so the next worker takes it
over after the claim timeout; the third failed attempt sets `failed` for
good. The user sees the `error` either way. The credit balance is
checked before the upload is stored, before the embedding call and
before the summary call. The API pods never process
anything, so they stay stateless and the workers scale on their own. A
worker finishes the source in flight before it stops on SIGTERM.

## URL sources

The worker fetches the URL (`lasteverlm_ingest.loaders.url`) and hands
the body to the loader for its content type: `text/html` and
`application/xhtml+xml` to the HTML extractor, `application/pdf` to the
PDF loader, `text/plain` and `text/markdown` to the text loader; any
other type fails the source. The HTML extractor drops scripts, styles
and page chrome (`nav`, `header`, `footer`, `aside`, forms), keeps only
`<main>`/`<article>` when the page has them, and puts the page title
first.

The worker runs inside the cluster, so every connection is guarded: the
host is resolved by the loader itself, every address it resolves to
must be public (no loopback, private, link-local such as the cloud
metadata endpoint, carrier-grade NAT, multicast or reserved ranges,
IPv4-mapped IPv6 included), and the socket connects to the address that
was checked. Redirects are followed by hand, at most five, and each hop
goes through the same check. The body is capped at `MAX_UPLOAD_BYTES`,
the whole fetch at 30 seconds.

A 4xx answer, a blocked address, an unsupported type or a body over the
cap fail the source at once; a timeout, a refused connection, 429 or
5xx are retried like any other transient failure.

## Image sources

An upload named `.png`, `.jpg`, `.jpeg`, `.webp` or `.gif` (or sent with
that media type) is an image source. The API checks the file's first
bytes and answers 415 when they are not one of those four formats; the
stored object gets the media type from those bytes, not from the name.

The worker reads the image with one call to `LLM_MODEL` (the platform's
chat model takes images): it transcribes all legible text verbatim and
then describes the image, charts and tables with their values, in the
language of the text in the image. Because that call is billed, the
image loader is a `ModelLoader`: the worker checks the credit before it
and records its own `usage` row of kind `llm`, before the embedding and
summary rows. The text is then chunked, embedded and summarized like any
other source. A model refusing the image (HTTP 400) fails the source at
once, and so does an empty answer (a blank image: "the image holds no
readable content"), whose call is still recorded as usage; other
provider errors are retried. `IMAGE_MAX_TOKENS` (2000) caps
the answer.

## Running the container locally

```bash
make build
docker run --rm -p 8000:8000 --env-file .env lasteverlm-ingest:$(git rev-parse --short HEAD)
```
