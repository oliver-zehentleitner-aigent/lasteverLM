# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Items that need the maintainer are marked **[maintainer]**.

## Maintainer

- **[maintainer]** Repository secrets and variables for `deploy.yml` (needs admin): `KUBECONFIG_B64`, `DEMO_TOKEN`; variables `DOMAIN`, `ACME_EMAIL`, `LLM_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `MODEL_PRICES`, `S3_ENDPOINT` (see `infra/docs/operations.md`). Until then infra deploys from the machine.
- **[maintainer]** SMTP password in the admin panel; rotate the database admin password.
- **[maintainer]** Confirm the three pending-confirmation entries: uploads-only retrieval (`rag/context/retrieval.md`), a ban stays until an admin lifts it (`core/context/ratelimit.md`), the shared visitor salt (`account/context/privacy.md`).

## Agent A (root)

- Review and merge every pull request in the family until the prototype is accepted; keep `docs/architecture.md` the truth.
- Tag v0.2.0 once the audio end-to-end run on the cluster is green and the audio tile is on.

## Agent B (`infra/`)

- Deploy `45ba0fa` (core/0003 migration, audio, URL and image sources, web tiles); report pods, HPAs and the smoke test.
- `deploy.yml` first real run once the maintainer has set the repository secrets.

## Agent C (`ingest/`)

- Nothing open. Available for findings from the live run.

## Agent D (`rag/`)

- Audio end-to-end on the cluster after the deploy: create, ready, presigned URL plays, shared view, delete removes the object.
- Confirmations from the maintainer on `context/retrieval.md` (uploads-only retrieval) once they arrive.

## Agent E (`web/`)

- Flip the audio tile (`available: true` in `web/src/lib/outputs.ts`) on D's green.
- Click through URL and image sources over the real domain; findings as a PR.
- Polish after the maintainer's own click-through.

## Agent F (`account/`)

- Confirmation from the maintainer on `context/privacy.md` (shared visitor salt) once it arrives.

## Agent G (`core/`)

- Standby; confirmation from the maintainer on `context/ratelimit.md` (a ban survives the purge) once it arrives.
