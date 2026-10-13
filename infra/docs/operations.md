# Operations

How to take `infra/` from a clean checkout to a running lasteverLM
deployment, and how to run it afterwards. The reasoning behind these
choices is in `context/`. All commands run in `infra/`.

## Tools

`tofu` (OpenTofu 1.6+), `helm` (3.x), `kubectl`, `vultr-cli`, `make`,
`curl`, `tar`, `python3` (3.10+). Migrations run inside the cluster,
the bucket is created with curl; nothing else is needed.

## Inputs

| Input | Where | Used by |
|---|---|---|
| `VULTR_API_KEY` | environment | `make up`, `make kubeconfig`, `make db-trust`, `make down` |
| `TF_VAR_object_storage_tier_id` (or `tofu/terraform.tfvars`) | environment | `make up`; `vultr-cli object-storage tier list` shows the ids |
| `DATABASE_ADMIN_URL` | environment; the managed instance's admin role, created by the maintainer | `make env` (derived URLs), `make db-bootstrap` |
| `PGSSLROOTCERT` | environment, path to the instance's CA file | `make secrets` (ConfigMap `lasteverlm-pg-ca`) |
| `DOMAIN`, `ACME_EMAIL` | environment | `make values` / `make deploy` |
| `LLM_MODEL`, `EMBEDDING_MODEL`, `MODEL_PRICES` (JSON) | environment | `make values` / `make deploy` |
| `TAG` (default `latest`), `REGISTRY` (default `ghcr.io/oliver-zehentleitner`) | make variables | `make deploy` |
| `EMBEDDING_DIMENSION`, `SIMILARITY_FLOOR`, `TTS_MODEL`, `TTS_VOICE` (default `ryan`), `INFERENCE_BASE_URL` | environment, optional | `make values` |
| `INFERENCE_API_KEY` | environment | `make secrets` |
| `AUTH_ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `VISIT_HASH_SECRET`, `SMTP_*` | environment, optional | `make secrets` (account seeds; without an allowlist and an admin address nobody can log in) |
| `DEMO_TOKEN` | environment, for `make smoke` only; the cluster's value is generated, see below | `make smoke` |

Generated, never typed: `APP_DB_PASSWORD`, `AUTH_JWT_SECRET` and
`DEMO_TOKEN` are created by `make env` with `openssl rand`, kept in
`build/cluster.env` (mode 600, ignored by Git) and go only into the
Kubernetes Secrets. No target prints them. To use the demo token from
the operator machine, copy it from `build/cluster.env` into the env
file by hand.

Keep the secrets in an env file outside the repository and load it with
`set -a; . ~/lasteverlm.env; set +a`.

## First deployment

```sh
make up          # VKE cluster and Object Storage (AUTO_APPROVE=1 skips the plan prompt); writes build/cluster.env
make kubeconfig  # build/kubeconfig; the Makefile exports KUBECONFIG for every target
make bucket      # sources bucket (private; the keys live only in the lasteverlm-s3 Secret)
make db-trust    # the managed database accepts only the node addresses and this machine
make platform    # ingress-nginx + cert-manager + metrics-server; prints the load balancer IP
```

Point `DOMAIN` at the printed IP (an A record), then:

```sh
make db-bootstrap  # once: application role, database, pgvector (runs make secrets first)
make deploy        # make values + make migrations + helm upgrade --install
make status
```

The managed PostgreSQL is not created here: the maintainer created it
by hand, `DATABASE_ADMIN_URL` is its admin connection string.
Everything derives from that one value, so a rotated admin password is
`make secrets` (which re-runs `make env`) and a restart of the pods.
Every connection uses `sslmode=verify-full` against the CA mounted
from the ConfigMap `lasteverlm-pg-ca`. `make db-trust` has to be
re-run after nodes are recycled; the proper fix is the VPC attachment
(`context/database.md`).

`make deploy` runs the migration hook first (see below) and then rolls
every service to `TAG`. A later `make deploy TAG=<git-sha>` is the
manual equivalent of what the release workflow does on a tag.
`HELM_WAIT=0` returns right after the install instead of waiting for
the rollout. Before DNS and the certificate exist, the smoke test
reaches the deployment through the load balancer address:
`make smoke URL=https://<lb-ip> SMOKE_ARGS="--host $DOMAIN --insecure"`.

## The chart

`chart/` renders, for the namespace `lasteverlm`:

| Object | What |
|---|---|
| ConfigMap `lasteverlm-config` | non-secret settings from the values file |
| Deployments `account`, `ingest`, `rag` | API services, port 8000, `/healthz` probes, `envFrom` the ConfigMap and their Secrets |
| Deployments `ingest-worker`, `rag-worker` | same image, command `lasteverlm-<service>-worker`, no Service, no port |
| Deployment `web` | static frontend, port 8080 |
| HorizontalPodAutoscalers | one per Deployment above, CPU based, minimum two replicas |
| Services | one per API service and web, port 80 |
| Ingress `lasteverlm` | path routing `/api/account`, `/api/ingest`, `/api/rag`, `/`; TLS via cert-manager; per-IP rate limiting (`limit-rps`, burst multiplier, `limit-connections`) |
| ClusterIssuer `letsencrypt` | ACME http01 |
| Job `lasteverlm-migrate` + ConfigMap | pre-install/pre-upgrade hook, see Migrations |

Values: `chart/values.yaml` holds the defaults (replicas, autoscaler
bounds, resources, rate limits, which Secrets each service mounts).
Every image sets a numeric `USER`; an image that names its user would
need `runAsUser` in its values, because `runAsNonRoot` cannot verify a
name.
`make values` writes `build/values.yaml` with the deployment-specific
part (domain, tag, registry, model names, prices, S3 endpoint) via
`scripts/values.py`; `make deploy` passes it to Helm. The chart version
is the repository tag: `make package VERSION=0.1.0`.

## Migrations

`make migrations` collects `db/migrations/*.sql` from `infra/`
(extensions, applied first) and from `../core`, `../account`,
`../ingest`, `../rag`, in that order, into `chart/files/migrations.tgz`
next to a copy of `db/migrate.sh`. The chart ships both as a ConfigMap
and runs the script in a `postgres:17-alpine` Job as a Helm
pre-install/pre-upgrade hook with the admin connection string. A failed
migration fails the release before any pod changes.

Contract for the service directories:

- Files are `db/migrations/NNNN_<topic>.sql`, numbered per service, applied in file order.
- Each file runs in its own transaction and is recorded as `<service>/NNNN_<topic>` in `schema_migrations`; never edit an applied file, add a new one.
- The psql variable `:EMBEDDING_DIMENSION` is available (default 1536), so `vector(:EMBEDDING_DIMENSION)` follows the configured provider.
- `CREATE EXTENSION` belongs in `infra/db/migrations`, not in a service's migration.
- Service files run under `SET ROLE lasteverlm` (the application role owns its tables; the admin is a member of that role, granted by `make db-bootstrap`). A migration must not assume superuser rights or ownership of anything the application role does not own.

To see what a run did: `kubectl -n lasteverlm logs job/lasteverlm-migrate`
(the Job is deleted on success and before the next run).

## Secrets

| Secret | Keys | Mounted by |
|---|---|---|
| `lasteverlm-db` | `DATABASE_URL` (application role) | account, ingest, rag and their workers |
| `lasteverlm-db-admin` | `DATABASE_URL` (admin role, application database) | migration Job only |
| `lasteverlm-db-bootstrap` | `DATABASE_ADMIN_URL`, `APP_DB_PASSWORD` | bootstrap Job only |
| ConfigMap `lasteverlm-pg-ca` | `pg-ca.crt` | every pod that opens a database connection, at `/etc/lasteverlm/pg-ca.crt` |
| `lasteverlm-s3` | `S3_ACCESS_KEY`, `S3_SECRET_KEY` | ingest, rag (audio files) |
| `lasteverlm-inference` | `INFERENCE_API_KEY` | ingest, rag |
| `lasteverlm-auth` | `AUTH_JWT_SECRET`, `DEMO_TOKEN` | account, ingest, rag |
| `lasteverlm-account` | `AUTH_ALLOWED_DOMAINS`, `ADMIN_EMAILS`, `VISIT_HASH_SECRET` | account |
| `lasteverlm-smtp-seed` (optional) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | account |

Re-running `make secrets` updates the objects in place; pods pick the
new values up on their next restart (`kubectl -n lasteverlm rollout restart deployment`).

Edge: ingress-nginx redirects HTTP to HTTPS and sends HSTS
(`platform/ingress-nginx.values.yaml`); the Ingress additionally
carries `force-ssl-redirect`.

## TLS certificate

cert-manager issues the certificate through the ClusterIssuer
`letsencrypt` (ACME HTTP-01, solved through the nginx ingress class,
contact `ACME_EMAIL`). The Ingress names the secret `lasteverlm-tls`;
cert-manager creates the Certificate from it, and the order stays
pending until `DOMAIN` resolves to the load balancer, then completes on
its own. For lasteverlm.zehentleitner.co that happened on 2026-10-13:
Certificate `lasteverlm-tls` Ready, issuer Let's Encrypt `YR2`, SAN
`lasteverlm.zehentleitner.co` only, valid 07:01 UTC (09:01 CEST) to
2027-01-11, renewal scheduled by cert-manager for 2026-12-12 (30 days
before expiry). Checked from outside: `http://` answers 308 to
`https://`, `https://` answers 200 with
`Strict-Transport-Security: max-age=31536000`.

```sh
kubectl -n lasteverlm get certificate,certificaterequest,order   # Ready / valid
kubectl -n lasteverlm describe certificate lasteverlm-tls         # events, renewal time
```

A Certificate that stays not Ready: `kubectl -n lasteverlm get
challenge` shows the pending HTTP-01 challenge and why (usually DNS not
pointing at the load balancer yet, or port 80 not reachable).

## Platform versions

Pinned in the `Makefile`: ingress-nginx chart 4.15.1 (controller
1.15.1), cert-manager v1.21.2, metrics-server chart 3.14.0, VKE
`v1.37.1+2` (default in `tofu/variables.tf`; `make vke-versions` lists
what the API offers). Bumps go through a pull request and a
`CHANGELOG.md` line.

## Workflows

Owned here, stored at the repository root in `.github/workflows/`:

| File | Trigger | What |
|---|---|---|
| `ci.yml` | push, pull request, path-filtered per directory | `make check` in the directories that changed |
| `docker.yml` | push to `main`, tags `v*` | builds every service image with the repository root as context (`-f <service>/Dockerfile .`), pushes to ghcr.io tagged with the Git SHA and the tag |
| `deploy.yml` | tags `v*` (after `docker.yml`), and manual with a tag input | `make deploy TAG=<tag>` in `infra/` with the kubeconfig from a repository secret, then the smoke test where a demo token is configured |
| `ktw-lint.yml` | push to `main`, pull request | the Keep the Why structure check for the root and every sub-project |
| `pages.yml` | push to `main` | the Keep the Why dashboard export |

Repository secrets for `deploy.yml`: `KUBECONFIG_B64` (the file
`make kubeconfig` writes, base64), `DEMO_TOKEN` (optional). Repository
variables: `DOMAIN`, `ACME_EMAIL`, `LLM_MODEL`, `EMBEDDING_MODEL`,
`MODEL_PRICES`, `S3_ENDPOINT`, optional `EMBEDDING_DIMENSION`,
`SIMILARITY_FLOOR`, `TTS_MODEL`, `TTS_VOICE`. The workflow runs `make values` and
`make deploy` without a tofu state, which is why `S3_ENDPOINT` is a
variable there.

## Teardown

`make down` runs `tofu destroy` after its confirmation prompt and
removes `build/cluster.env` and `build/kubeconfig`. The Let's Encrypt
account key and certificates go with the cluster.

## Checks

`make check` runs what CI runs for this directory: `tofu fmt` and
`validate`, `helm lint` and `helm template`, `sh -n` on the runner,
`scripts/values.py`, the unit tests, `ktw-lint`.
