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
query, the way core reads `users.is_admin`: the purge is one batch
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
