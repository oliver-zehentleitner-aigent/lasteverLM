# Operating lasteverLM-ingest

Endpoints, processing and the database in detail. Configuration, run,
test, build and deploy are in the [README](../README.md); why it is
built this way is in [`../context/`](../context/index.md); the API it
implements is the ingest section of the family's
[architecture](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/architecture.md).

## Database

The service owns `notebooks`, `library_sources`, `sources` and `chunks`.
A library source is what a user uploaded or entered once (a file, an
image, a URL), owned by that user, processed once; its chunks hang on it
(`chunks.library_source_id`). A source is the link of a library source
into a notebook (`sources.library_source_id`, unique per notebook); its
id is the public source id. Library sources of kind `generated` are
written by the rag service when it indexes a finished output: they live
only through their one link, this service lists and detaches them like
any other source, never loads them, and never shows them in the library.
The migrations are
[`db/migrations/0001_ingest.sql`](../db/migrations/0001_ingest.sql),
[`0002_source_size.sql`](../db/migrations/0002_source_size.sql)
(the stored object's size) and
[`0003_source_library.sql`](../db/migrations/0003_source_library.sql)
(the library; the expand step: every existing source got a library
source with the same id, the old columns on `sources` and `chunks` stay
nullable until 0004 drops them one release later), plain SQL for psql, applied by infra's `make migrate` after infra's extensions
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
| DELETE | `/notebooks/{id}` | 204 | detaches its sources (they stay in the library) and deletes its generated sources |
| GET | `/notebooks/{id}/sources` | 200 | poll this for `status` |
| POST | `/notebooks/{id}/sources` | 202 / 200 | multipart `file` (PDF, `.txt`, `.md`, PNG, JPEG, WebP, GIF) with an optional field `capture` for PDFs (`text`, `vision`, `auto`; default `auto`), JSON `{"url"}` (`http`/`https`, no credentials in the URL), or JSON `{"library_id"}` (add from the library); 200 with the existing source when it is already in this notebook |
| DELETE | `/sources/{id}` | 204 | detach: removes the source from this notebook, it stays in the library |
| GET | `/library` | 200 | the caller's library, newest first, with where-used |
| GET | `/library/{id}` | 200 | one library source |
| DELETE | `/library/{id}` | 204 | to the trash: removed from every notebook, chunks and stored object kept |
| GET | `/library/trash` | 200 | the caller's trash, most recently deleted first |
| POST | `/library/{id}/restore` | 204 | back from the trash into the library, in no notebook |
| DELETE | `/library/{id}/purge` | 204 | deletes a trashed entry now: chunks and stored object go |
| GET | `/healthz` | 200 | liveness and readiness probe: core's `Health`, `{"status": "ok", "version", "commit"}` from `APP_VERSION`/`APP_COMMIT` (`"unknown"` when unset) |
| GET | `/admin/stats` | 200 | admins only (403 otherwise): counts over all users, see below |
| GET | `/admin/stats/daily?days=30` | 200 | admins only: library sources created per day, see below |

A source is `{"id", "notebook_id", "name", "kind", "status", "error",
"created_at", "library_id"}`; name, kind, status and error are the
library source's. A library entry is

```json
{"id": "…", "name": "notes.txt", "kind": "text", "status": "ready", "error": null,
 "size_bytes": 2048, "url": null, "created_at": "…",
 "notebooks": [{"id": "…", "title": "Thesis", "source_id": "…"}]}
```

`size_bytes` is null for URLs, `url` is set only for them; an entry in
no notebook has `"notebooks": []`.

A trash entry is the same without `notebooks`, plus `deleted_at` and
`purge_at`:

```json
{"id": "…", "name": "notes.txt", "kind": "text", "status": "ready", "error": null,
 "size_bytes": 2048, "url": null, "created_at": "…",
 "deleted_at": "2026-10-13T18:00:00Z", "purge_at": "2026-10-27T18:00:00Z"}
```

`purge_at` is `deleted_at` plus the owner's `trash_days` (account's
`users.preferences ->> 'trash_days'`, read directly at query time; absent,
null or no user row means 14). Every worker purges expired entries at
start and then once an hour (`PURGE_EVERY_SECONDS`): rows first, then
their objects. A trashed entry is not processed, cannot be added to a
notebook (404) and is not in `GET /library`; uploading its bytes or URL
again restores it and links it, without processing it again.

`GET /admin/stats` answers

```json
{"sources": {"processing": 3, "ready": 120, "failed": 4},
 "jobs": {"pending": 1, "running": 2, "failed": 4},
 "chunks": 5821,
 "source_bytes": 73400320}
```

`sources` counts library sources (not generated ones) by status. `jobs` splits the `processing` rows:
`pending` waits for a worker (unclaimed, or its claim is older than
`CLAIM_TIMEOUT_SECONDS`), `running` is claimed by a worker; `failed` is
the failed ones. `source_bytes` sums `library_sources.size_bytes`; rows
created before migration 0002 have no size and count 0. One read-only query.

`GET /admin/stats/daily?days=N` (1–365, default 30) answers one entry
per UTC day for the last N days including today, oldest first, days
without sources included:

```json
{"days": [{"day": "2026-10-13", "sources_created": 3,
           "by_kind": {"pdf": 1, "text": 0, "url": 1, "image": 1}, "failed": 1}]}
```

It counts library sources by their creation day (generated ones
excluded); `failed` is how many of that day's are failed now. One
read-only query.

Errors are `{"error": "<message>"}`: 400 bad upload, 401 token, 402
credit exhausted, 403 admin only, 404 not yours or missing, 413 too large, 415
unsupported type, 422 invalid body.

## Processing

`POST /sources` first looks for the same library source of the caller:
`sha256:<hex>` of the uploaded bytes, or `url:<normalised URL>` (scheme
and host lowercased, default port and fragment dropped, path and query
kept). Found, it only links it into the notebook — nothing is stored or
processed again, and a failed one is put back into the queue, since
uploading again is how a user retries. Not found, it checks the caller's
credit, uploads the file to the bucket at `<owner>/<library_id>/<name>`
(objects from before migration 0003 keep their
`<notebook_id>/<source_id>/<name>` keys), and only then writes the library
source with `status: processing`, links it and returns. The order matters:
a `processing` row is claimable the moment it exists, so a worker must
never find one whose object is not there yet (v0.7.1 did, and failed with
`NoSuchKey`). A failed upload answers 503 and leaves no row; when a
concurrent upload of the same bytes inserted its row first, this one is
linked to it and its own object is deleted. For a URL the stored object is the URL itself
(`<owner>/<library_id>/url`) and the name is the URL; the API opens no
connection to it. The library source is now in the queue: the queue is
the `library_sources` table, a `processing` row that no worker holds;
generated rows are rag's and never claimed. Worker processes (`lasteverlm-ingest-worker`, any number
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
`library_sources.summary` for the output generators, and sets `ready`.
Usage rows name the notebook the library source was first added to. A failure
that a retry cannot change (unreadable file, no text, credit exhausted)
sets `failed` at once. A failure that may pass next time (object
storage, the embedding or summary request, an unexpected error) leaves
the row `processing` with the error text and releases the claim with a
backoff (`retry_at`, migration 0008): no worker takes it for 5 seconds
after the first failure and 15 after the second, so the next attempt
follows promptly instead of after the claim timeout; the third failed
attempt sets `failed` for good. The user sees the `error` either way. Credit is checked
with core's `has_credit` before the upload is stored, before an image is
read, before the embedding call and before the summary call; an admin
always has credit, anyone else needs a positive balance. The API pods never process
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
image loader is a `ModelLoader`: the worker checks the credit before it,
and the loader hands the call's usage to the worker's `bill` callback as
soon as it returns, which records a `usage` row of kind `llm` before the
embedding and summary rows and stops the source when the credit is gone. The text is then chunked, embedded and summarized like any
other source. A model refusing the image (HTTP 400) fails the source at
once, and so does an empty answer (a blank image: "the image holds no
readable content"), whose call is still recorded as usage; other
provider errors are retried. `IMAGE_MAX_TOKENS` (2000) caps
the answer.

## PDF capture modes

A PDF upload carries `capture` (multipart field next to `file`): `text`
reads the text layer (pypdf), `vision` has the vision model read every
page, `auto` (the default; web sends the user's `pdf_capture` preference
explicitly) reads the text layer and has the model read only the pages
without one — a page counts as text when its layer has at least 20
visible characters. Any other value is 400; the field is ignored for
other kinds and in the JSON forms (a PDF behind a URL is read by its
text layer). The mode is stored on the library source (`capture`, null
for non-PDFs) and returned in sources, library and trash entries. The
same bytes captured in two modes are two library sources: the dedupe key
of a PDF is `sha256:<hex>:<capture>`; PDFs from before migration 0006
are `text`.

Pages for the model are rendered with pypdfium2 at 150 dpi, long edge at
most 2000 px (A4: 1241 × 1754), as JPEG, one at a time (pdfium is not
thread-safe); up to four model calls run at once. Each call is
`LLM_MODEL` with the page and a transcription prompt, billed as it
returns like an image; every answered call is billed even when another
page of the batch fails, and the credit is checked before the next
batch. Page numbers stay with their text for citations; a page the model
finds empty is skipped. Cost: `vision` is one model call per page, `auto`
only pays for the pages without a text layer; measured on two scanned
A4 pages, about 515 input and 960 output tokens per page, 5 s for both.
Transcription of a scan is good but not perfect (a running header was
misread in the measurement), the text layer is exact where one exists,
which is why `auto` prefers it.

Failures name the mode: a PDF without any text in `text` mode fails
with a hint to upload it with `auto` or `vision`; a PDF whose pages all
come back empty fails with "PDF holds no readable content (capture mode
…)"; more than `PDF_VISION_MAX_PAGES` (100) pages for the model fail
before any call; `vision` or `auto` without a vision model configured
fail with "capture mode … needs a vision model".

## Demo library

Every new user finds four demo sources in their library, one per kind,
forming one fictional set around Zeltavia (the country of the smoke
test) so that questions across sources work:

| Source | Kind | What it is |
|---|---|---|
| `field-notes-1893.pdf` | pdf (capture `text`) | three pages of an 1893 survey diary: Marrow Bay, the river Quill, a fog crossed by dead reckoning, the Saltglass Reef |
| `zeltavian-glossary.md` | text | words and customs that the field notes use (brennet, smokra, the Knelling, …) |
| `marrow-bay-map.png` | image | a map of the places in both, with labels the vision model transcribes |
| https://en.wikipedia.org/wiki/Dead_reckoning | url | the real navigation method the diary describes |

`seeds.ensure_seeded` runs on the owner's first `GET /library` or first
upload. `library_seeds` (migration 0007) marks every owner it has looked
at, so it seeds at most once; an owner who already has library sources
is marked and not seeded, and deleting everything never brings the demo
back. The demo user itself is never seeded. The sources are ordinary
library sources with `demo: true` (shown in sources, library and trash
entries), stored per owner like an upload and processed by the worker.
Their processing does not check the owner's credit and its usage rows
go to the demo user (`DEMO_USER_ID`) as the sponsor: a new user starts
with no credit. Uploading a demo file again links the demo source, like
any duplicate. `SEED_DEMO_LIBRARY=false` turns seeding off.

The PDF and the map are generated from `src/lasteverlm_ingest/demo/`
by `demo/build.py` (a small PDF writer with Helvetica and real page
breaks, and Pillow for the map, under 30 KB) and committed; run it only
after changing the sources. Measured: the vision model transcribes all
fifteen labels of the map in one call (537 input, 119 output tokens);
the call returned the labels without a description of the map.

## Running the container locally

```bash
make build
docker run --rm -p 8000:8000 --env-file .env lasteverlm-ingest:$(git rev-parse --short HEAD)
```
