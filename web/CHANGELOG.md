# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Security headers on every response of the web image: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` (a share link's token never leaves in a referrer), `X-Frame-Options: DENY` and `frame-ancestors 'none'`.
- Audio player that keeps its URL across output polls and fetches a fresh presigned URL once when the old one has expired.

### Changed

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
