# Admin

## Stored bytes come from a size column, not from the bucket

**Id:** 18bc9032-4ff3-43a3-8098-ca77996efa4f
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-13, for the admin statistics ("total source bytes if cheap")
**Revisit when:** the admin overview needs exact totals for sources created before migration 0002

`GET /admin/stats` sums `library_sources.size_bytes` (on `sources` until
the source library, migration 0003), a column added by migration 0002 and
written by the API when it stores a source. Rows
created before the migration have no size and count as 0; there is no
backfill.

**Reason:** the endpoint is one read-only database query; listing the
bucket on every call costs one S3 request per thousand objects and makes
an admin page depend on object storage being reachable. The API already
holds the bytes when it stores them, so recording the length is free.

**Alternatives:**
- Sum object sizes from an S3 listing: exact for old rows too, but slow
  and an external dependency on every request.
- Backfill old rows from the bucket in the migration: a migration that
  needs S3 credentials and network access, for a handful of demo rows.
