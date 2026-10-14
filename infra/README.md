# infra

[![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

Infrastructure of [lasteverLM](../README.md): the Vultr resources, the
Helm chart that deploys the whole application, the migration runner and
the deploy procedure. No application code. The services live in the
sibling directories; the contract they are built against is
[`docs/architecture.md`](../docs/architecture.md).

Status: deployed on Vultr (VKE in Frankfurt, managed PostgreSQL,
Object Storage), served at https://lasteverlm.zehentleitner.co with a
Let's Encrypt certificate; `compose.yaml` runs the same stack locally.

## What is in here

| Path | Purpose |
|---|---|
| `compose.yaml`, `compose/` | Local development stack and its gateway configuration |
| `tofu/` | OpenTofu configuration: VKE cluster and Object Storage (the managed PostgreSQL is created by the maintainer and taken as an input) |
| `chart/` | The Helm chart (`values-prod.yaml`: the production configuration, committed): ConfigMap, API and worker Deployments with autoscalers, Services, Ingress with rate limiting, ClusterIssuer, migration hook, account's read-only Role |
| `platform/` | Values for the platform charts: ingress-nginx (JSON access log), cert-manager, metrics-server |
| `db/migrations/` | Infra-owned SQL (extensions); the services' own migrations are collected at deploy time |
| `db/migrate.sh`, `db/bootstrap.sh` | The migration runner the chart's hook Job executes, and the one-time database bootstrap |
| `scripts/` | `dburls.py` (admin URL to the derived connection strings), `tofu_outputs.py` (tofu outputs to `cluster.env`, fails on a missing one), `web-csp-check.sh` and `csp/walk.mjs` (`make web-csp-check`) |
| `tests/` | The family's end-to-end smoke test (`smoke.py`) and its unit test against a stub, the unit tests of `scripts/` |
| `docs/` | Operations runbook |
| `context/` | Why the infrastructure is built this way ([Keep the Why](https://keepthewhy.com)) |

The repository's workflows under `../.github/workflows/` are owned
here as well: `ci.yml`, `docker.yml`, `deploy.yml`, `ktw-lint.yml`, `black.yml`,
`pages.yml`.

## From a clean checkout to a running cluster

Tools on the operator's machine: `tofu`, `helm`, `kubectl`,
`vultr-cli`, `make`, `curl`, `python3`. No `psql`: migrations run
inside the cluster. All commands run in this directory.

```sh
set -a; . ~/lasteverlm.env; set +a       # VULTR_API_KEY, DATABASE_ADMIN_URL, INFERENCE_API_KEY, other secrets
cp tofu/terraform.tfvars.example tofu/terraform.tfvars   # object storage tier id, region

make up            # VKE cluster and Object Storage; writes build/cluster.env
make kubeconfig    # build/kubeconfig; every later target uses it
make bucket        # sources bucket
make db-trust      # managed database: only the node addresses and this machine
make platform      # ingress-nginx, cert-manager, metrics-server; prints the load balancer IP
make db-bootstrap  # once: application role, database, pgvector (creates the Secrets first)
make deploy        # helm upgrade --install: migrations hook, then every service at TAG
make status
```

`make` alone lists every target. `make deploy TAG=<full git sha>` rolls a
specific image tag out; the release workflow does the same on a tag
`v*`. `make check` runs the static checks and the unit tests;
`make smoke` (or `URL=https://...`) runs the end-to-end smoke test against a
deployment (demo token from `DEMO_TOKEN`): login, create a notebook,
upload a text source unique to the run, wait for ready, open a
conversation, ask in it, assert a citation, read its history, delete
the notebook and the library source. Details: [docs/operations.md](docs/operations.md).

## Local development

`compose.yaml` runs the whole application on one machine: PostgreSQL 18
with pgvector, S3-compatible storage ([RustFS](https://github.com/rustfs/rustfs);
the MinIO images are no longer published), Mailpit, every service
built from this checkout, and an nginx gateway that routes like the
production ingress. Needs Docker with the compose plugin and one value
from outside, `INFERENCE_API_KEY`; the models default to the deployed
ones.

```sh
export INFERENCE_API_KEY=...   # or: set -a; . ~/lasteverlm.env; set +a
make local-up      # build, bootstrap + migrate the database, create the bucket, start; waits for health
make local-smoke   # the end-to-end smoke test against http://localhost:8080
make local-down    # stop, keep the data (local-reset also deletes the volumes)
```

| URL | What |
|---|---|
| http://localhost:8080 | the app (gateway: `/api/account`, `/api/ingest`, `/api/rag`, the rest to web) |
| http://localhost:8025 | Mailpit: every magic-link mail lands here |
| http://localhost:9001 | storage console (`local-dev-access` / `local-dev-secret-key`) |
| `localhost:5432` | PostgreSQL (`lasteverlm` / `local-dev-password`, database `lasteverlm`) |

Every port binds to 127.0.0.1. The database is set up by the same
`db/bootstrap.sh` and `db/migrate.sh` the cluster uses, so a migration
that would fail on deploy fails here first. Login: the demo token
(`local-demo-token` unless `DEMO_TOKEN` is set) or a magic link for
an address in `AUTH_ALLOWED_DOMAINS` (default `example.com`; the
admin is `admin@example.com` unless `ADMIN_EMAILS` is set). Model
names, `MODEL_PRICES`, `EMBEDDING_DIMENSION`, `TTS_MODEL`,
`TTS_VOICE`, `STT_MODEL`, `DECISION_MODEL`, `POSTGRES_PORT` and
`GATEWAY_PORT` are taken from the shell when set. The passwords and keys in `compose.yaml` are
local-only values; the deployment never reads that file (`make
secrets` generates its own). A changed `EMBEDDING_DIMENSION` needs
`make local-reset`: the vector columns are created with it.

## Contract with the services

What the chart assumes is written down as the runtime contract in
[`docs/architecture.md`](../docs/architecture.md): image names and
ports, the `/healthz` probe, the worker commands
(`lasteverlm-ingest-worker`, `lasteverlm-rag-worker`), the ConfigMap
and Secret names, the migration convention (`<service>/db/migrations`,
order infra, core, account, ingest, rag, psql variable
`:EMBEDDING_DIMENSION`). A change there is a pull request against the
architecture document first.
