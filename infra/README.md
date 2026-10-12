# infra

[![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

Infrastructure of [lasteverLM](../README.md): the Vultr resources, the
Helm chart that deploys the whole application, the migration runner and
the deploy procedure. No application code. The services live in the
sibling directories; the contract they are built against is
[`docs/architecture.md`](../docs/architecture.md).

Status: skeleton, not yet applied to a real account. Planned: a compose
file for local development once Docker is available on the development
machine.

## What is in here

| Path | Purpose |
|---|---|
| `tofu/` | OpenTofu configuration: VKE cluster and Object Storage (the managed PostgreSQL is created by the maintainer and taken as an input) |
| `chart/` | The Helm chart: ConfigMap, API and worker Deployments with autoscalers, Services, Ingress with rate limiting, ClusterIssuer, migration hook |
| `platform/` | Values for the platform charts: ingress-nginx (JSON access log), cert-manager, metrics-server |
| `db/migrations/` | Infra-owned SQL (extensions); the services' own migrations are collected at deploy time |
| `db/migrate.sh`, `db/bootstrap.sh` | The migration runner the chart's hook Job executes, and the one-time database bootstrap |
| `scripts/` | `values.py` (environment to chart values), `dburls.py` (admin URL to the derived connection strings) |
| `tests/` | The family's end-to-end smoke test (`smoke.py`) and its unit test against a stub |
| `docs/` | Operations runbook |
| `context/` | Why the infrastructure is built this way ([Keep the Why](https://keepthewhy.com)) |

The repository's workflows under `../.github/workflows/` are owned
here as well: `ci.yml`, `docker.yml`, `deploy.yml`, `ktw-lint.yml`,
`pages.yml`.

## From a clean checkout to a running cluster

Tools on the operator's machine: `tofu`, `helm`, `kubectl`,
`vultr-cli`, `make`, `curl`, `python3`. No `psql`: migrations run
inside the cluster. All commands run in this directory.

```sh
set -a; . ~/lasteverlm.env; set +a       # VULTR_API_KEY, DOMAIN, ACME_EMAIL, model names, prices, secrets
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

`make` alone lists every target. `make deploy TAG=<git-sha>` rolls a
specific image tag out; the release workflow does the same on a tag
`v*`. `make check` runs the static checks and the unit tests;
`make smoke URL=https://...` runs the end-to-end smoke test against a
deployment (demo token from `DEMO_TOKEN`): login, create a notebook,
upload a text source, wait for ready, ask, assert a citation, delete
the notebook. Details: [docs/operations.md](docs/operations.md).

## Contract with the services

What the chart assumes is written down as the runtime contract in
[`docs/architecture.md`](../docs/architecture.md): image names and
ports, the `/healthz` probe, the worker commands
(`lasteverlm-ingest-worker`, `lasteverlm-rag-worker`), the ConfigMap
and Secret names, the migration convention (`<service>/db/migrations`,
order infra, core, account, ingest, rag, psql variable
`:EMBEDDING_DIMENSION`). A change there is a pull request against the
architecture document first.
