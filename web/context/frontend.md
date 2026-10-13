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

## Two columns: sources and output forms left, viewer and chat right

**Id:** f81a9fe1-d433-4e32-b143-ed29542a8722
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the family lead, 2026-10-12
**Revisit when:** the outputs API lands in the family contract, or a generated form needs more room than a tab

The workspace has two columns. Left: the sources of the notebook on top
(upload, status, delete), the output forms below as tiles (Report, Quiz,
Data table, Mindmap, Infographic, Audio). Right: an output viewer on top
with one tab per generated document, the chat with citations below.
There is no notes pane.

**Reason:** generated documents are what the product is about once the
sources are in; a tab per document keeps them side by side with the chat
that produced the questions, and the tiles make the available forms
visible without a menu. Saved answers, the one thing a notes pane would
have held, become a Report.

**Rejected alternative:** the three-pane NotebookLM shape with a notes
pane, which the first skeleton had. Rejected by the maintainer: notes
without a server side were a browser-local stopgap, and the outputs make
the pane redundant. See the superseded entry in `notes.md`.

The outputs endpoints and the per-kind content shapes are the family
lead's proposal and not confirmed in the contract yet; the client and the
viewer are built to the proposal, the per-kind renderers wait for the
confirmation (`src/components/outputs/OutputContent.tsx`).

## Generated documents are listed under Outputs, not among the sources

**Id:** 96a281ad-62e4-421e-b7f7-455077b79075
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer feedback after the 0.4.0 click-through, relayed by the family lead, 2026-10-13
**Revisit when:** generated documents stop being sources of kind `generated` in the backend, or a notebook holds so many documents that the left column needs another shape

The left column has three parts: the uploaded sources (PDF, text, web
page, image), the output forms as tiles, and a list of the generated
documents with kind, title and status. The backend is unchanged: every
ready document is still a source of kind `generated`, so the chat cites
it and "ask about this" scopes to it; the web filters that kind out of
the Sources list (`uploadedSources` in `src/lib/outputs.ts`).

**Reason:** documents shown as sources read as if they were uploads, and
the maintainer found that confusing in the click-through. What the user
added and what was generated from it are different things and get
different lists.

**Rejected alternative:** keep generated documents in the Sources list
with a "generated" badge, as before. Rejected because the badge did not
make the difference clear enough.

**Rejected alternative:** stop registering documents as sources in the
backend. Rejected because citations into documents and the scoped ask
rely on it, and the confusion is one of display only.

## Every failed request ends in a sentence, never the server's raw body

**Id:** bd6a0d24-9fce-43d0-9c17-329ab5f143b4
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12, preparing the first run against real services
**Revisit when:** the ingress or the services start returning JSON errors for every status

A failed response is shown as the service's `{"error"}` text when the
body is one; otherwise as a fixed description of the status with its
code ("The file is too large for the server (HTTP 413)"). The body of a
non-JSON error is never displayed. A failed `fetch` becomes "Cannot
reach the server".

**Reason:** the deployment answers some failures without the contract's
JSON shape: the ingress returns HTML pages for 502, 503, 504 while pods
start and for 413 on an oversized upload, and a browser offline produces
no response at all. Showing an HTML dump or a blank is what the first
real run would otherwise have produced on exactly the paths a demo hits
first (upload, first question).

**Rejected alternative:** stripping the HTML to its title ("502 Bad
Gateway"). Rejected because the nginx title tells the user nothing
useful; a description written for the situation does, and the code stays
visible for anyone debugging.
