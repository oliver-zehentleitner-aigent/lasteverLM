# web

[![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

The frontend of lasteverLM: turn sources into documents and talk about
both. One static single-page app served by nginx, talking to the
`/api/account`, `/api/ingest` and `/api/rag` prefixes of the
[architecture](../docs/architecture.md), laid out as described in the
[UI spec](../docs/ui.md). This directory is the `web` service of the
repository; see the [root README](../README.md) for the whole system.

## What it does

- **Light and dark**: a theme toggle in the header and in Settings, following the system by default; the choice follows the user across browsers.
- **German and English**: the interface follows the user's language setting, the browser's language before login.
- **Sign in** with a magic link sent by mail (an address without access is told so), or with the code printed under the link in the same mail, pasted on the sign-in page (format checked while typing, shown or hidden).
- **Wizard** for adding sources in three steps: what goes in (PDF, Text, Web page, Image, Audio as MP3, WAV or, converted first, M4A, AAC, OGG, Opus, FLAC, WEBM or MP4), how it gets in (drop or pick files, paste text, enter a URL), what should come out (any number of document kinds, or skip to just chat; for a new notebook only, adding to an existing one ends after the sources).
- **Notebook view** in two columns. Left: the uploaded sources with status and delete and a checkbox each (the chat and new documents use only the ticked ones, remembered per notebook), the output formats as tiles (a click selects, a Create button starts the job), and the generated documents (kind, title, status; open and delete). Right: a viewer with one tab per generated document, and the chat in tabs, one per conversation (new with "+", closed and deleted with "×"), with `[n]` citations that open a provenance panel (source, page, chunk position, similarity, the chunk verbatim with the matching sentence marked; "open in source" opens the source in a new tab, a PDF on the cited page).
- **Documents**: report (Markdown), quiz (interactive, with reveal), data table (sortable, CSV export), mind map (markmap), infographic (card grid), audio (player that re-fetches its presigned URL once it expires), decision (a question weighed against the sources: the model's answer as a gauge, bars or a scale, the evidence for and against, what the sources do not say). Per document: ask about this (scopes the next question in the active chat tab), print (report and table), share (read-only link `/s/<token>`, revocable), full view (the document over the whole window, chat behind a toggle, Esc or × to leave). Draggable dividers set the split between document and chat and the widths of the three columns, remembered per browser; long tab bars scroll.
- **Settings** (`/settings`): interface language, language of generated documents, voice for audio, days in the trash, how PDFs are read; preselected wherever they apply.
- **Output options**: language for every format, voice and speed for audio, shown under the format tiles and remembered on the document.
- **Library** (`/library`): every upload, URL and output once, in one table with a view selector (all, sources, outputs) and filters by kind, notebook and name (an output opens in its notebook, or read-only once that is deleted, and is usable as a source in another notebook); each row with the notebooks it is in; an upload opens in a new tab (its address, or its presigned preview); ticked rows can start a notebook, be added to one (only the missing ones) or be deleted into a trash after a confirmation naming the notebooks, restore or purge from there; the wizard adds entries from it, removing a source in a notebook only detaches it, and citations to a source no longer in the notebook show "source removed".
- **Credit**: balance in the header, voucher dialog; a 402 anywhere opens it.
- **Admin** pages for admins and, read-only, for viewers (role per user on the Users page, where an admin can also delete a user after typing out the address, viewer domains on the Access page), under `/admin` with a sub-navigation (Overview, Users, Access, Credits, Security, Visits, Mail, System), each with its own URL and loading only its own data: an overview with headline numbers and charts of the last 30 days (recharts, loaded only on that page) of numbers from all three services (each loads on its own, so one service down does not blank the rest), users, login log, sign-in attempts (allowed and refused, with IP), visits per day and path, voucher creation (5 EUR by default, codes shown once) with the list of issued vouchers (open ones deletable), allowed sign-in (domains and single addresses, added and removed one at a time), SMTP settings read-only (configured in the deployment) with a test button, the rate-limit rule (as a sentence, five numbers editable, the ban cap among them, reset to defaults), rate-limit blocks, bans (with lift), raw access log.

Status: deployed at https://lasteverlm.zehentleitner.co with the rest of the stack; what changed per release is in [CHANGELOG.md](CHANGELOG.md).

## Configuration

Build-time only; the app holds no secrets.

| Variable | Used | Meaning |
|---|---|---|
| `API_BASE_URL` | build | base URL of the API gateway; empty means same origin, the deployed case |
| `VITE_ADMIN_MOCK` | build | `true` runs the admin page against an in-memory mock |
| `VITE_DEV_PROXY` | dev server | forwards `/api/*` to this target so the app runs same-origin locally |
| `CSP` | image build | `enforce` (default: the full policy), `report` (the full policy as `Content-Security-Policy-Report-Only`: the browser lists what it would block, blocks nothing) or `off` (`frame-ancestors 'none'` only); written by `scripts/csp.mjs` with the sha256 of the inline theme script taken from the built `index.html` |
| `CSP_MEDIA_SRC` | image build | where images and audio may load from besides the app (presigned object-storage URLs); default `https:` |

## Run locally

```sh
cp .env.example .env.local            # VITE_DEV_PROXY=http://localhost:8000
make run                              # installs with npm ci, then http://localhost:5173
```

`make install` runs `npm ci` on its own; `check`, `run` and `build`
depend on it, so every target works on a fresh checkout.

With the account service's dev server on `:8000` (`make run-dev` in
`../account`), the login page works end to end: the sign-in link
is printed to that server's terminal. The token `demo` is accepted as a
Bearer token (no sign-in form takes it); see
[`docs/development.md`](docs/development.md).

## Test

```sh
make check        # lint (oxlint), types (tsc), tests (vitest)
```

Unit tests cover the pure logic in `src/lib/`: citation markers, table
sorting and CSV, quiz answer keys, mind map outline, the source forms
and tile notes.

Against a deployment, `make e2e URL=https://host` checks that the
frontend and the three API prefixes answer `/healthz` through the
ingress; it opens no browser and writes nothing.

## Build and deploy

```sh
make build                                   # dist/
make image API_BASE_URL=                     # = docker build -f web/Dockerfile . from the repository root
docker run --rm -p 8080:8080 lasteverlm-web  # GET /healthz -> {"status":"ok"}
docker build -f web/Dockerfile --build-arg CSP=report .   # the full policy, report only (check: make web-csp-check in infra/)
```

The image serves `dist/` with nginx as a non-root user on port 8080;
`/healthz` is answered by nginx, hashed assets are cached for a year,
`index.html` is never cached, every app route falls back to it, and
every response carries `nosniff`, `no-referrer` and a no-framing
policy. In the
cluster, ingress routes `/` here and `/api/*` to the services (see the
deployment section of the architecture).

## Layout of the code

```text
src/
├── api/          one module per API prefix, one fetch wrapper, token storage
├── components/   login, header, wizard, two-column workspace, viewer, share page, admin
│   └── outputs/  one renderer per document kind
├── hooks/        route and async-state helpers
├── lib/          pure functions, unit-tested
└── styles.css    plain CSS, light and dark, print
```

- How it is built and tested: [`docs/`](docs/). Why it is built this way: [`context/`](context/).
- [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), [`CHANGELOG.md`](CHANGELOG.md)

## License

MIT, see the repository's [LICENSE](../LICENSE).
