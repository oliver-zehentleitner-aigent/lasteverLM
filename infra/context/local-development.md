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

## The local database is set up by the cluster's own scripts

**Id:** 07934f86-700a-4f20-99ca-974182f87892
**Type:** decision
**Status:** active
**Evidence:** inferred
**Revisit when:** the cluster's migration path changes (another runner, migrations inside the services)

The `migrate` service in `compose.yaml` runs `db/bootstrap.sh`
and `db/migrate.sh` from this directory against the local
PostgreSQL, with every service's `db/migrations/` mounted in the
layout the chart's hook Job sees. The gateway routes the same paths as
the production Ingress, with the same body size and read timeout.

**Reason:** the local stack is where a migration or a routing change
should fail first. The production path has rules a plain local setup
would not exercise — the application role owning its tables through
`SET ROLE`, the order infra, core, account, ingest, rag, the
`:EMBEDDING_DIMENSION` variable — and the cluster has already
failed once on table ownership; running the same scripts locally
catches that class of error before a deploy.

**Rejected alternatives:** a superuser connection with an init SQL
file — simpler, but hides exactly the ownership and privilege errors
the cluster would hit; each service creating its schema on start-up —
contradicts the contract that migrations are applied once, outside the
services; the web container's own dev proxy (`VITE_DEV_PROXY`) in
place of a gateway — covers only the front end's requests, not the
API paths a test or curl sends.

## Local-only credentials are written into compose.yaml

**Id:** f18fc8da-3a11-4d86-af73-59cd3b418528
**Type:** decision
**Status:** active
**Evidence:** inferred
**Revisit when:** the compose file is used for anything reachable from another machine

The database passwords, the storage keys, the JWT secret, the demo
token and the visitor hash secret in `compose.yaml` are fixed,
readable values such as `local-dev-password`. They are not secrets
and are not used anywhere else: the deployment never reads this file,
`make secrets` generates its own values with `openssl rand`, and
every published port binds to 127.0.0.1.

**Reason:** `make local-up` should work from a clean checkout with a
single value from outside (`INFERENCE_API_KEY`, which costs money and
therefore cannot have a default). Names that say "local" and "dev"
make a copy into a real configuration easy to spot.

**Rejected alternatives:** generating them on first run into a local
env file — one more step and one more file to explain for values that
protect nothing outside the developer's machine; requiring them all in
the shell environment — the same, and a reason for developers to reuse
production values.
