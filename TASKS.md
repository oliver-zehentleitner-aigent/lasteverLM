# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Decisions that need the maintainer are marked **[maintainer]**.

## Open decisions

- **[maintainer]** Hosted Supabase (free tier) or self-hosted on the cluster. See `context/architecture.md`.
- **[maintainer]** LLM and embedding providers. Decides the embedding dimension in the schema.
- **[maintainer]** Supabase Auth login or shared demo token.
- **[maintainer]** Time budget for the MVP.

## Agent A (this repository)

- Review `docs/architecture.md` with the maintainer, then freeze the v0 API contract.
- Add each service repository to the `children` block in `.keep-the-why` once it is initialized.
- Pre-review every pull request in the family before the maintainer looks at it.
- Draft the walkthrough script (`docs/walkthrough.md`) once the services run end to end.

## Agent B (`lasteverLM-infra`)

- Create the repository, initialize Keep the Why with `parent: https://github.com/oliver-zehentleitner/lasteverLM`.
- Vultr Kubernetes cluster, ingress-nginx, TLS, one namespace `lasteverlm`.
- Deployment and Service manifests for ingest, rag and web; Secrets from environment, never committed.
- Database schema as Supabase migrations (`db/migrations/`), following the data model in `docs/architecture.md`.
- A `make deploy` or equivalent that takes a clean checkout to a running cluster.

## Agent C (`lasteverLM-ingest`)

- Create the repository, initialize Keep the Why with the parent above.
- FastAPI service implementing the ingest endpoints from `docs/architecture.md`.
- Parsers for PDF, plain text and URL; chunking with overlap; embeddings behind one interface so the provider can change.
- Dockerfile, `/healthz`, unit tests for chunking and parsing.

## Agent D (`lasteverLM-rag`)

- Create the repository, initialize Keep the Why with the parent above.
- FastAPI service implementing the rag endpoints from `docs/architecture.md`.
- Retrieval over `chunks` restricted to one notebook; answer generation with citations mapped back to source and passage; refusal when nothing relevant is found.
- Dockerfile, `/healthz`, unit tests for citation mapping with a mocked LLM.

## Agent E (`lasteverLM-web`)

- Create the repository, initialize Keep the Why with the parent above.
- Three-pane layout: sources (upload, status, delete), chat (question, answer, clickable citations), notes.
- Talks only to the two API prefixes in `docs/architecture.md`; no direct Supabase access except auth, if enabled.
- Dockerfile serving the built app, efficient layout, no polishing pass.
