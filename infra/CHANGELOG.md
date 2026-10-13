# Changelog

All notable changes to this directory are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-13

### Added

- `VOUCHER_DEFAULT_CENTS` in the ConfigMap (`config.voucherDefaultCents`, default 1000 as in account); production sets 500 (5 EUR).

## [0.2.1] - 2026-10-13

### Changed

- CPU requests lowered to measured use (APIs 50m, workers 100m, web 25m); autoscaler target 80 % instead of 70 %.
- Python in `scripts/` and `tests/` formatted with black (line length 100, `pyproject.toml`); `make check` and CI run `black --check`.
- Production configuration (domain, ACME e-mail, models, prices, embedding dimension, TTS, S3 endpoint) committed in `chart/values-prod.yaml`; `make deploy` and `deploy.yml` read it, `deploy.yml` needs only the `KUBECONFIG_B64` secret (plus optional `DEMO_TOKEN`) and no repository variables; `make smoke` defaults to its domain; the chart fails the render on invalid `modelPrices` JSON.

### Removed

- `make values` and `scripts/values.py`; deploy configuration no longer comes from the environment.

### Fixed

- `deploy.yml` checks out the commit `docker.yml` built (`workflow_run.head_sha`) instead of the tag name, which could be moved in between while secrets are in scope; `GITHUB_TOKEN` limited to `contents: read`.
- `make secrets` writes the SMTP Secret with the names account reads (`SMTP_USERNAME`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS` instead of `SMTP_USER`, `SMTP_FROM`) and fails loud on `SMTP_HOST` without `SMTP_FROM_ADDRESS`; the Secret is renamed `lasteverlm-smtp-seed` → `lasteverlm-smtp`, mounted into account as before.

## [0.2.0] - 2026-10-13

### Added

- rag API and worker mount the `lasteverlm-s3` Secret (audio files go to the bucket); `TTS_VOICE` (default `ryan`) in the ConfigMap, from `make values` and the deploy workflow's repository variable.
- `compose.yaml`: local development stack (PostgreSQL 18 with pgvector, RustFS as S3 storage, Mailpit, every service, an nginx gateway routing like the ingress), set up by the same bootstrap and migration scripts as the cluster; `make local-up`, `local-down`, `local-reset`, `local-smoke`.
- `docs/operations.md`: what cert-manager did for the domain and how to check the certificate.

### Changed

- `make deploy` fails loud on a short commit SHA as `TAG`; images carry the full SHA.

### Removed

- An empty file `--aws-sigv4` that an earlier `make bucket` bug had left in the directory.

## [0.1.0] - 2026-10-12

### Changed

- Chart no longer states `runAsUser` per service; the images set numeric `USER` lines.

### Added

- End-to-end smoke test (`tests/smoke.py`): demo-token login, notebook, text upload, ready, ask with citation, cleanup; runs against any URL, with a unit test against an in-process stub.
- Helm chart (`chart/`) for the whole application: ConfigMap, API Deployments with autoscalers, worker Deployments for ingest and rag, Services, Ingress with per-IP rate limiting, ClusterIssuer, migrations as a pre-upgrade hook.
- `Makefile` taking a clean checkout to a running cluster: `up`, `kubeconfig`, `bucket`, `db-trust`, `platform`, `secrets`, `db-bootstrap`, `values`, `migrations`, `deploy`, `package`, `down`; `check`, `test` and `smoke` for verification. Database URLs with `sslmode=verify-full` against the mounted CA; generated application secrets; trusted-IP list on the managed database; TLS-only ingress with HSTS.
- Migration runner (`db/migrate.sh`) that applies each service's `db/migrations/` in order infra, core, account, ingest, rag with the psql variable `EMBEDDING_DIMENSION`; `0001_extensions.sql` creates pgvector.
- OpenTofu configuration for the Vultr Kubernetes cluster and Object Storage (`tofu/`); the managed PostgreSQL is an input (`DATABASE_ADMIN_URL`) with a bootstrap Job for role, database and pgvector; service migrations run under the application role.
- Platform chart values (`platform/`): ingress-nginx with JSON access log, cert-manager, metrics-server.
- Repository workflows (`.github/workflows/`): ci, docker, deploy, ktw-lint, pages.
- Operations runbook (`docs/operations.md`) and Keep the Why context (`context/`).
