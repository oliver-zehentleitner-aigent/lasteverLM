# Changelog

All notable changes to this directory are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- End-to-end smoke test (`tests/smoke.py`): demo-token login, notebook, text upload, ready, ask with citation, cleanup; runs against any URL, with a unit test against an in-process stub.
- Helm chart (`chart/`) for the whole application: ConfigMap, API Deployments with autoscalers, worker Deployments for ingest and rag, Services, Ingress with per-IP rate limiting, ClusterIssuer, migrations as a pre-upgrade hook.
- `Makefile` taking a clean checkout to a running cluster: `up`, `kubeconfig`, `bucket`, `platform`, `secrets`, `values`, `migrations`, `deploy`, `package`, `down`; `check`, `test` and `smoke` for verification.
- Migration runner (`db/migrate.sh`) that applies each service's `db/migrations/` in order infra, core, account, ingest, rag with the psql variable `EMBEDDING_DIMENSION`; `0001_extensions.sql` creates pgvector.
- OpenTofu configuration for the Vultr Kubernetes cluster, Managed PostgreSQL with pgvector and Object Storage (`tofu/`).
- Platform chart values (`platform/`): ingress-nginx with JSON access log, cert-manager, metrics-server.
- Repository workflows (`.github/workflows/`): ci, docker, deploy, ktw-lint, pages.
- Operations runbook (`docs/operations.md`) and Keep the Why context (`context/`).
