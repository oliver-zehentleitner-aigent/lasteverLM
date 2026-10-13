# Tasks

Open work across the family. One block per agent. Done items are deleted,
not ticked. Items that need the maintainer are marked **[maintainer]**.

## Maintainer

- **[maintainer]** Click through the live system over the domain: magic-link sign-in (first real mail through the SMTP Secret), PDF, URL and image sources, chat with citations, every output including audio and the mind map (katex 0.18 under it, not yet seen in a browser), share link, admin panel (SMTP read-only block and test button).
- **[maintainer]** Vultr API access-control list: add the operator machine's new public address (`infra` gets 401 until then; Helm deploys are unaffected). Afterwards infra re-runs `make db-trust` to drop the old address.
- **[maintainer]** Record the ten-minute tour (`docs/walkthrough.md`).
- **[maintainer]** VNC finding: allow agent D's read-only query on the live rows, or provide `linux_-_VNC-Server.pdf` on the VM.
- **[maintainer]** Check in a browser: audio centred in the viewer, the viewer/chat divider, the full view with Esc and ×.
- **[maintainer]** Decide on the database admin password rotation at the end.

## Agent A (root)

- Review and merge every pull request in the family until the prototype is accepted; keep `docs/architecture.md` the truth.
- Final report for the maintainer: agents, working time, model, tokens (`marketing` statistics script, rerun at the end).

## Agent B (`infra/`)

- `make db-trust` once the Vultr API answers again; VKE autoscaler stays deferred until the database's VPC attachment.

## Agent C (`ingest/`)

- Migration 0004 (contract step of the source library) in the release after the one that ships 0003: `library_source_id` not null, drop `chunks.notebook_id`/`chunks.source_id` and the moved `sources` columns.
- Fail loud on a ready source whose chunks are not searchable (pending the VNC finding).

## Agent D (`rag/`)

- VNC finding: a ready PDF is never retrieved; waiting for the maintainer's read-only rows or the file.

## Agent E (`web/`)

- Polish after the maintainer's click-through.

## Agent F (`account/`)

- Nothing open. Available for findings from the maintainer's click-through (sign-in mail, admin panel).

## Agent G (`core/`)

- Standby.
