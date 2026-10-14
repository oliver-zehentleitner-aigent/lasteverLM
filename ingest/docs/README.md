# Operating lasteverLM-ingest

Endpoints, processing and the database in detail. Configuration, run,
test, build and deploy are in the [README](../README.md); why it is
built this way is in [`../context/`](../context/index.md); the API it
implements is the ingest section of the family's
[architecture](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/docs/architecture.md).

## Database

The service owns `notebooks`, `library_sources`, `sources` and `chunks`.
A library source is what a user uploaded or entered once (a file, an
image, a recording, a URL), owned by that user, processed once; its chunks hang on it
(`chunks.library_source_id`). A source is the link of a library source
into a notebook (`sources.library_source_id`, unique per notebook); its
id is the public source id. Library sources of kind `generated` are
written by the rag service when it indexes a finished output: owned by
the user, linked into the notebook the output was made in, and rag's for
their whole life (trash, restore, purge). This service never loads them,
keeps them out of the uploads library and its trash, lists the ready
ones on their own (`GET /library?kind=generated`) and links them into
any of the owner's notebooks like an upload; detaching or deleting a
notebook removes only links, never the output.
The migrations are
[`db/migrations/0001_ingest.sql`](../db/migrations/0001_ingest.sql),
[`0002_source_size.sql`](../db/migrations/0002_source_size.sql)
(the stored object's size) and
[`0003_source_library.sql`](../db/migrations/0003_source_library.sql)
(the library; the expand step: every existing source got a library
source with the same id, the old columns on `sources` and `chunks` stayed
nullable for the rolling deploy) and
[`0004_source_library_contract.sql`](../db/migrations/0004_source_library_contract.sql)
(the contract step, one release later: drops those columns and makes
`library_source_id` not null; added after 0005–0009, which the runner
allows since it records each file by name), plain SQL for psql, applied by infra's `make migrate` after infra's extensions
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
| GET | `/notebooks` | 200 | the caller's notebooks, `{"id", "title", "created_at", "share_token"}` (`share_token` null when not shared) |
| POST | `/notebooks` | 201 | `{"title"}` |
| PATCH | `/notebooks/{id}` | 200 | `{"title"}`: rename, trimmed, 1–200 characters like at creation (400 otherwise); the notebook |
| POST | `/notebooks/{id}/share` | 200 | `{"share_token"}`: a read-only link (`notebooks.share_token`, `secrets.token_urlsafe(24)` like rag's output links), the same token on every call until revoked. Rag's public view shows the title, the sources' names and kinds and the shared outputs, never the source files |
| DELETE | `/notebooks/{id}/share` | 204 | revokes the link; sharing again makes a new token |
| DELETE | `/notebooks/{id}` | 204 | detaches its sources (they stay in the library, outputs included; rag keeps an output's origin title) |
| GET | `/notebooks/{id}/sources` | 200 | poll this for `status` |
| POST | `/notebooks/{id}/sources/bulk` | 200 | `{"library_ids": [...]}` (1–200): links the caller's library entries into their notebook at once, uploads (any status, not trashed) and ready outputs alike; nothing is processed or billed. Answers `{"added": [library_id], "already": [library_id]}` in the order given (duplicates counted once); an existing link is `already`, never doubled (unique `sources_link_idx`). One transaction: if any id is unknown, someone else's, trashed or an unfinished output, nothing is added and the answer is 404 naming them |
| POST | `/notebooks/{id}/sources` | 202 / 200 | multipart `file` (PDF, `.txt`, `.md`, PNG, JPEG, WebP, GIF) with an optional field `capture` for PDFs (`text`, `vision`, `auto`; default `auto`), JSON `{"url"}` (`http`/`https`, no credentials in the URL), or JSON `{"library_id"}` (add from the library: an upload not in the trash, or a ready output; nothing is processed or billed, the chunks are reused; 404 otherwise); 200 with the existing source when it is already in this notebook |
| DELETE | `/sources/{id}` | 204 | detach: removes the source from this notebook, it stays in the library |
| GET | `/library` | 200 | the caller's library (uploads), newest first, with where-used |
| GET | `/library?kind=all` | 200 | uploads and ready outputs in one list, newest first; every entry has `notebooks` (the notebooks it is linked into, so the web can tell whether it is in a given one), outputs also `origin` and `output_id` |
| GET | `/library?kind=generated` | 200 | the caller's ready outputs (rag's, not trashed), newest first, with where-used, `output_id` (the output in rag) and `origin`: `{"id", "title"}` of the notebook it was made in, read from rag's `outputs` (`id` null once that notebook is deleted, `title` then rag's snapshot); `preview_url` null |
| GET | `/library/{id}` | 200 | one library source |
| DELETE | `/library/{id}` | 204 | to the trash: removed from every notebook, chunks and stored object kept |
| GET | `/library/trash` | 200 | the caller's trash, most recently deleted first |
| POST | `/library/{id}/restore` | 204 | back from the trash into the library, in no notebook |
| DELETE | `/library/{id}/purge` | 204 | deletes a trashed entry now: chunks and stored object go |
| GET | `/healthz` | 200 | liveness and readiness probe: core's `Health`, `{"status": "ok", "version", "commit", "dependencies": {"postgres", "storage", "inference"}}`; version and commit from `APP_VERSION`/`APP_COMMIT` (`"unknown"` when unset), each dependency `"ok"` or `"down"` from core's `DependencyProbe` (a pooled connection, a bucket HEAD, `GET /models`; 2 s each, cached 15 s). `status` stays `"ok"` while a dependency is down, so the probe never restarts a pod over it |
| GET | `/estimate?kind=text\|url\|pdf_text\|pdf_vision\|image\|audio` | 200 | any bearer (account's price list calls it server-side and publishes only the charge): `{"kind", "unit", "action", "cost_cents", "charge_cents", "per_source_charge_cents", "nominal": [{"model", "tokens_in", "tokens_out"}]}`, euro cents through core's billing at the current pricing rules; 503 without an exchange rate. Nominal units below |
| GET | `/admin/stats` | 200 | viewers and admins (core's `admin_read`; 403 `admin only` otherwise): counts over all users, see below |
| GET | `/admin/stats/daily?days=30` | 200 | viewers and admins: library sources created per day, see below |
| DELETE | `/admin/users/{id}` | 204 | admins only (viewers 403): everything the user owns in ingest. The stored objects of their library (trash and converted recordings included) are deleted first, then their library rows (generated ones too, chunks cascade), notebooks (links and rag's rows cascade) and seed mark in one transaction. A storage failure is 503 `{"error"}` naming the count and the first key, with every row kept for a retry. Idempotent: 204 also when nothing is left or the user never existed. Account calls it, with the admin's bearer, after rag's purge and before deleting the user |

A source is `{"id", "notebook_id", "name", "kind", "status", "error",
"created_at", "library_id", "capture", "demo", "preview_url", "original_url"}`; name,
kind, status, error, capture and demo are the library source's. A
library entry is

```json
{"id": "…", "name": "notes.txt", "kind": "text", "status": "ready", "error": null,
 "size_bytes": 2048, "url": null, "created_at": "…", "capture": null, "demo": false,
 "preview_url": null, "original_url": null,
 "notebooks": [{"id": "…", "title": "Thesis", "source_id": "…"}]}
```

`size_bytes` is null for URLs, `url` is set only for them; an entry in
no notebook has `"notebooks": []`. `capture` is set for PDFs only (see
PDF capture modes), `demo` marks the demo library. `preview_url` is where
the frontend opens the source without the bearer token: for an image, a
PDF, a text or a recording a presigned GET of the stored object, inline,
valid for one hour and signed anew on every listing (the object carries
its type, so an image shows in an `<img>`, a PDF in the browser's viewer,
a text as `text/plain; charset=utf-8`, a recording plays in an
`<audio>`); for a recording that was converted (see Audio sources) it is
the converted MP3, the file that was transcribed; for a URL source the
URL itself; `null` for generated rows. `original_url` is set only for a
converted recording: the uploaded original, presigned for one hour as a
download (`Content-Disposition: attachment` with the file name, since a
cross-origin link cannot ask for that itself); `null` everywhere else,
including a recording whose conversion has not run yet. `size_bytes` is
always the original's. Sources, library and trash entries all carry
both. The object keys themselves are never returned.

A trash entry is the same without `notebooks`, plus `deleted_at` and
`purge_at`:

```json
{"id": "…", "name": "notes.txt", "kind": "text", "status": "ready", "error": null,
 "size_bytes": 2048, "url": null, "created_at": "…", "capture": null, "demo": false,
 "preview_url": null, "original_url": null, "deleted_at": "2026-10-13T18:00:00Z", "purge_at": "2026-10-27T18:00:00Z"}
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
 "jobs": {"pending": 1, "running": 2, "waiting_for_credit": 0, "failed": 4},
 "chunks": 5821,
 "source_bytes": 73400320}
```

`sources` counts library sources (not generated ones) by status. `jobs` splits the `processing` rows:
`pending` waits for a worker (unclaimed, or its claim is older than
`CLAIM_TIMEOUT_SECONDS`) and its owner has credit, `waiting_for_credit`
waits for its owner's credit (no worker takes it), `running` is claimed
by a worker; `failed` is
the failed ones. `source_bytes` sums `library_sources.size_bytes`; rows
created before migration 0002 have no size and count 0. One read-only query.

`GET /admin/stats/daily?days=N` (1–365, default 30) answers one entry
per UTC day for the last N days including today, oldest first, days
without sources included:

```json
{"days": [{"day": "2026-10-13", "sources_created": 3,
           "by_kind": {"pdf": 1, "text": 0, "url": 1, "image": 1, "audio": 0}, "failed": 1}]}
```

It counts library sources by their creation day (generated ones
excluded); `failed` is how many of that day's are failed now. One
read-only query.

Errors are `{"error": "<message>"}`: 400 bad upload, 401 token, 403 admin only, 404 not yours or missing, 413 too large, 415
unsupported type, 422 invalid body.

### Nominal units of `GET /estimate`

What one unit is priced as (constants in `api/estimate.py`, measured on
the demo set and the live vision runs, deliberately round):

| kind | unit | model calls |
|---|---|---|
| `text`, `pdf_text` | page | 500 embedding tokens (about 2,000 characters of prose) |
| `url` | web page | 6,000 embedding tokens (the demo article, 24,348 characters as text) |
| `pdf_vision` | page | `LLM_MODEL` 515 in / 960 out (measured on scanned A4), then 960 embedding tokens |
| `image` | image | `LLM_MODEL` 540 in / 500 out, then 500 embedding tokens |
| `audio` | minute | `STT_MODEL` 60 seconds, then 200 embedding tokens |

Once per source on top (`per_source_charge_cents`): the summary call at
its largest input (6,000 in, 300 out) and the action's fixed fee.

## Processing

`POST /sources` first looks for the same library source of the caller:
`sha256:<hex>` of the uploaded bytes, or `url:<normalised URL>` (scheme
and host lowercased, default port and fragment dropped, path and query
kept). Found, it only links it into the notebook — nothing is stored or
processed again, and a failed one is put back into the queue, since
uploading again is how a user retries. Not found, it uploads the file
to the bucket at `<owner>/<library_id>/<name>`
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
`claimed_by`; the job moves `claimed_at` to now with every answered
model call (an image, a PDF page, a transcription) and every embedding batch, and a claim
not moved for `CLAIM_TIMEOUT_SECONDS` is treated as abandoned and taken
over, unless the row has had three attempts: then
the claim fails it ("processing did not finish in 3 attempts"), so a
source that kills or hangs its worker does not take every worker in
turn. An idle worker polls every
`WORKER_POLL_SECONDS`. The pipeline
(`lasteverlm_ingest.worker.process_source`) loads the file from the
bucket, parses it, chunks it, embeds the chunks in batches, writes them
and records one `usage` row of kind `embedding`. It then asks the
language model for a one-paragraph summary in the language of the
source (the first `SUMMARY_INPUT_TOKENS` tokens go into the prompt),
records a second `usage` row of kind `llm`, stores the summary in
`library_sources.summary` for the output generators, and sets `ready`.
Usage rows name the notebook the library source was first added to.
Every row is booked through core's `record_usage`, which computes the
cost from `MODEL_PRICES` and the charge from account's pricing rules:
all model calls of processing one source (vision pages, the
transcription, the embeddings, the summary) are one action,
`source:<kind>` (`demo_seed` for the sponsored demo sources), with the
library source's id as `action_id`, retries included. Before every model
call the worker also checks that the pricing rules (account's settings
row, cached 30 s) carry an exchange rate: without one a call could be
paid upstream but not booked, so no worker claims a source while the
rate is missing, and a job that finds it gone goes back to the queue
before its next provider call (attempt not counted), like a source
waiting for credit. Queued sources then show `error` "pricing has no
exchange rate, ask an admin" (derived, never stored); once an admin sets
the rate they run, without a re-upload. A failure
that a retry cannot change (unreadable file, no text) sets `failed` at
once. A failure that may pass next time (object
storage, the embedding or summary request, an unexpected error) leaves
the row `processing` with the error text and releases the claim with a
backoff (`retry_at`, migration 0008): no worker takes it for 5 seconds
after the first failure and 15 after the second, so the next attempt
follows promptly instead of after the claim timeout; the third failed
attempt sets `failed` for good. The user sees the `error` either way.

Adding a source never needs credit; processing does. Every user needs a
positive balance, admins included (core's rule); the demo seeds are
sponsored. The claim query takes a row only when its owner's balance
(ledger minus usage, in the same SQL) is positive, so a source added
without credit stays `processing` in the table, unclaimed and with no
attempt counted, and the API shows it as `waiting_for_credit` in
sources and library entries (never stored; core's `SourceStatus`). The
moment the owner has credit again the next claim takes it: no hook on
account's ledger, no periodic pass. The worker also checks credit before
every model call (an image, a PDF page, a transcription, the
embeddings, the summary); when it has run out, the source goes back to
the queue the same way (claim released, attempt not counted, error
cleared) instead of failing, and the work done so far is redone when it
resumes. The API pods never process
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
the whole fetch at 30 seconds, the DNS lookup included (it runs in a
small thread pool, since the resolver has no timeout of its own; a lookup
that does not answer in time is a transient failure).

A 4xx answer, a blocked address, an unsupported type or a body over the
cap fail the source at once; a timeout, a refused connection, 429 or
5xx are retried like any other transient failure.

A provider error that core marks `permanent` (a 4xx other than 408, 409
and 429: the platform refused the request, a retry sends the same one)
fails the source at once, for every model call; every other provider
error is retried.

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
embedding and summary rows and puts the source back to wait when the credit is gone. The text is then chunked, embedded and summarized like any
other source. A model refusing the image (HTTP 400) fails the source at
once, and so does an empty answer (a blank image: "the image holds no
readable content"), whose call is still recorded as usage; other
provider errors are retried. `IMAGE_MAX_TOKENS` (2000) caps
the answer.

## Audio sources

An upload named `.mp3`, `.wav`, `.m4a`, `.mp4`, `.aac`, `.ogg`, `.oga`,
`.opus`, `.flac` or `.webm` (or sent with one of their `audio/*` types,
`video/mp4` or `video/webm`) is an audio source, capped at
`MAX_AUDIO_UPLOAD_BYTES` (60 MiB, below the ingress body limit) instead
of `MAX_UPLOAD_BYTES`. The API reads the format from the first bytes:
an MP4/M4A (`ftyp`), ADTS AAC, Ogg (Vorbis or Opus), FLAC or
WebM/Matroska container is stored as `audio/mp4`, `audio/aac`,
`audio/ogg`, `audio/flac` or `audio/webm`, and a WAV over the
transcription model's 25 MiB as `audio/wav` (both are converted, see
below); anything else goes through core's `probe_audio`, which accepts a
WAV within the limits and an MP3 within 25 MiB and four hours and stores
them as `audio/wav` or `audio/mpeg`. Bytes that are none of these get 415 with the reason and
the accepted list. Audio is deduplicated by the sha256 of the original's
bytes like every file.

The platform's transcription model takes WAV and MP3 only, at most
25 MiB. The worker transcribes every MP3 and a WAV within the cap as
uploaded; a WAV over the cap and every other container it converts first
with ffmpeg into mono 16 kHz MP3 at 32 kbit/s from the first audio track
(a video's audio track included). ffmpeg runs as a subprocess with the
demuxer forced from the sniffed bytes and only the `file` protocol, in a
private directory under `/tmp`, for at most 300 s; a failure fails the
source at once with ffmpeg's last line of output. The format does not
change the cost (transcription is billed per second of audio), only
whether a recording fits the cap: a 44.1 kHz stereo WAV reaches 25 MiB
after about 2.5 minutes, the 32 kbit/s MP3 after about two hours. The converted MP3 is
stored beside the original (`<owner>/<library_id>/_transcribed.mp3`,
`library_sources.transcribed_path`, migration 0010) and is what is
transcribed: core's limits apply to it, not to the original, and a retry
reuses it instead of converting again. Deleting the entry from the trash
removes both objects. The image's ffmpeg is a minimal build (see the
Dockerfile): only the demuxers, decoders and the resampler these formats
need, and the MP3 encoder.

The worker sends the MP3 or WAV to `STT_MODEL` (core's default
`whisper-large-v3-turbo`, priced in `MODEL_PRICES` per million seconds)
in one call. The loader is a `ModelLoader` like the image loader: the
credit is checked before the call, its usage (kind `stt`, the seconds the
platform billed) is recorded the moment it returns, the claim is
refreshed (also after a conversion). The call has its own client: one
attempt, at most `STT_TIMEOUT_SECONDS` (300), which must stay below
`CLAIM_TIMEOUT_SECONDS` so no other worker takes the job over while the
call runs. The platform returns plain text without timestamps, so a
recording becomes one passage without a page number, chunked, embedded
and summarized like a text file; a citation names the recording, not a
position in it. An answer the platform billed but that cannot be used (no
speech recognised, no duration reported) is recorded as usage and fails
the source at once with core's message. A registry built without a
transcriber (tests) has no `audio` loader, and audio uploads then get 415.

## PDF capture modes

A PDF upload carries `capture` (multipart field next to `file`): `text`
reads the text layer (pypdf), `vision` has the vision model read every
page, `auto` (the default; web sends the user's `pdf_capture` preference
explicitly) reads the text layer and has the model read only the pages
without one — a page counts as text when its layer has at least 20
visible characters and at least 60 % of them are letters (a font
without a usable ToUnicode map yields glyph codes like `&MM,:N K OP`,
which `auto` sends to the model and `text` skips). Any other value is 400; the field is ignored for
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
before any call; a PDF of more than 2000 pages fails in every mode,
also behind a URL ("PDF has N pages; at most 2000 are read",
`loaders/pdf.py`, `MAX_PAGES`), before any page is read; `vision` or `auto` without a vision model configured
fail with "capture mode … needs a vision model".

## Demo library

Every new user finds five demo sources in their library, one per kind,
forming one fictional set around Zeltavia (the country of the smoke
test) so that questions across sources work:

| Source | Kind | What it is |
|---|---|---|
| `field-notes-1893.pdf` | pdf (capture `text`) | three pages of an 1893 survey diary: Marrow Bay, the river Quill, a fog crossed by dead reckoning, the Saltglass Reef |
| `zeltavian-glossary.md` | text | words and customs that the field notes use (brennet, smokra, the Knelling, …) |
| `marrow-bay-map.png` | image | a map of the places in both, with labels the vision model transcribes |
| https://en.wikipedia.org/wiki/Dead_reckoning | url | the real navigation method the diary describes |
| `hollin-interview.mp3` | audio | an 80-second radio interview (two voices) with the keeper of Hollin Lighthouse: the lamp's history, the fog signal Old Grumble, the Strand ledger naming the expedition's ship, Puffin Sunday. None of these facts is in the other four, so a question about them is answered from the transcript |

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
after changing the sources. The recording is made once from its script
(`hollin-interview.txt`) by `demo/build_audio.py` with the platform's
speech model (voices serena and ryan, joined and re-encoded by ffmpeg to
mono 64 kbit/s, 637 KB) and committed; unlike `build.py` it is not
deterministic and costs a few cents, so it runs only when the script
changes. Its transcript comes from the normal pipeline when the seed is
processed. Owners seeded before the recording was added do not get it:
seeding happens once per owner, and the demo reset gives them the new
set. Measured: the vision model transcribes all
fifteen labels of the map in one call (537 input, 119 output tokens);
the call returned the labels without a description of the map.

## Running the container locally

```bash
make build
docker run --rm -p 8000:8000 --env-file .env lasteverlm-ingest:$(git rev-parse --short HEAD)
```
