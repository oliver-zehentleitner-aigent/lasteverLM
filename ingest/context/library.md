# Source library

## Sources live in a per-user library; notebooks link them, chunks hang on the library entry

**Id:** a3fccab3-f77b-4bd2-bf32-07e522aba768
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** design proposal by the ingest author, aligned with the rag and web authors, approved by the fleet lead and the maintainer, 2026-10-13
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
Outputs that rag indexes get a library row of kind `generated` that no
library read ever returns, so every chunk has exactly one parent.

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
  first fetch; a refresh is a separate feature.
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
**Source:** the maintainer's request through the fleet lead, 2026-10-13; the retention key agreed with the account service
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

## The library schema came in two migrations, expand (0003) and contract (0004)

**Id:** 5bd279ae-da86-4aa6-878e-2217d77b14fc
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** library design reviewed with the coordinating agent, 2026-10-13 (0004 listed in TASKS.md as one release after 0003); 0004 written during the security and quality audit, 2026-10-14
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
