# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Admin panel split into pages under `/admin` with a sub-navigation: Overview (`/admin`), Users, Access, Credits, Security, Visits, Mail (`/admin/<page>`). Each page mounts only its sections, so it loads only its own data; an unknown admin page opens the overview.

## [0.4.1] - 2026-10-13

### Changed

- Notebook view: generated documents are listed under Outputs in the left column (kind, title, status; a click opens the tab, × deletes) instead of among the sources; the Sources list shows only uploads. A citation into a generated document scrolls to its row there.

## [0.4.0] - 2026-10-13

### Added

- Chat tabs: one tab per conversation of the notebook, "+" for a new one, "×" closes one after a confirmation and deletes its messages; the last tab closed is replaced by a fresh one, and a notebook without conversations gets one when the chat opens. Every question carries the active tab's `conversation_id`; "ask about this" scopes the next question in the active tab.
- Admin page: sign-in attempts (time, e-mail, IP, allowed or refused), newest first, next to the login log.
- Admin page: "Rate limit and bans" above the blocks and bans: the rule in force as a sentence, the four editable numbers (requests per minute, block minutes, strikes to a ban, strike window in hours) with core's bounds checked before saving, "Reset to defaults", the environment-only ban cap and retention as text, and a line on the coarse ingress limit in front.
- Admin vouchers: open vouchers can be deleted from the list (with a confirmation; the code stops working); redeemed ones have no button.

## [0.3.0] - 2026-10-13

### Added

- Admin overview at the top of the admin page: users, logins, vouchers, credit and usage cost (account), sources, ingest jobs, chunks and stored bytes (ingest), notebooks, chat messages, documents by kind and status, document jobs and shared documents (rag). Each service's group loads on its own and shows its own error; failures, blocks and bans are highlighted when not zero.
- Admin vouchers: list of issued vouchers (amount, created by and when, status, redeemed by and when), newest first, refreshed after creating; the codes are never listed.
- Admin page: allowed sign-in as two lists, domains and single addresses, each with add and remove per entry; the hint states that with both empty no one but the configured admins can sign in.
- `ApiError.code`: the service's machine-readable `code` next to `error`, when it sends one.

### Changed

- Admin vouchers: the create form defaults to 5 EUR.
- Login page: a refused address (403 `not_allowed`) shows "This address has no access to lasteverLM." instead of the "check your mail" step; the tagline reads "Provide documents, ask questions, get cited answers."

### Removed

- Admin page: the whole-list domain editor and its `PUT /admin/settings/domains`, gone in account.

## [0.2.1] - 2026-10-13

### Changed

- Admin page: SMTP is shown read-only (host, port, username, from address, STARTTLS) with the configuration's origin and the test button; the edit form and its PUT are gone, because the account service takes SMTP from the environment only. "Not configured" when the host is empty; the test reports the address it went to.

### Security

- `katex` (transitive through `markmap-lib`) pinned to `^0.18.2` with an npm `overrides` block, for GHSA-238p-pmpm-9mq7 (prototype pollution bypassing the trust restrictions; low).

## [0.2.0] - 2026-10-13

### Added

- Security headers on every response of the web image: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (a share link's token never leaves in a referrer), `X-Frame-Options: DENY` and `frame-ancestors 'none'`.
- Audio player that keeps its URL across output polls and fetches a fresh presigned URL once when the old one has expired.

### Changed

- Sources list: a source the worker retries shows the error of the last attempt ("Retrying after: …") instead of a bare "processing"; the empty list names all four source kinds.
- Admin page: the bans section states how long a ban holds (until lifted, at most 90 days).
- Audio is an active document kind: the tile creates an audio overview, played in the viewer and on the share page.
- Wizard: Web page (enter a URL) and Image (PNG, JPEG, WebP, GIF) are active source types.
- Disabled tiles show "Soon." from one place instead of in their descriptions, so enabling a form is a one-line change.

## [0.1.0] - 2026-10-12

### Added

- Admin page (users, login log, visits per day and path, voucher creation shown once, allowed domains, SMTP settings with test, rate-limit blocks, bans with lift, access log) behind `is_admin`, runnable against an in-memory mock with `VITE_ADMIN_MOCK=true`.
- API clients for the `/api/account`, `/api/ingest` and `/api/rag` prefixes of the family contract v1.1, with one fetch wrapper that forwards the bearer token, surfaces `{"error"}` responses as thrown errors and raises 401 and 402 as application events.
- Chat with clickable `[n]` citations that show the quoted passage and highlight the source; a citation into a generated document opens its tab; "ask about this" scopes the chat to the open document, shown as a chip.
- Dev-server proxy (`VITE_DEV_PROXY`) so the app runs same-origin against a local service.
- Document renderers: report (Markdown, sanitized), quiz (interactive with reveal and score), data table (sortable, CSV export), mind map (markmap, loaded on demand), infographic (card grid); audio prepared and disabled.
- Header with e-mail, credit balance and a voucher dialog that also opens on a 402 response.
- Magic-link login page with a "check your mail" state, the `/auth/callback` route that exchanges the mailed token for a JWT, and an access-token path for development.
- Makefile with `check`, `run`, `build`, `image` and `e2e` (reachability of a deployment through its ingress); multi-stage Dockerfile serving the build with nginx as a non-root user on port 8080, `/healthz` included.
- Output viewer with one tab per generated document, polling while waiting or processing, and the three actions per document: ask about this, print (report and table, print stylesheet), share (read-only link, revocable) plus delete.
- Share page `/s/<token>` rendering a shared document without login and recording a visit.
- Skeleton of the frontend: Vite, React and TypeScript, plain CSS, no UI framework.
- Two-column workspace per notebook: sources and output tiles left, viewer and chat right.
- Unit tests for citation markers, table sorting and CSV export, quiz answer keys and the mind map outline.
- Wizard for adding sources in three steps (what goes in, how it gets in, what should come out), opened for a new notebook and from the sources list.

### Changed

- Grouped citation markers in an answer, such as `[1, 2, 5]`, become one clickable marker per number; before, only single markers `[1]` were recognised.

- Failed requests always show a readable message: the service's error text, or a description of the status for responses without one (ingress 502/503/504, 413, network failure); HTML error pages are never shown.

- `make check`, `make run` and `make build` install dependencies first through `make install`, so they work on a fresh checkout.
