# Frontend

## No router and no UI framework, plain CSS

**Id:** 4c6ad39c-9dac-46eb-b56e-919edc47f1e4
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12; family lead's stack approval of the same day
**Revisit when:** the app grows past a handful of routes or needs components a CSS file cannot carry

Routing is a small hook over `history.pushState` with three routes (home,
`/auth/callback`, `/admin`); styling is one plain CSS file with
variables for light and dark. Runtime dependencies are React and
React DOM only.

**Reason:** the family rule is to keep dependencies minimal, and the MVP
is time-boxed with an explicit "no polishing pass". Three routes do not
justify a router, and a component library would cost more in learning
its conventions than it saves in a layout this small.

**Rejected alternative:** react-router plus Tailwind or a component kit.
Rejected as dependency and build weight for no visible gain at this
size. Tailwind was explicitly left to this repository's call and declined
for the same reason.

## 401 and 402 are application events, raised once in the fetch wrapper

**Id:** 627f9553-df43-476c-b8ad-337c13ccded8
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12; API contract v1 (401 unauthenticated, 402 credit exhausted)

`src/api/client.ts` dispatches an event on a 401 or 402 response before
throwing the usual `ApiError`. The app shell listens once: 401 clears
the token and shows the login page, 402 opens the voucher dialog. Panes
only show the error text.

**Reason:** both statuses change the state of the whole app, not of the
request that hit them. Handling them per call would repeat the same two
branches in every pane and drift apart over time.

**Rejected alternative:** checking the status in each pane's error
handler. Rejected as duplication; the contract defines the two statuses
globally, so one place in the client matches the contract's shape.

## Admin panel behind one interface with an in-memory mock

**Id:** e4c2c795-9b9b-488d-ae08-99b596434f74
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12, on the family lead's request to build the admin pages before the account service exists
**Revisit when:** the account service is deployed and the admin endpoints are verified against it

`src/api/admin.ts` defines `AdminApi`, implemented twice: against
`/api/account/admin/*` and as an in-memory mock selected at build time
by `VITE_ADMIN_MOCK=true`. The pages import the interface only.

**Reason:** the account service is built in parallel and its admin
endpoints were still provisional when the pages were written. The
interface lets the UI be finished and reviewed now; when the shapes
move, one file changes.

**Rejected alternative:** a request-interception mock (service worker) or
waiting for the service. Interception adds a dev dependency and hides
which calls are real; waiting would serialize two agents that are meant
to work in parallel.
