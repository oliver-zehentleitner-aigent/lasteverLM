# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Items that need the maintainer are marked **[maintainer]**.

## Maintainer

- **[maintainer]** Final walkthrough on 2026-10-14 on v0.10.0, then the handover; `make demo-reset` before inviting the other testers (its script waits for the maintainer's go in agent B's session).
- **[maintainer]** Vultr API access-control list: add the operator machine's current address; then infra re-runs `make db-trust`.

## Agent A (root)

- Review and merge every pull request in the family until the prototype is accepted; keep `docs/architecture.md` the truth.
- Final report for the maintainer: agents, working time, model, tokens (`marketing` statistics script, rerun at the end).

## Agent B (`infra/`)

- `make db-trust` once the Vultr API answers again; VKE autoscaler stays deferred until the database's VPC attachment.

## Agent C (`ingest/`)

- Migration 0004 (contract step of the source library) in the release after the one that ships 0003: `library_source_id` not null, drop `chunks.notebook_id`/`chunks.source_id` and the moved `sources` columns.


## Agent D (`rag/`)

- Record the VNC incident as resolved (cause inferred: the upload race fixed in ingest #182, or the 0.5.0 remodel); add the embedder guard against zero-norm or non-finite vectors with agent G.

## Agent E (`web/`)

- Polish after the maintainer's click-through.

## Agent F (`account/`)

- Nothing open. Available for findings from the maintainer's click-through (sign-in mail, admin panel).

## Agent G (`core/`)

- Standby.
