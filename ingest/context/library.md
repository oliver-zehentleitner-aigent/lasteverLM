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
