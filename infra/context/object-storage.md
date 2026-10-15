# Object storage

## Object storage lives in Amsterdam, the cluster in Frankfurt

**Id:** aace1aa3-3220-4499-a8fd-eb5dd9885ef2
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** Vultr API `GET /v2/object-storage/clusters`, queried 2026-10-12
**Revisit when:** Vultr opens an object storage cluster in `fra`

The compute region is `fra` (nearest to where the demo is used), but Vultr has
no object storage cluster there; the available European clusters are in
`ams`. `object_storage_region` therefore defaults to `ams` separately
from `region`. Uploads cross one hop between the regions, which at the
MVP's file sizes is irrelevant. Moving the cluster to `ams` as well was
not chosen only because the regions may diverge again later; nothing
else depends on it.

## The bucket is created with one signed curl request, not by the provider

**Id:** 7c84c107-07b8-4200-93ab-c8407f97ac37
**Type:** workaround
**Status:** active
**Evidence:** confirmed
**Source:** `tofu validate` against provider 2.33.1 on 2026-10-12: "Blocks of type bucket are not expected here"
**Revisit when:** the `vultr_object_storage` resource gains the `bucket` block that the provider's unreleased docs already describe

`make bucket` issues a single `PUT /<bucket>` with curl's built-in
SigV4 signing against the S3 endpoint and accepts 200 or 409 as "exists".

**Reason:** the released provider manages the storage subscription but
not buckets inside it, so the bucket has to come from somewhere else.

**Rejected alternatives:** a second OpenTofu root with the AWS provider
pointed at the Vultr endpoint — a whole provider and an extra apply
step for one bucket; letting the ingest service create the bucket on
startup — moves an infrastructure concern into application code and
needs bucket-creation rights on the service's keys; installing `s3cmd`
or the AWS CLI — one more tool on the operator's machine for one call
curl already makes.

## The object storage cluster is chosen by id, not by region filter

**Id:** 948b72f6-5f66-4002-998e-8e251e03116a
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** first `tofu apply` on 2026-10-12: the region filter returned two Amsterdam clusters (ids 6 and 12) and the data source refused to pick
**Revisit when:** the provider's data source learns to pick a cluster, or ams1 is retired

`object_storage_cluster_id` defaults to 6 (`ams1.vultrobjects.com`)
and the `vultr_object_storage_cluster` data source is not used. A
region can host several object storage clusters, so the filter is not
a selector. The id comes from `vultr-cli object-storage cluster list`.
