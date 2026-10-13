# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


### Changed

- Admin Overview redesigned: the heading with one meta line (build and service health with status dots, linked to System) instead of the version link, one row of six equal KPI tiles instead of three groups of 18, an attention strip only for what needs an action (bans, blocks, a service down or without a version) as the only red on the page, failures without an admin page as muted details. The charts share one time range (7 days while the data is young, else 30, with a toggle) in a two-column grid of equal cards paired by topic; a chart without data is listed on one line instead of drawn empty.
- Wizard: after a failed upload (a storage outage now answers 503) the files that went in leave the list and the rest stays selected for a retry, with a line saying how many are left.
- Library trash: "settings" in the note links to the settings page, scrolled to and focused on the trash-days field.
- Admin Credits: new voucher codes are compact chips with a copy button each and "copy all" for several ("copied" for a second; the text is selected when the clipboard API is not available), placed next to the create form when there is room.

## [0.6.1] - 2026-10-13

### Added

- Demo sources: a "demo" badge on the example sources a new account starts with (library, trash, the wizard's library picker, the source list); the library page polls while entries are processing; an empty chat in a notebook with demo sources offers a first question to ask.
- Admin System page (`/admin/system`, from `GET /api/account/admin/system`): per service version, commit and health, the cluster's pods and deployments, or a note for a local run; the overview shows the build under its heading. The build is the tooltip of the brand in the header for everyone (from the public `healthz`).
- Voice sample: a "sample" button next to the voice in the audio options and in the settings plays a short sentence pair in that voice, speed and language (`POST /api/rag/outputs/voice-sample`, fetched on click only).
- The interface in German and English: every visible string goes through `t()` with one map per language (`src/i18n/`, the German map typed against the English keys, so a missing key fails the typecheck); `ui_language` decides, the browser's language before login; dates, numbers and amounts are formatted in that language. Messages from the services stay in English.
- PDF capture mode: the wizard offers Auto, Text or Vision for PDF uploads with a line on each (cost included), preset from the `pdf_capture` preference and sent as `capture`; the settings page sets the default; the source list and the library show the mode on PDF entries.
- Library trash: a Trash view next to the sources lists deleted entries with when they are purged; restore puts one back in the library (in no notebook), "delete for good" removes it at once after a confirmation. The settings page sets the days an entry stays there (`trash_days`, empty for 14).

### Changed

- Wizard: "From library" is the first tile.
- Library delete moves the entry to the trash instead of removing it; the confirmation says so.

## [0.6.0] - 2026-10-13

### Added

- Column dividers between the notebook list, the left column and the right column: drag or arrow keys, widths remembered per browser, double-click or Home for the default, minimum widths kept.
- Output options under the format tiles, from rag's `GET /outputs/options`: language for every kind, voice (grouped female and male) and speed for audio; preset from the user's preferences, sent as `options` with only the keys the kind takes. The wizard uses the preferences too. The viewer and the shared page show what a document was made with.
- Settings page `/settings` (header link): interface language, language of generated documents, voice for audio, saved through `PUT /api/account/me/preferences`.
- Citation provenance panel: a click on `[n]` shows source and kind, page, chunk position ("chunk 12 of 43"), the similarity to the question as a number and a bar, and the full chunk text with the sentence closest to the cited statement marked; "open in source" as before. The citation list shows page and similarity inline. Older citations get position and full text from `GET /api/rag/chunks/{id}` where the chunk still exists.
- Admin overview charts of the last 30 days under the headline numbers: cost and credit granted per day, logins and visits, chat messages and documents, documents by kind, sources added per day by kind, cost by model, top users by usage. Each chart loads on its own; recharts 3.10.1 in its own chunk, loaded only on the overview, behind an error boundary; colours from the theme (`--chart-1` … `--chart-6`, light and dark).
- Chat height presets 1x, 2x, 3x at the right end of the chat tab bar: the chat gets 15, 30 or 45 % of the right column. They set the divider's ratio (stored the same way), the matching preset is highlighted, a drag moves off it.
- Admin Users: a "Granted" column (the user's ledger sum) next to used and balance; the overview's "Credit granted" tile links to the Users page and "Vouchers open" to Credits.

### Fixed

- The document and chat tab bars scroll sideways when the tabs do not fit (columns no longer grow with them); the active tab scrolls into view, the mouse wheel scrolls the bar, arrows, Home and End move between tabs. In the chat bar "+" stays in place.

## [0.5.1] - 2026-10-13

### Fixed

- Mind map: the SVG fills its container instead of a fixed 60vh, and markmap re-fits on every size change of it (full view, divider, window resize) on the next frame; labels use the theme's text colour at normal weight instead of markmap's dark grey, which was unreadable on the dark theme.
- Shared page: as tall as the window; the mind map and the table get the full width (the mind map was clipped and zoomed in a 56rem column), reading kinds stay in a centred column, the audio player is centred.

### Changed

- Output format: the Create button sits at the right edge under the tiles, the hint on its left.

## [0.5.0] - 2026-10-13

### Added

- Library page `/library` (header link): every upload and URL of the user with kind, status, size, date and the notebooks it is in (links), filter by kind and name, delete from every notebook after a confirmation that names them.
- Wizard: "From library" adds entries not yet in this notebook; adding a file or URL that is already in the notebook says so instead of adding it twice.
- Chat: a citation whose source is no longer in the notebook is marked "source removed".
- Divider between document viewer and chat: drag or arrow keys to change the split, remembered per browser (localStorage, guarded), double-click or Home to reset.
- Full view for the open document: over the whole window, the viewer's tabs kept, the chat behind a "chat" toggle (also opened by "ask about this"); Esc closes the chat first, then the full view, × leaves too, and the focus returns to the full-view button.

### Changed

- Removing a source in a notebook detaches it (it stays in the library), and deleting a notebook detaches its sources; the confirmations say so.
- Notebook view: the tiles are "Output format"; a click (or Enter) only selects a format, highlighted and kept while the notebook is open, and a Create button below starts the job. Create is disabled without a selection or without a ready source, with a hint saying which.
- Viewer: the audio player is centred in the pane, horizontally and vertically.
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
