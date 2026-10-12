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

## Migrations run as a Helm hook before every upgrade, not as a separate make step

**Id:** 035196f6-5949-4b55-bcc9-1beab2b7d73c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12, following the maintainer's move to Helm with automatic releases on tags
**Revisit when:** a migration has to run while the old pods keep serving (expand/contract), or a rollback needs a down migration

The migration Job carries `helm.sh/hook: pre-install,pre-upgrade` with
`hook-delete-policy: before-hook-creation,hook-succeeded`; the
ConfigMap with the tarball is a hook too, at a lower weight. A failed
Job fails the release before any Deployment changes. The hook is
rendered only when `chart/files/migrations.tgz` exists, which
`make migrations` and `make package` guarantee.

**Reason:** with releases triggered by a tag in CI, there is no
operator to run `make migrate` first; the hook ties the schema change
to the release that needs it, and a failed migration stops the rollout
instead of leaving new pods against an old schema.

**Rejected alternative:** a standalone `make migrate` Job before
`helm upgrade` — the earlier design; works by hand, rejected because the
release workflow would have to replicate it and the two could drift.
Init containers running migrations in every pod — four Deployments
racing for the same DDL, and the admin credentials in every pod.

## The embedding dimension is a psql variable, not a number in a migration

**Id:** 726208e7-a8c2-4f34-af1d-eb09a943b9cd
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** parent architecture v1 ("the migration takes it as a parameter, default 1536"); the mechanism was chosen here on 2026-10-12
**Revisit when:** a second parameter needs to reach migrations, or the dimension has to change on a populated table

`db/migrate.sh` passes `-v EMBEDDING_DIMENSION=<n>` to every `psql`
call, taken from the Job's environment, which the chart sets from the
same value the `lasteverlm-config` ConfigMap carries, default 1536. A migration writes
`vector(:EMBEDDING_DIMENSION)`.

**Reason:** the dimension follows the embedding provider, which is
configuration, and the one copy of that value is the ConfigMap the
services read too. A psql variable is the plainest way to get it into
SQL without a templating step.

**Rejected alternative:** rendering the SQL files with `sed` before
shipping them, as the Makefile does for the Ingress — would make the
collected files differ from what the service directory committed,
which defeats the audit trail.

## Migrations run as the admin role, services as a restricted one

**Id:** 7652a827-0b6a-4e1a-ad3b-fe108d3d4f4a
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** infra design session, 2026-10-12
**Revisit when:** the first `make migrate` against a real Vultr database shows which privileges the application role actually has

OpenTofu creates a logical database and a separate role for the
services; the Job uses the primary admin user Vultr creates with the
instance. `CREATE EXTENSION vector` is assumed to need the admin role on
a managed database — not verified yet, which is why the evidence is
inferred. Even if the application role turns out to have the privilege,
keeping DDL on a role the services do not hold is the intended split.

## The managed database is reachable from any IP

**Id:** f8de01a5-e14a-4479-84cc-9cbc512333bd
**Type:** workaround
**Status:** superseded
**Superseded by:** eafb2511-ce6a-4da4-a91b-18b1fcaca468
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12
**Revisit when:** the cluster has stable egress addresses to allowlist, or the database is attached to the cluster's VPC

`vultr_database` sets no `trusted_ips`, so the instance accepts TLS
connections from anywhere with valid credentials. The worker nodes'
public addresses are only known after the cluster exists and change
when nodes are recycled, so an allowlist written at apply time would be
wrong after the first node replacement. Known and accepted for the MVP;
the fix is a VPC-attached database (`vpc_id` on both resources), which
is a second apply step this skeleton does not take yet.

## The managed database accepts only the cluster nodes and the operator machine

**Id:** eafb2511-ce6a-4da4-a91b-18b1fcaca468
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer requirement relayed by the family coordinator, 2026-10-12 ("security exemplary, no shortcuts")
**See:** database.md#the-managed-database-is-reachable-from-any-ip — f8de01a5-e14a-4479-84cc-9cbc512333bd — as of 2026-10-12
**Revisit when:** the database is attached to the cluster's VPC, or nodes are recycled (the list has to be refreshed)

`make db-trust` writes the worker nodes' public addresses plus the
address of the machine running it into the instance's trusted-IP list.
It is re-run after any node change; the Makefile documents that. The
proper fix is attaching the database to the cluster's VPC (`vpc_id` on
the instance, private host for the pods), which removes the public
path entirely; it is not done yet because the instance was created by
hand outside OpenTofu and the VPC attachment is a second step with its
own downtime window.

**Reason:** an instance open to every address with only a password in
front is the one shortcut the maintainer named explicitly; the node
list is what can be enforced tonight without touching the instance's
network.

**Rejected alternative:** leave it open until the VPC move — rejected
by the maintainer.

## The managed PostgreSQL is an input, not an OpenTofu resource

**Id:** 210e2af5-c0c6-4459-8aff-9e33a06c52b2
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordinator, 2026-10-12: the maintainer created the instance by hand in Frankfurt before the first run
**Revisit when:** the instance is recreated, or the project wants the database under OpenTofu after all

`tofu/` creates the cluster and the object storage only. The instance's
admin URL is `DATABASE_ADMIN_URL` in the operator's environment;
`make env` derives from it the application role's URL and the admin URL
on the application database (`scripts/dburls.py`), and
`make db-bootstrap` runs a Job as the admin role that creates the role
(login only, no superuser, cannot create extensions), the database the
role owns, and `CREATE EXTENSION vector`. A rotated admin password is
one `make secrets` away because nothing but the environment holds it.

**Reason:** importing a hand-made instance into state on the first
night was more risk than value, and a database that outlives
`make down` is what the maintainer wanted anyway; the bootstrap Job
keeps the toolchain free of a local `psql`.

**Rejected alternatives:** `tofu import` of the instance — one wrong
attribute and the next apply replaces a database; keeping the
`vultr_database` resource and letting it create a second instance —
two databases to pay for and confuse.

