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
| GET | `/notebooks` | 200 | the caller's notebooks, `{"id", "title", "created_at", "share_token", "starter"}` (`share_token` null when not shared; `starter` true for a notebook made as a copy of the starter) |
| POST | `/notebooks` | 201 | `{"title"}` |
| POST | `/starter/copy?force=true` | 201 | a fresh copy of the starter notebook for the caller, the new notebook as in `GET /notebooks` (see Starter notebook); 409 `starter_exists` without `force` while the caller has a starter notebook, 429 `{"error": "starter_copy_too_soon", "retry_after"}` (and `Retry-After`) within an hour of the last such copy, 404 `no_starter` without a starter, 503 on a storage failure |
| PATCH | `/notebooks/{id}` | 200 | `{"title"}`: rename, trimmed, 1–200 characters like at creation (400 otherwise); the notebook |
| POST | `/notebooks/{id}/share` | 200 | `{"share_token"}`: a read-only link (`notebooks.share_token`, `secrets.token_urlsafe(24)` like rag's output links), the same token on every call until revoked. Rag's public view shows the title, the sources' names and kinds and the shared outputs, never the source files |
| DELETE | `/notebooks/{id}/share` | 204 | revokes the link; sharing again makes a new token |
| DELETE | `/notebooks/{id}` | 204 | detaches its sources (they stay in the library, outputs included; rag keeps an output's origin title) |
| GET | `/notebooks/{id}/sources` | 200 | poll this for `status` |
| POST | `/sources/{id}/refetch` | 202 | fetch a web page again (owner, the link id): `{"library_id", "version", "fetched_at"}`. A read page goes to `processing` until a worker has compared it: unchanged, `fetched_at` moves and nothing is charged; changed, a new version (`version + 1`) takes the links and is read and charged as a web page. An unread or failed page is simply read. 409 for any other source (not a web page, being read, an older version) |
| POST | `/sources/process` | 200 | `{"library_ids": [...]}` (1–200): read the caller's unread sources now. `added` entries move to `processing` (`"queued"`), entries being read, read or failed stay as they are (`"unchanged"`): `{"queued": [library_id], "unchanged": [library_id]}`. Nothing is billed here (the worker bills the reading); without credit the queued ones show `waiting_for_credit`. One transaction: 404 naming any id that is not the caller's (unknown, someone else's, trashed). Called by rag before an answer or an output and by the web's "read now" |
| POST | `/sources/estimate` | 200 | `{"library_ids": [...], "refetch": [...]}`: what reading them would charge, `{"items": [{"library_id", "kind", "unread", "charge_cents_min", "charge_cents_max", "basis"}]}` in euro cents (decimal strings). Unread entries from their stored size, page count (PDFs) or duration (MP3/WAV), a range where those are unknown (a web page before its fetch, an older PDF, a recording to convert); read ones 0 ("read already"), unless in `refetch` ("re-read if changed": 0 to one web page). Each includes the summary and the fixed fee. 404 naming ids not the caller's, 503 without an exchange rate |
| POST | `/notebooks/{id}/sources/bulk` | 200 | `{"library_ids": [...]}` (1–200): links the caller's library entries into their notebook at once, uploads (any status, not trashed) and ready outputs alike; nothing is processed or billed. Answers `{"added": [library_id], "already": [library_id]}` in the order given (duplicates counted once); an existing link is `already`, never doubled (unique `sources_link_idx`). One transaction: if any id is unknown, someone else's, trashed or an unfinished output, nothing is added and the answer is 404 naming them |
| POST | `/notebooks/{id}/sources` | 202 / 200 | multipart `file` (PDF, `.txt`, `.md`, PNG, JPEG, WebP, GIF) with an optional field `capture` for PDFs (`text`, `vision`, `auto`; default `auto`), JSON `{"url"}` (`http`/`https`, no credentials in the URL), or JSON `{"library_id"}` (add from the library: an upload not in the trash, or a ready output; nothing is processed or billed, the chunks are reused; 404 otherwise); 200 with the existing source when it is already in this notebook |
| GET | `/sources/{id}/text` | 200 | the stored file of a text or Markdown source, read or not, as `text/plain; charset=utf-8` (decoded as the text loader decodes it: UTF-8, else Latin-1), for the viewer's "Original" view; owner only (404 otherwise), 415 for other kinds, 413 above 2 MiB |
| GET | `/sources/{id}/chunks?offset=0&limit=50` | 200 | the "As read" view, owner only (404 otherwise): `{"source_id", "library_id", "kind", "capture", "read_by", "chunk_count", "offset", "chunks": [{"chunk_id", "index", "page", "text", "vision"}]}`, in order of `index` (`chunks.idx`, a citation's `chunk_index`; `chunk_id` is a citation's `chunk_id`); `limit` 1–200; `page` for PDFs, null otherwise; audio chunks carry no position (no timestamps from the platform); `read_by` as on a source; `vision` is true for every chunk of an image and for a PDF chunk that starts on a page the vision model read (the page its citation names) |
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
"created_at", "library_id", "capture", "starter", "version", "fetched_at", "final_url", "checked_at", "snapshot_url", "preview_url", "original_url", "read_by"}`; name,
kind, status, error, capture and starter are the library source's.
`read_by` names the models that made the source's text,
`{"vision": "<model>" | null, "stt": "<model>" | null}`: `vision` for an
image or a PDF whose pages the vision model read, `stt` for a recording.
It is `null` when no model made the text (plain text, a PDF read by its
text layer only, a web page), for a source not read yet, and for sources
read before it was recorded (migration 0018). A library entry is

```json
{"id": "…", "name": "notes.txt", "kind": "text", "status": "ready", "error": null,
 "size_bytes": 2048, "url": null, "created_at": "…", "capture": null, "starter": false,
 "preview_url": null, "original_url": null,
 "notebooks": [{"id": "…", "title": "Thesis", "source_id": "…"}]}
```

`size_bytes` is null for URLs, `url` is set only for them; an entry in
no notebook has `"notebooks": []`. `capture` is set for PDFs only (see
PDF capture modes), `starter` marks a copy from the starter notebook. `preview_url` is where
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
 "size_bytes": 2048, "url": null, "created_at": "…", "capture": null, "starter": false,
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
the former Zeltavia demo set and the live vision runs, deliberately round):

| kind | unit | model calls |
|---|---|---|
| `text`, `pdf_text` | page | 500 embedding tokens (about 2,000 characters of prose) |
| `url` | web page | 6,000 embedding tokens (the former demo article, 24,348 characters as text) |
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
`source:<kind>`, with the
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

Adding a source only stores it: a new upload, URL or text is `added`
(not read yet), and no worker claims it until it is used, when rag (before
an answer or an output) or the web ("read now") calls `POST
/sources/process`, which moves it to `processing`. Uploading a failed
source again puts it back to `added`. The upload stores what the cost of
reading depends on: the page count of a PDF and the length of an MP3 or
WAV (migration 0014), for `POST /sources/estimate`.

Adding a source never needs credit; processing does. Every user needs a
positive balance, admins included (core's rule). The claim query takes a row only when its owner's balance
(ledger minus usage, in the same SQL) is positive, so a source added
without credit stays `processing` in the table, unclaimed and with no
attempt counted, and the API shows it as `waiting_for_credit` in
sources and library entries (never stored; core's `SourceStatus`). The
moment the owner has credit again the next claim takes it: no hook on
account's ledger, no periodic pass. An action starts only if the balance
covers its estimated maximum plus what the owner's started work holds;
once started it runs to the end and books every call,
even below zero, so a source is never left half read and half paid.

- **Funded at request:** when `POST /sources/process` or a refetch queues
  a read, ingest stores its estimated maximum (`funded_cents`, from the
  same estimate as `POST /sources/estimate`). If the balance covers that
  plus what the owner's started work holds, it marks the
  row `funded_request_at`. The claim takes such a row whatever the
  balance is by then.
- **Not funded:** an unmarked row is claimed once the balance, less what
  started work holds, covers its estimate; until then it shows
  `waiting_for_credit`.
- **Release:** both columns clear when the read ends, ready or failed
  (migration 0017).

- **Held:** started work is the owner's funded rows (`processing`, not
  trashed), rag's outputs that are `waiting` or `processing` and not
  trashed (`outputs.reserved_cents`, rag's migration 0016), and the
  estimated maximum of every `explain_output` step still `waiting` or
  `running` in a running agent plan (`plans.steps`).

Rag computes the same sum for its own start check. The API pods never process
anything, so they stay stateless and the workers scale on their own. A
worker finishes the source in flight before it stops on SIGTERM.

## URL sources

The worker fetches the URL (`lasteverlm_ingest.loaders.url`) and hands
the body to the loader for its content type: `text/html` and
`application/xhtml+xml` to the HTML extractor, `application/pdf` to the
PDF loader, `text/plain` and `text/markdown` to the text loader, and
structured data to `lasteverlm_ingest.loaders.structured`; any other type
fails the source with a message naming the type and the supported list.
The HTML extractor drops scripts, styles and page chrome (`nav`,
`header`, `footer`, `aside`, forms), keeps only `<main>`/`<article>`
when the page has them, and puts the page title first.

Structured data becomes lines that carry their own context, so a chunk
cites well wherever the chunker cuts:

| Format | Content types | Rendering |
|--------|---------------|-----------|
| JSON | `application/json`, `text/json`, any `+json` | one line per value with its key path (`languages.Python: 12345`, `items[0].name: …`) |
| NDJSON | `application/x-ndjson`, `application/ndjson`, `application/jsonl`, `application/x-jsonlines` | as JSON, each line numbered (`[3].id: …`) |
| YAML | `application/yaml`, `text/yaml`, `application/x-yaml`, `text/x-yaml` | as JSON; parsed with `safe_load` only |
| XML | `application/xml`, `text/xml`, any `+xml` (RSS, Atom) | one line per element text and attribute with its path (`rss/channel/item[2]/title: …`, `feed/entry/link@href: …`); namespaces dropped from names |
| CSV, TSV | `text/csv` (comma, or the semicolon, tab or pipe the first lines use), `text/tab-separated-values` | one line per row, every value named by its column (`row 3: city: Graz; price: 12`); the first row is the header |

One object, element or row is one passage, so its values stay together
and apart from the next record.

The rendering is a contract: rag's number check reads chunk text and must
tell a value from an index, so a change here is announced to rag first.

- A CSV or TSV line starts with `row <n>: ` (`n` counts data rows from
  1); after it, `<column>: <value>` pairs are joined by `; `.
- A JSON, NDJSON or YAML line is `<path>: <value>`. The path joins keys
  with `.` and writes a list index as `[<n>]` (from 0) right after the
  key or, for an NDJSON line or a top-level list, at the start.
- An XML line is `<path>: <value>`. The path joins element names with
  `/`, numbers repeated siblings as `[<n>]` (from 1) and names an
  attribute as `@<name>`.
- `row <n>` and every bracketed `[<n>]` are positions, never values. A
  key that is itself a number (`2023: 5`) is a label and stays.
- JSON and YAML numbers are written positionally (`0.00001`, never
  `1e-05`); CSV and XML values stay as the source wrote them. A `text/plain` body is read as JSON when
it is an object or array that parses cleanly; anything else stays text.
The snapshot shows this rendering, escaped into the same inert document
as a text page.

Beyond the body cap, a document fails the source with its reason when it
nests deeper than 32 levels, has more than 10,000 values (XML: elements),
a CSV row has more than 500 columns or a field more than 100,000
characters. XML is parsed by defusedxml with entity declarations and
external references refused: no entity expansion (billion laughs), no
external entity or DTD is fetched. YAML aliases count every time they are
used, so an alias bomb hits the value cap; a self-referencing one fails.

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


Web pages have versions (migration 0015). The first read stores
`fetched_at` and `content_hash`, the sha256 of the extracted text with
whitespace normalized. A refetch puts the page back to `processing` with
`refetch_requested_at` set. The worker fetches and compares before any
model call:

- **Unchanged:** the page is ready again with a new `fetched_at`, and
  nothing is charged.
- **Changed:** in one transaction a new row (`version + 1`, `processing`)
  takes the dedupe key and every link and is read like a new source,
  charged as a web page. The old row is ready again, read-only, with
  `superseded_by` naming its successor. It is hidden from the library,
  but it keeps its chunks so the citations of existing outputs stay
  checkable.

Purging a page removes its older versions with it.

Every read of a web page version keeps a snapshot of what was read
(migration 0016): the fetched HTML rebuilt from an allowlist, so it
renders inert (`loaders/snapshot.py`). Only text and structure tags are
kept, with links to http(s) pages. Scripts, styles and their `url()`
imports, frames, forms, objects, images and other external resources,
event handlers and `style` attributes are dropped. A content security
policy in the document allows nothing but its own inline stylesheet. A
plain-text page becomes the same kind of document with its text in a
`<pre>`; a PDF behind a URL has no snapshot.

The snapshot is stored as `text/html; charset=utf-8` at
`<owner>/<library_id>/_snapshot.html`, with the address after redirects
(`final_url`) and `fetched_at`. Sources, library and trash entries carry
`snapshot_url`, presigned for one hour and inline. A refetch that finds
the page unchanged keeps the version's snapshot and `fetched_at` and
only moves `checked_at`. A new version gets its own snapshot, and a
purge removes the snapshots with their versions. The starter copy
copies a page's snapshot too.

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
embedding and summary rows. The text is then chunked, embedded and summarized like any
other source. A model refusing the image (HTTP 400) fails the source at
once, and so does an empty answer (a blank image: "the image holds no
readable content"), whose call is still recorded as usage; other
provider errors are retried. `IMAGE_MAX_TOKENS` (2000) caps
the answer.

### Large images are read in tiles

The platform scales every image to about the same small input budget,
roughly 400–600 tokens whatever its size, before the vision model sees it.
On a large screenshot the small text then becomes unreadable, and the
model fills it with plausible but invented lines. On a 2880×1800 app screen
with 72 cards, 68 of 160 lines were right read whole, and 159 of 160 in
four tiles ([vision-eval.md](vision-eval.md)).

An image over 1.5 MP is therefore cut (`loaders/tiles.py`) into the
fewest equal crops of at most 1.5 MP each, overlapping by 48 px:

| Image | Tiles |
|---|---|
| 1920×1080 | 2 |
| 2880×1800 | 4 of 1464×924 |
| 3840×2160 | 6 |

The crops are read in parallel, each with the image prompt and its own
loop check. A PNG stays PNG, so small text stays sharp. The answers are
joined in reading order, left to right and top to bottom. A line of at
least 20 characters that a tile shares with the tile above or to its left
is the overlap read twice, and is dropped from the later tile; shorter
lines such as "OK" are kept, since they may really repeat. Every call is
billed. If a tile fails, the answered tiles are billed and the image fails
with that tile's error ("… (tile 2 of 4)"). An image Pillow cannot decode
is sent whole, as before.

The upload records the tile count in `library_sources.page_count`. The
estimate charges one call per tile ("image, read in 4 tiles"; an image
uploaded before tiling counts as 1–4). The chunks view gives `tiles` for
an image read in more than one.

### Repetition loops

A model can fall into a loop: a few words, then one phrase until the
output cap. `loaders/degeneration.py` checks every model-made transcript
(an image, a PDF page read by the vision model, an audio transcript)
deterministically, on word tokens. It counts as degenerate when one of
these holds:

- one n-gram of 1 to 8 words repeats back to back 100 times or more;
- the answer stopped at the output cap (finish reason `length`) and one
  repetition fills at least 90 % of its last 200 words;
- some 500 consecutive words hold fewer than 25 distinct words.

Real repetition passes: a table of dozens of identical labels, a chorus
sung several times, a list of "Yes" answers.

A degenerate image or page answer is asked for once more, with
`temperature` 0.4, `frequency_penalty` 0.5, `presence_penalty` 0.3 and
`repetition_penalty` 1.15 (the platform accepts all four). If the second
answer loops too, the source fails with "the model's description
degenerated into repetition"; for a PDF the failing page is named. Both
calls are billed, and nothing is indexed. An audio transcript that loops
fails at once with "the model's transcript degenerated into repetition"
and its call is billed. There is no second attempt for audio, because
core's transcriber sends no sampling settings and the same file would be
transcribed the same way.

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
thread-safe); up to four pages are read at once. A rendered page over
1.5 MP is read in tiles like a large image, one tile after another: an A4
or letter page in two. On a dense scanned A4 page, read whole, 37 of 60
lines were right; read in two tiles, 60 of 60 ([vision-eval.md](vision-eval.md)).
The estimate counts two tiles of input per vision page. Each call is
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

## Starter notebook

A new user gets a copy of the starter notebook an admin marks (account's
settings row `starter_notebook`, `{"owner_id", "notebook_id"}`, set in
account's admin panel). `starter.ensure_starter` runs on the owner's
first `GET /notebooks` (the first thing the web loads after sign-in),
`GET /library` (any `kind`) or upload:

- The starter's uploads are copied: linked into it, `ready`, not
  trashed; never generated rows, whose outputs rag copies. First the
  stored objects (the original and a converted recording) under the
  owner's prefix, with the type the upload stored them with.
- Then, in one transaction: the seed mark (`library_seeds`), a notebook
  with the starter's title, a library row per source (`ready`, flagged
  `starter: true`, summary, dedupe key and capture as in the starter),
  its link, and its chunks with their embeddings. Nothing is processed
  and nothing is charged.
- The same transaction writes rag's `output_copies` row: the new and the
  starter notebook, the owner, and the id maps (`source_map`: old link
  id and old library id to new; `chunk_map`: old chunk id to new). Rag's
  worker copies the starter's outputs from it, remapping provenance.

At most once per owner. An owner with entries of their own is marked and
not seeded. Without a starter (no row, or a notebook that is gone)
nothing happens and the owner is not marked, so they get it once one is
set while their library is still empty. The starter's author gets no
copy. A storage failure copies nothing and is tried again on the next
access. The copies are the owner's own: deletable, purgeable, and an
upload of the same bytes links the copy like any duplicate.

The notebook is flagged `notebooks.starter` (migration 0019; copies made
before it were flagged by a backfill: a notebook linking starter sources
and created within a minute of its owner's seed).

**Made again on request.** `POST /starter/copy` (the help page's
"Recreate") makes a fresh copy for a user who deleted theirs, whether
or not they were seeded before. It is free:

- Without `force`, a user who still has a starter notebook gets 409
  `starter_exists`, so the web can ask before it makes another.
- At most one copy an hour per user (`library_seeds.copied_at`; the
  first sign-in's copy does not count). Otherwise 429 with `retry_after`.
- Deleting a notebook keeps its sources, so the user usually still has
  the starter's sources, and the library holds each content once per
  user. A starter source the user still has, found by its dedupe key, is
  linked into the new notebook, and restored first if it is in the
  trash. Its chunks map onto the starter's by index. Only the sources
  that are gone are copied, as at the first sign-in.
- The new notebook is flagged `starter`, and rag gets its
  `output_copies` row as at the first sign-in.

## Running the container locally

```bash
make build
docker run --rm -p 8000:8000 --env-file .env lasteverlm-ingest:$(git rev-parse --short HEAD)
```
