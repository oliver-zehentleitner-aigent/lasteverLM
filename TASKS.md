# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Items that need the maintainer are marked **[maintainer]**.

## Maintainer

- **[maintainer]** Add the agent account as collaborator with write access to this repository; branch protection on `main` with CI required and no review requirement.
- **[maintainer]** Give the agent token the `workflow` scope so CI files can land in pull requests.
- **[maintainer]** Vultr API key, object storage tier id, deployment domain and ACME e-mail, as an env file on the machine.
- **[maintainer]** Docker on the machine, agent user in the `docker` group, for local compose and image builds.
- **[maintainer]** GitHub Pages source set to GitHub Actions, for the docs site and the dashboard.
- **[maintainer]** Decide on Supabase inside the cluster (recommendation: no, see `context/architecture.md`).

## Agent A (this repository)

- Review and merge every pull request in the family until the prototype is accepted; keep `docs/architecture.md` the truth.
- Draft the walkthrough script (`docs/walkthrough.md`) once the services run end to end.

## Agent G (`core/`)

- Models, settings, `current_user` (JWT and demo token), `record_usage`, `balance_cents`, model prices with defaults, provider interfaces (`Embedder`, `LLM`), the rate-limit middleware with blocks and bans, the migration for `usage`, `access_log`, `ip_blocks`, `ip_bans`.
- Tests for price calculation, balance, token resolution, the block and ban rules.

## Agent B (`infra/`)

- Cluster, ingress-nginx with rate-limit annotations, cert-manager, namespace `lasteverlm`; Managed PostgreSQL with `vector`, Object Storage bucket; all reproducible from a clean checkout once `VULTR_API_KEY` exists.
- Helm chart `infra/chart`: API Deployments with HPA (min 2), worker Deployments for ingest and rag, web, Ingress, ConfigMap, migration Job.
- Workflows in `.github/`: `ci.yml` path-filtered, `docker.yml` to ghcr.io, `deploy.yml` on tags, `ktw-lint.yml`, `pages.yml`.
- `make secrets` from environment, `make migrate` applying infra, core, account, ingest, rag migrations in that order; the end-to-end smoke test.

## Agent C (`ingest/`)

- FastAPI service for the ingest contract; `SourceLoader` (pdf, text), `Chunker`, `Embedder`, `Storage` interfaces with one implementation each; `worker` entrypoint claiming sources from PostgreSQL.
- Usage accounting through core on every embedding call; 402 on zero balance.
- Tests for chunking and parsing, Dockerfile, `/healthz`, migrations for notebooks, sources, chunks.

## Agent D (`rag/`)

- FastAPI service for the rag contract; `Retriever`, `LLM`, `CitationMapper`, `OutputGenerator` per kind; refusal below the similarity floor; `worker` entrypoint claiming outputs from PostgreSQL; generated outputs indexed as sources; sharing.
- Usage accounting through core on every call; 402 on zero balance.
- Tests for citation mapping and the refusal path with a mocked LLM, Dockerfile, `/healthz`, migration for messages.

## Agent E (`web/`)

- Wizard, two-column notebook view, viewer with renderers, print, share page, ask-about-this; login with magic link and callback route, balance in the header, voucher redeem dialog.
- Admin panel pages: users, login log, visitor log, access log, blocks and bans, SMTP settings, allowed domains, voucher creation.
- Build-time `API_BASE_URL`, multi-stage Dockerfile with nginx, lint and typecheck in CI.

## Agent F (`account/`)

- FastAPI service for the account contract v1: magic link, JWT, `/me`, vouchers, visits, admin endpoints, SMTP settings with test mail.
- Migrations for users, magic_links, vouchers, ledger, settings, login_log, visit_log; demo user seed; admin endpoints for access log, blocks and bans (lift).
- Tests for the token flow, the allowlist, voucher atomicity and the balance; Dockerfile, `/healthz`.
- Send Agent E the exact admin response shapes.
