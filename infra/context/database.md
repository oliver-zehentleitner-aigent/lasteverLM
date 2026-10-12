# Database

## Migrations are plain SQL owned by each service, applied by one Job from here

**Id:** 5372a96b-deb8-4dc3-8a00-63743e5a2f01
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12; the parent's architecture v1 fixes the ownership and the order (core, account, ingest, rag)
**Revisit when:** a migration needs logic SQL cannot express, or a service has to migrate independently of the others

Each service directory keeps `db/migrations/NNNN_<topic>.sql` for its
own tables; `infra/` keeps only the extensions file and the runner.
`make migrations` collects all of them from the sibling directories of
the mono repo into `chart/files/migrations.tgz`; the chart ships the
tarball and `db/migrate.sh` as a ConfigMap and runs the script in a
`postgres:17-alpine` Job as a Helm pre-install/pre-upgrade hook, so a
release cannot roll out pods against a schema that is behind. See the
hook entry below. The script applies `infra`, then the services
in the fixed order, each file once, each in its own transaction, and
records a file as `<service>/NNNN_<topic>` in `schema_migrations`.

**Reason:** the schema is the contract between services written by
different agents; plain SQL is the one format none of them has to
translate, and the service that owns a table owns its DDL. The
`<service>/` prefix in the version key exists because every service directory
numbers from `0001` — without it the second service's first
migration would look already applied. Running inside the cluster means
the operator's machine needs no `psql` and no database network access,
and the Job logs are the audit trail of what was applied when.

**Rejected alternatives:** Alembic or dbmate — a migration tool brings
its own version table, its own CLI and, for Alembic, a Python
environment into a directory that has no Python; each service applying
its own migrations at startup — four pods racing for the same schema,
and `CREATE EXTENSION` would need the admin role in every service;
`psql` from the operator's machine — not installed where this is built,
and it would need the database opened to that machine's IP.

