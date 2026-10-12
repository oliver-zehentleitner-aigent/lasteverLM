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

- **Sign in** with a magic link sent by mail, or with an access token for development.
- **Wizard** for adding sources in three steps: what goes in (PDF, Text; Web page and Image shown as coming), how it gets in (drop or pick files, paste text), what should come out (any number of document kinds, or just chat).
- **Notebook view** in two columns. Left: sources with status and delete, and the output kinds as tiles. Right: a viewer with one tab per generated document, and the chat with `[n]` citations that open the cited passage.
- **Documents**: report (Markdown), quiz (interactive, with reveal), data table (sortable, CSV export), mind map (markmap), infographic (card grid); audio is prepared and disabled. Per document: ask about this (scopes the chat), print (report and table), share (read-only link `/s/<token>`, revocable).
- **Credit**: balance in the header, voucher dialog; a 402 anywhere opens it.
- **Admin** page for admins: users, login log, visits per day and path, voucher creation (codes shown once), allowed sign-in domains, SMTP settings with a test button, rate-limit blocks, bans (with lift), raw access log.

Status: skeleton, verified against the account service's in-memory dev server. Not yet deployed.

## Configuration

Build-time only; the app holds no secrets.

| Variable | Used | Meaning |
|---|---|---|
| `API_BASE_URL` | build | base URL of the API gateway; empty means same origin, the deployed case |
| `VITE_ADMIN_MOCK` | build | `true` runs the admin page against an in-memory mock |
| `VITE_DEV_PROXY` | dev server | forwards `/api/*` to this target so the app runs same-origin locally |

## Run locally

```sh
npm ci
cp .env.example .env.local            # VITE_DEV_PROXY=http://localhost:8000
make run                              # http://localhost:5173
```

With the account service's dev server on `:8000` (`make run-dev` in
`../account`), the login page works end to end: the sign-in link
is printed to that server's terminal, and the token `demo` signs in as
the demo user. See [`docs/development.md`](docs/development.md).

## Test

```sh
make check        # lint (oxlint), types (tsc), tests (vitest)
```

Unit tests cover the pure logic in `src/lib/`: citation markers, table
sorting and CSV, quiz answer keys, mind map outline.

## Build and deploy

```sh
make build                                   # dist/
make image API_BASE_URL=                     # = docker build -f web/Dockerfile . from the repository root
docker run --rm -p 8080:8080 lasteverlm-web  # GET /healthz -> {"status":"ok"}
```

The image serves `dist/` with nginx as a non-root user on port 8080;
`/healthz` is answered by nginx, hashed assets are cached for a year,
`index.html` is never cached, every app route falls back to it. In the
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

MIT, see [LICENSE](LICENSE).
