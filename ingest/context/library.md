# Source library

## Sources live in a per-user library; notebooks link them, chunks hang on the library entry

**Id:** a3fccab3-f77b-4bd2-bf32-07e522aba768
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** design proposal by the ingest author, aligned with rag and web, approved by the maintainer, 2026-10-13
**Revisit when:** sources need to be shared between users, or a vector index with a notebook filter loses recall because libraries grow far larger than notebooks

What a user uploads or enters (a file, an image, a URL) is a library
source (`library_sources`), owned by that user and processed once.
`sources` is the link of a library source into a notebook; its id stays
the public source id, so the Source shape and citations keep their
meaning. Chunks and embeddings hang on the library source and are
searched from every notebook that links it. Detaching (DELETE /sources)
keeps the library source and its chunks; deleting it from the library
removes it from every notebook. The same bytes (sha256) or the same
normalised URL from the same user link the existing library source
instead of storing and processing it again; two users never share one.
Outputs that rag indexes get a library row of kind `generated`, so every
chunk has exactly one parent. These rows were first hidden from every
library read; since 2026-10-14 they are listed on their own and linkable
(entry aadeec34-047c-4e27-8c7b-33de3a883a1b).

**Reason:** processing once per library source is what makes adding to a
second notebook free and instant; keeping the link id as the source id
spares the API, rag's citations and web a breaking change.

**Alternatives:**
- Chunks per notebook (copy the chunks on every link): every notebook
  pays embedding again or copies vectors, and a delete has to find every
  copy. Rejected: processing once is the point of the library.
- Deduplicate URLs by content hash: needs the fetch the library is meant
  to save, and the same text at two URLs is two sources for citations.
  Consequence of deduplicating by URL: adding the same URL again uses the
  first fetch; fetching again is its own request, with versions
  (url-sources.md, entry 9b572655-c22f-47b1-8ba1-ecdffad01088).
- Chunks with two possible parents (library source or a generated
  source): every search and delete would branch on the parent; the
  hidden `generated` row keeps one rule at the cost of one filter.
- Hashing the objects stored before the migration so old files
  deduplicate too: skipped, the demo ends in days and a pre-migration file
  processed once more costs one more embedding run.

## Deleting from the library goes to a trash with per-user retention

**Id:** 2e28a094-0219-4fe7-8d85-e1f9ba20517f
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request, 2026-10-13; the retention key agreed with the account service
**Revisit when:** storage of trashed objects becomes a cost worth a quota, or users ask to empty the trash at once

`DELETE /library/{id}` sets `deleted_at` and removes the entry from every
notebook; its chunks and stored object stay. It can be restored (into
no notebook) or purged at once; otherwise the workers purge it when the
owner's `trash_days` (account's preference, default 14) has elapsed,
at start and once an hour. Uploading its bytes or URL again restores it,
so the dedupe key stays unique per user.

**Reason:** deletion was final, and a misclick lost chunks whose
embeddings and summary cost model calls. The trash makes a delete
reversible for the cost of keeping rows and objects a while.

The retention is read straight from `users.preferences` in the purge
query, the way core reads a user's role: the purge is one batch
statement over all users, and services do not call each other at
runtime; the contract with account is the key name and its default.

**Alternatives:**
- No trash, a confirm dialog only: a confirm protects against the click,
  not against the second thought a minute later.
- Reading the retention through account's API: one call per owner per
  purge and a runtime dependency between services, for a single number.
- A second library row on re-upload of trashed bytes: two rows with one
  dedupe key, or a key that is unique only outside the trash; restoring
  is simpler and saves the processing.

## Outputs are library items that rag owns

**Id:** aadeec34-047c-4e27-8c7b-33de3a883a1b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (outputs become user-owned library items, usable as a source in other notebooks); the split of the lifecycle agreed with rag the same day
**Revisit when:** ingest has to process or change generated rows itself

A generated library source (rag's output) is owned by the user and can
be linked into any of their notebooks; linking reuses its chunks. Rag
owns its whole lifecycle, trash, restore and purge with the audio object
first, so the objects-before-rows order stays in one service: ingest
keeps excluding generated rows from its trash and purge, and its notebook
delete and detach remove only links. The origin notebook is read from
rag's `outputs` (`notebook_id`, `origin_title`), not from a link, because
the user can unlink an output from the notebook it was made in.

**Alternatives:**
- Ingest's purge sweeping trashed generated rows: two services deleting
  one kind of row, and the audio object (rag's) would have to be deleted
  by rag before ingest's sweep, an order across services.
- The origin as the link whose id equals the library id: gone once the
  user unlinks the output from its origin notebook.

## A shared notebook shows its sources by name, never their files

**Id:** 9eda5c9c-7673-4343-814b-0d42feea51e1
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (share a notebook read-only), including what the public view shows
**Revisit when:** users ask to share source files along with a notebook, or a notebook's sources include material meant to be public

A notebook gets a read-only link (`notebooks.share_token`, made once,
revoked by the owner, the scheme of rag's output links). Rag composes the
public view: the title, the outputs shared with it, and the sources by
name and kind only, with no file, no preview and no presigned URL. The
source files are the owner's uploads; sharing the notebook shares what
was made from them, not the uploads themselves.

**Alternatives:**
- Sharing the source files too (presigned links in the public view):
  one link would hand out every upload of the notebook, including ones
  the owner never meant to pass on, and copyrighted material they may
  use privately but not redistribute.

## Deleting a user removes the objects before the rows

**Id:** 74926408-01fb-42f0-9a63-83af364b450c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (delete a user in the admin panel, objects before rows); the call contract settled with account the same day
**Revisit when:** storage gets a lifecycle rule or a listing that can find objects without their rows

`DELETE /admin/users/{id}` reads the keys of the user's stored objects
from their library rows, deletes the objects, and only then deletes the
rows. A storage failure answers 503 and leaves every row, so the retry
(account stops and the admin tries again) finds the same keys; rows are
the only index of what the user stored.

**Alternatives:**
- Rows first, objects swept later by an orphan sweep: the rows are the
  only record of the keys, so the sweep would have to list the bucket and
  match prefixes; until it ran, a deleted user's files would still sit in
  storage.

## The library schema came in two migrations, expand (0003) and contract (0004)

**Id:** 5bd279ae-da86-4aa6-878e-2217d77b14fc
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** library design, 2026-10-13 (0004 planned for one release after 0003); 0004 written during the security and quality audit, 2026-10-14
**Revisit when:** never for these two files; the next schema move that a running release still reads follows the same pattern

0003 created `library_sources`, backfilled it and made the old columns
on `sources` and `chunks` nullable instead of dropping them. 0004 drops
them (and sets `library_source_id` not null), and ships in a release
after the one that shipped 0003. It is numbered 0004 although 0005–0008
were applied before it: the runner records each file by name, so a file
added later still runs once. It repeats 0003's backfill, guarded so a
second run is a no-op, for rows an old pod wrote during 0003's rollout.

**Reason:** a deploy is a rolling update: for a while pods of the
previous release run against the migrated schema. With the columns
dropped in one step, those pods would fail every source read and write
until they were replaced. Keeping them one release costs nothing but
dead columns.

**Alternatives:**
- One migration that moves and drops at once: breaks the previous
  release's pods mid-rollout.
- Keeping the old columns for good: every reader would have to know
  which of two places is current, and `sources` would keep a nullable
  `status` nobody writes.

## Which model made a source's text is stored on the library row

**Id:** e0341fed-25d9-4b97-aa77-ab6ac5760941
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15 (the web says which model read a source: described, page read, transcribed); the storage and the shape are the ingest author's, agreed with web
**Revisit when:** a source is read by more than one vision or speech model, or chunks need a provenance of their own beyond the page they start on

When a model-made read finishes, the worker records `read_by`
(`{"vision": <model> | null, "stt": <model> | null}`) and, for a PDF,
`vision_pages`, the pages the vision model read, on the library row
(migration 0018). The API gives `read_by` on a linked source and in the
chunks view, and marks each chunk `vision` when it is an image's or
starts on a vision page. A source read by no model has `read_by` null,
and so does a source read before the field existed.

**Reason:** the model is known exactly when the loader runs. The same
row is what a starter copy duplicates, so a copy says what read the
original without any usage rows of its own. Per-chunk provenance follows
from the page, because a chunk is attributed to the page it starts on,
as its citation is.

**Alternatives:**
- Deriving the models from the usage rows of the read: the summary is
  an `llm` row with the same model as a vision call, so an image's rows
  cannot tell them apart; a starter copy has no usage rows at all.
- A `vision` column on every chunk: a write per chunk and a migration of
  the chunks table, for what the page already says.
