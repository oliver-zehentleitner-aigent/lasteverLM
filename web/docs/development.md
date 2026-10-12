# Development

## Prerequisites

Node 24 and npm. For the UI shell alone no backend is needed: the admin
page runs against a mock with `VITE_ADMIN_MOCK=true`, and the workspace
shows the API's error messages when the prefixes are not reachable.

## Local run

```sh
cp .env.example .env.local
make run          # npm ci if needed, then the vite dev server on http://localhost:5173
```

`.env.local` sets `VITE_DEV_PROXY`; the dev server then forwards `/api/*`
to that target, so the app runs same-origin exactly as behind the
cluster's ingress and `API_BASE_URL` stays empty. Without the proxy,
`API_BASE_URL` must point at a gateway that allows CORS from the dev
server.

## Against the account service

The account service (`../account`) has an in-memory dev mode that needs
no PostgreSQL (see its README; `make run-dev` on port 8000). With `VITE_DEV_PROXY`
pointing at it:

- the login page sends the link request; the service prints the sign-in
  link to its terminal, open it in the browser to land on
  `/auth/callback` and be signed in;
- the token `demo` on "Have an access token?" signs in as the demo user
  (no admin);
- the first address in the service's allowed list becomes admin and sees
  the admin page.

The ingest and rag prefixes are not served by that process; the sources
and chat panes show the resulting errors until those services run behind
the same proxy target.

## Checks

| Command | What |
|---|---|
| `make install` | `npm ci`, skipped when `node_modules` is current |
| `make check` | install, then the three below; what CI runs |
| `npm run lint` | oxlint, warnings are errors |
| `npm run typecheck` | `tsc -b` over app and config |
| `npm test` | vitest, the pure functions in `src/lib/` |
| `make build` | production build into `dist/` |

## Container

```sh
make image API_BASE_URL=          # docker build -f web/Dockerfile . from the repository root
docker run --rm -p 8080:8080 lasteverlm-web
curl http://localhost:8080/healthz
```

nginx runs unprivileged on 8080, serves `dist/`, answers `/healthz`
itself, caches hashed assets for a year and never caches `index.html`,
so a new image is picked up on the next load. All app routes
(`/`, `/admin`, `/auth/callback`, `/s/<token>`) fall back to `index.html`.

## Adding to the API client

The contract lives in `../docs/architecture.md`. Mirror a change there in
`src/api/types.ts` and the prefix module it belongs to; nothing else
calls `fetch`. A new admin endpoint is added to the `AdminApi` interface
and to both implementations, HTTP and mock.

## Adding a document kind

One renderer in `src/components/outputs/`, one case in
`OutputContent.tsx`, one entry in `OUTPUT_FORMS` (`src/lib/outputs.ts`)
with its label and whether it is printable. Pure logic the renderer
needs (sorting, scoring, conversion) goes to `src/lib/` with a test.
