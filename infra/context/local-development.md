# Local development

## RustFS stands in for MinIO as the local S3 storage

**Id:** d7f94e9a-8ec7-4264-b7d2-f39408fd3926
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** Docker Hub `minio/minio` answers "object not found", `quay.io/minio/minio` requires authentication (both checked 2026-10-13); `rustfs/rustfs` 1.0.1 (Apache-2.0) published 2026-10-03
**Revisit when:** MinIO publishes public images again, or RustFS stops being maintained

`compose.yaml` runs `rustfs/rustfs:1.0.1` as the S3 endpoint the
ingest and rag services write to locally. The task asked for MinIO,
but MinIO no longer publishes pullable images; building it from source
on every developer machine is not a reasonable start-up step.

**Reason:** RustFS speaks the S3 API the services use through boto3
(put, get, delete, list, create bucket), takes its keys from two
environment variables like MinIO did, ships a web console, and is
Apache-2.0. The local smoke test (upload, ingest, ask with citation)
passed against it.

**Rejected alternatives:** MinIO built from source — slow, and an
AGPL build step in every checkout; SeaweedFS — mature, but S3 access
keys need its own JSON identity configuration and the Docker Hub tag
listing showed no plain release tags to pin; pointing local runs at
the real Vultr bucket — mixes developer data into the deployment's
storage and needs the production keys on every machine.
