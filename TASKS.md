# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Items that need the maintainer are marked **[maintainer]**.

## Maintainer

- **[maintainer]** Create the six empty upstream repositories (MIT, Python gitignore): `lasteverLM-core`, `-account`, `-infra`, `-ingest`, `-rag`, `-web`. Until then every agent works in a local repository with remotes preset.
- **[maintainer]** Give the agent token the `workflow` scope so CI files can land in pull requests.
- **[maintainer]** Vultr API key and the deployment domain, as an env file on the machine.
- **[maintainer]** Review and merge PR #1 (this skeleton and architecture v1).

## Agent A (this repository, core)

- `lasteverLM-core`: models, settings, `current_user`, `record_usage`, `balance_cents`, model prices, provider interfaces, the `usage` migration. Tag `v0.1.0` so services can pin it.
- Pre-review every pull request in the family before the maintainer looks at it.
- Draft the walkthrough script (`docs/walkthrough.md`) once the services run end to end.

## Agent B (`lasteverLM-infra`)

- Cluster, ingress-nginx, cert-manager, namespace `lasteverlm`; Managed PostgreSQL with `vector`, Object Storage bucket; all reproducible from a clean checkout once `VULTR_API_KEY` exists.
- Deployment and Service manifests for account, ingest, rag, web; Ingress with the three API prefixes and `/` to web.
- `make secrets` from environment, `make migrate` applying core, account, ingest, rag migrations in that order.

## Agent C (`lasteverLM-ingest`)

- FastAPI service for the ingest contract v1; `SourceLoader` (pdf, text), `Chunker`, `Embedder`, `Storage` interfaces with one implementation each; `worker` entrypoint running in-process for now.
- Usage accounting through core on every embedding call; 402 on zero balance.
- Tests for chunking and parsing, Dockerfile, `/healthz`, migrations for notebooks, sources, chunks.

## Agent D (`lasteverLM-rag`)

- FastAPI service for the rag contract v1; `Retriever`, `LLM`, `CitationMapper` with one implementation each; refusal below the similarity floor.
- Usage accounting through core on every call; 402 on zero balance.
- Tests for citation mapping and the refusal path with a mocked LLM, Dockerfile, `/healthz`, migration for messages.

## Agent E (`lasteverLM-web`)

- Three-pane layout, login with magic link and callback route, balance in the header, voucher redeem dialog.
- Admin panel pages: users, login log, visitor log, SMTP settings, allowed domains, voucher creation.
- Build-time `API_BASE_URL`, multi-stage Dockerfile with nginx, lint and typecheck in CI.

## Agent F (`lasteverLM-account`)

- FastAPI service for the account contract v1: magic link, JWT, `/me`, vouchers, visits, admin endpoints, SMTP settings with test mail.
- Migrations for users, magic_links, vouchers, ledger, settings, login_log, visit_log; demo user seed.
- Tests for the token flow, the allowlist, voucher atomicity and the balance; Dockerfile, `/healthz`.
- Send Agent E the exact admin response shapes.
