# Object storage

## Object storage lives in Amsterdam, the cluster in Frankfurt

**Id:** aace1aa3-3220-4499-a8fd-eb5dd9885ef2
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** Vultr API `GET /v2/object-storage/clusters`, queried 2026-10-12
**Revisit when:** Vultr opens an object storage cluster in `fra`

The compute region is `fra` (nearest to the maintainer), but Vultr has
no object storage cluster there; the available European clusters are in
`ams`. `object_storage_region` therefore defaults to `ams` separately
from `region`. Uploads cross one hop between the regions, which at the
MVP's file sizes is irrelevant. Moving the cluster to `ams` as well was
not chosen only because the regions may diverge again later; nothing
else depends on it.

