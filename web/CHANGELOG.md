# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Admin page (users, login log, visits per day and path, voucher creation shown once, allowed domains, SMTP settings with test, rate-limit blocks, bans with lift, access log) behind `is_admin`, runnable against an in-memory mock with `VITE_ADMIN_MOCK=true`.
- API clients for the `/api/account`, `/api/ingest` and `/api/rag` prefixes of the family contract v1.1, with one fetch wrapper that forwards the bearer token, surfaces `{"error"}` responses as thrown errors and raises 401 and 402 as application events.
- Chat with clickable `[n]` citations that show the quoted passage and highlight the source; a citation into a generated document opens its tab; "ask about this" scopes the chat to the open document, shown as a chip.
- Dev-server proxy (`VITE_DEV_PROXY`) so the app runs same-origin against a local service.
- Document renderers: report (Markdown, sanitized), quiz (interactive with reveal and score), data table (sortable, CSV export), mind map (markmap, loaded on demand), infographic (card grid); audio prepared and disabled.
- Header with e-mail, credit balance and a voucher dialog that also opens on a 402 response.
- Magic-link login page with a "check your mail" state, the `/auth/callback` route that exchanges the mailed token for a JWT, and an access-token path for development.
- Makefile with `check`, `run`, `build` and `image`; multi-stage Dockerfile serving the build with nginx as a non-root user on port 8080, `/healthz` included.
- Output viewer with one tab per generated document, polling while waiting or processing, and the three actions per document: ask about this, print (report and table, print stylesheet), share (read-only link, revocable) plus delete.
- Share page `/s/<token>` rendering a shared document without login and recording a visit.
- Skeleton of the frontend: Vite, React and TypeScript, plain CSS, no UI framework.
- Two-column workspace per notebook: sources and output tiles left, viewer and chat right.
- Unit tests for citation markers, table sorting and CSV export, quiz answer keys and the mind map outline.
- Wizard for adding sources in three steps (what goes in, how it gets in, what should come out), opened for a new notebook and from the sources list.
