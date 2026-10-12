# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Items that need the maintainer are marked **[maintainer]**.

## Maintainer

- **[maintainer]** DNS: A record for the deployment domain pointing at the load balancer, once infra reports the address.
- **[maintainer]** Repository secrets and variables for `deploy.yml` (needs admin): `KUBECONFIG_B64`, `DEMO_TOKEN`; variables `DOMAIN`, `ACME_EMAIL`, `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `MODEL_PRICES`, `S3_ENDPOINT` (see `infra/docs/operations.md`). Until then infra deploys from the machine.
- **[maintainer]** SMTP password in the admin panel; rotate the database admin password.
- **[maintainer]** Confirm: a ban stays until an admin lifts it, also past the 30-day retention (`core/context/ratelimit.md`, pending-confirmation).

## Agent A (root)

- Review and merge every pull request in the family until the prototype is accepted; keep `docs/architecture.md` the truth.
- Draft the walkthrough script (`docs/walkthrough.md`) once the services run end to end.
- Docs site (mkdocs) on Pages next to the dashboard.

## Everyone, after core is merged

- Replace `contracts.py` with imports from `lasteverlm_core` (account, ingest, rag), install core by path per `core/README.md`.
- Migration files: no `begin`/`commit` of their own, the runner wraps each file in one transaction (ingest, rag).
- Drop `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE` copies inside service directories; the root files apply.

## Agent G (`core/`)

- Models, settings, `current_user` (JWT and demo token), `record_usage`, `balance_cents`, model prices with defaults, provider interfaces (`Embedder`, `LLM`), the rate-limit middleware with blocks and bans, the migration for `usage`, `access_log`, `ip_blocks`, `ip_bans`.
- Tests for price calculation, balance, token resolution, the block and ban rules.

## Agent B (`infra/`)

- `deploy.yml`: `secrets` is not available in `if`; move `DEMO_TOKEN` into the step env.
- First real `make up` through `make deploy` once the Vultr values exist; fix what the real run turns up.
- Local development: `compose.yaml` with Postgres (pgvector), MinIO, Mailpit and the services, once Docker is on the machine.

## Agent C (`ingest/`)

- URL loader (next source kind), then image loader.
- `make install` target; README line for it.

## Agent D (`rag/`)

- Audio output once the inference platform's text-to-speech is confirmed.
- Chunker from core once it is there.

## Agent E (`web/`)

- Fix the token comment, drop `web/LICENSE`, switch the admin page off the mock by default.
- Polish only what the first real run shows.

## Agent F (`account/`)

- `make install` target; README line for it.
- Retention for core's access-log tables, or confirm core does it.
