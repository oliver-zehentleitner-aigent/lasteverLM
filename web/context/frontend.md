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

Since documents belong to the user (2026-10-14), one made in another
notebook can be added from the library; it is then listed among the
sources with the kind "Generated", because the user added it here like
an upload. The line runs between made here and added here, not by kind:
`uploadedSources` drops only the generated sources of this notebook's
own documents.

## An output format is selected first, a Create button starts the job

**Id:** 50dbbbc8-0fe9-4037-a53c-cdaac2bdbe3f
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer request after a click-through, relayed by the family lead, 2026-10-13
**Revisit when:** creating a document becomes free, or users ask for several formats in one go

The output tiles are a single choice: a click or Enter selects a
format, and only the Create button under them starts a generation. The
button is disabled without a selection or while no upload of the
notebook is ready, and a hint says which (`createBlocker` in
`src/lib/outputs.ts`).

**Reason:** the maintainer did not want a click on a tile to start a
job at once. The why was not stated; inferred: a generation costs
credit and cannot be undone, so it should take a deliberate second
step, and a job without a ready source has nothing to work on.

**Rejected alternative:** one click on a tile creates the document, as
before. Rejected by the maintainer.

## Full view covers the whole window, the chat sits behind a toggle

**Id:** 86a0a61a-7bdd-47af-af5d-be2a144c0192
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request for tall documents relayed by the family lead, 2026-10-13; window versus column and the toggle were left to this directory's call
**Revisit when:** a browser run shows the toggle is missed, or the left column is needed while reading a document in full view

The full view puts the open document over the whole window, with the
viewer's tabs kept. The chat is not visible there; a "chat" toggle in
the bar at the top right opens it in the lower part, and "ask about
this" opens it as well. Esc closes that chat first, then the full view.

**Reason:** the documents that need the full view, the mind map and wide
tables, need width as much as height, and the viewer's own tabs still
switch between documents, so the left column has nothing the full view
needs. A toggle is predictable with mouse, keyboard and touch alike.

**Rejected alternative:** full view over the right column only. Rejected
because it keeps a third of the width for sources and tiles that are
not used while reading.

**Rejected alternative:** the chat sliding up when the document is
scrolled to the end. Rejected for now: it depends on scroll behaviour
per renderer (the mind map does not scroll, it pans), and it could not
be tried in a browser here; the request allowed the toggle as the
fallback.

## Charts with recharts, pinned, in a chunk of their own

**Id:** 77802863-fb97-4706-a8b9-e6e7420382bb
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request for a statistics page relayed by the family lead, 2026-10-13 (an established React library, a pinned version, no hand-rolled SVG); the choice of library was this directory's call
**Revisit when:** recharts drops React 19 support or a major release changes its API, or the admin chunk becomes too large to load comfortably

The admin overview draws its charts with recharts 3.10.1, pinned exactly
in `package.json`. The charts live in `components/admin/StatsCharts.tsx`,
loaded with `React.lazy` only on that page, behind an error boundary;
colours come from the theme's `--chart-1` … `--chart-6` tokens, read
once per mount because recharts writes them into SVG attributes where
CSS variables do not resolve.

**Reason:** recharts is made of React components, so a chart reads like
the rest of the code; it brings bars, lines, areas, donuts, stacked and
horizontal bars, responsive containers and load animations out of the
box, and declares React 19 as a peer. Its weight (about 110 kB gzipped)
is paid only by admins opening the overview.

**Rejected alternative:** Chart.js through a React wrapper. Rejected
because it draws on a canvas with an imperative API next to React's,
and theming and tooltips go through its own configuration objects.

**Rejected alternative:** nivo or visx. Rejected: nivo pulls a larger
set of packages for the same charts, and visx is a toolkit of low-level
primitives, close to the hand-rolled SVG the request ruled out.

## The provenance panel marks the best-matching sentence, not an exact span

**Id:** 77c5025b-1e4c-41f0-a41c-46db75cdcaf3
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request that citations visibly prove their origin, relayed by the family lead, 2026-10-13; rag's citation shape of the same day (the full chunk text, no span)
**Revisit when:** rag returns the character span of the cited passage within the chunk

The panel shows the whole cited chunk and marks one sentence in it: the
one that shares the most words with the answer sentence carrying the
marker (`highlightPassage` and `claimFor` in `src/lib/provenance.ts`).
The panel says that the mark is the closest sentence, so it does not
read as an exact quote.

**Reason:** the citation carries the chunk, not the part of it the model
used, so any mark is an inference; word overlap with the claim is cheap,
deterministic and testable, and it is right in the common case where the
answer restates a sentence of the source.

**Rejected alternative:** no mark, only the chunk. Rejected because a
chunk of several hundred words does not show at a glance where the
statement comes from, which is what the panel is for.

**Rejected alternative:** ask the model for the span. Rejected for now:
it is a change in rag and costs tokens per answer; the revisit condition
covers it.

## German and English through a small t(), no i18n library

**Id:** 06b5b5ef-402b-4171-920c-a2d82823e139
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request for a German and English interface ("a small translation layer, one map per language, a t() helper, no heavy i18n library"), relayed by the family lead, 2026-10-13; the module-level language and the form of address were this directory's call
**Revisit when:** a third language, plural rules beyond one/other, or right-to-left text is needed

Every visible string goes through `t(key, vars)` from `src/i18n/`:
`en.ts` is the reference, `de.ts` is typed `Record<MessageKey, string>`
against it, so a missing or extra German key fails the typecheck, and a
test checks that both use the same `{placeholders}`. `tn(key, n)` picks
`.one` or `.other`. The current language is a module-level value that
`App` sets on every render from the user's `ui_language`, else the
browser's language, else English; lib helpers call `t()` directly, and
the labels of the kind, source and capture lists are getters, so their
callers did not change. German says "du".

**Reason:** two languages and a few hundred strings do not need a
library's message formats and loaders. One language is active at a time,
and it only changes through the user object `App` holds, which renders
the whole tree again, so a module-level value is enough and keeps
`t()` usable in pure helpers without threading it through every call.
"du" matches how current German web apps address their users and the
informal tone of the English copy.

**Rejected alternative:** react-i18next or a similar library. Rejected
by the request, and for the weight and the indirection it adds for two
languages.

**Rejected alternative:** a React context with a `useT()` hook only.
Rejected because the pure helpers (confirmation texts, the rate-limit
sentence, tile labels) are called outside components and would all have
needed `t` as a parameter.

**Rejected alternative:** "Sie" in German. Rejected for the tone; a
switch touches only `de.ts`.

## On the admin overview, red means "act here", and only the attention strip has it

**Id:** 160e3a94-c9f3-415e-a9e7-fb4a4da49ddd
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer review of the 0.7.1 overview ("too many tiles, several large and mostly empty, some red without anything he can do"), relayed by the family lead, 2026-10-13
**Revisit when:** an admin page appears where failed sources or documents can be inspected or retried

The overview has one KPI row of six plain tiles and, only when needed,
an attention strip whose every line links to the page where the admin
acts (Security for bans and blocks, System for a service down or
without a version). No tile is ever coloured. Failed sources and
documents are a muted detail under their tile, because no admin page
lists them yet. Charts share one time range and hide when empty.

**Reason:** a red number that offers nothing to do reads as an alarm the
admin cannot answer, and a wall of tiles hides the few numbers that
matter. The strip keeps colour for what is actionable, and the revisit
condition moves failures there once they have a page.

**Rejected alternative:** the previous three tile groups with red
outlines on failures. Rejected by the maintainer in review.

**Rejected alternative:** "pending sources older than N minutes" in the
strip, as requested. Not built: the stats carry no age, and pending
without an age would flash on every normal upload; it needs ingest to
report the oldest pending time.

## Light and dark through tokens only, following the system by default

**Id:** d3394545-e3bc-48fd-bae6-5243374ba47a
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request for a light and dark switch ("system" as default, every colour through the existing tokens), relayed by the family lead, 2026-10-13; the reasons below are this directory's
**Revisit when:** a third theme (high contrast, say) is asked for, or a component needs a colour that is not a token

Every colour of the app is a custom property in `styles.css`: the light
values on `:root`, the dark ones under `:root[data-theme='dark']` and,
for the system setting, the same values under `prefers-color-scheme:
dark` for a root without `data-theme='light'`. Components never carry
a colour of their own; the charts read the tokens as values (recharts
writes SVG attributes) and read them again when the theme changes; the
mind map maps markmap's variables to the tokens. A test parses the
token blocks, checks that both dark blocks match, and computes the WCAG
contrast of the pairs that carry text (4.5:1) or chart lines (3:1); it
found white on the dark accent and four light colours below the line,
which were changed.

**Reason:** with tokens a theme is a set of values, not a hunt through
components, and the contrast can be checked by a test instead of by eye.
"system" as the default because most people have already chosen light
or dark for their device, and the app should respect that until they
choose otherwise for it.

**Rejected alternative:** a theme class on the root with per-component
dark rules. Rejected: every component would need two sets of colours,
and the contrast test could not see them.

**Rejected alternative:** light as the default. Rejected because it
ignores the device setting the user already made.

## The header toggle switches light and dark only; "system" lives in Settings

**Id:** de0e4933-ad37-44b3-8f5d-b8d738b2b150
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** maintainer request relayed by the family lead, 2026-10-13 (drop "system" from the header toggle, start from the theme on screen, a click under "system" sets the explicit opposite); the reason is not stated there and is inferred below
**Revisit when:** someone asks for "system" back in the header, or a browser run shows the toggle confusing

The header toggle replaced a three-step cycle (light, dark, system). It
always sets the opposite of the theme on screen, its icon shows what a
click gives, and it goes through the one theme store like the Settings
page. "system" can be chosen on the Settings page only. Since
2026-10-14 the toggle changes this browser session only and saves
nothing in the account (see the entry on the session's theme).

**Reason (inferred):** in the cycle, the step to "system" often changed
nothing visible (the system's theme was the one already on screen), so a
click looked broken; two states make every click visible. The choice is
confirmed, the reason is this directory's reading.

**Rejected alternative:** the three-step cycle it replaced, for the
reason above.

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

## The architecture diagram is hand-drawn SVG, unlike the charts

**Id:** e9c8295b-3e1d-400a-a269-5949aa11f034
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request relayed by the family lead, 2026-10-13 ("SVG, no library", recharts "not the tool here", static layout with live numbers); the layout and the data mapping were this directory's call
**Revisit when:** the set of deployments changes often enough that a fixed layout needs editing each time, or the diagram has to show more than the chart's deployments and the three external services

The System page draws the architecture as one SVG component with fixed
coordinates: browser and ingress on top, the four deployments and the two
workers in the middle, PostgreSQL, object storage and the inference API
as external boxes below, the lines routed between the boxes. Only the
numbers are live: replicas ready of total, the build, and the attention
colour for an unhealthy deployment, mapped from the System data by the
chart's deployment names in a tested function.

**Reason:** the topology is fixed and small, so coordinates are less code
than a layout engine and keep the picture the same on every visit, which
is what makes the design recognisable. The charts entry above rules out
hand-rolled SVG for charts, because axes, scales and tooltips are what a
chart library is for; a box-and-arrow picture of nine nodes needs none
of that, and recharts has no shape for it.

**Rejected alternative:** a diagram library with automatic layout
(Mermaid and similar). Ruled out by the request; it would also add a
large dependency for a picture whose layout never changes.

## The source selection remembers the sources turned off, and never sends an empty list

**Id:** 118cc0d6-ca60-4e41-b491-bb532ae5ba34
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request relayed by the family lead, 2026-10-14 (a checkbox per source, all on by default, remembered per notebook in the browser); rag's request shape (`source_ids`, absent or empty meaning all); what is stored and the empty case were this directory's call
**Revisit when:** the selection is stored in the account instead of the browser, or rag gives an empty `source_ids` a meaning of its own

The browser keeps, per notebook, the ids of the sources turned off, not
the ones turned on. A request sends the ticked ids only when at least
one source is off, and nothing while all are on. With every source off,
the chat and Create are blocked with a hint instead of sending a request.

**Reason:** "all on" is the default, so a source added later (in this
tab, another browser or by the wizard) has to start ticked; a stored
"on" list would leave it off silently. Blocking the empty case follows
from the contract: rag reads an empty `source_ids` as all sources, so
sending it would answer from everything while the list shows nothing
ticked.

**Rejected alternative:** storing the ticked ids. Rejected because every
new source would start unticked until the user noticed.

**Rejected alternative:** sending an empty list when nothing is ticked.
Rejected for the reason above: the request would mean the opposite of
what the screen shows.

## Deleting a notebook with "delete them too" trashes its documents in rag before ingest deletes the notebook

**Id:** f372b0d1-2501-469f-8d60-370365d0bbbe
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision relayed by the family lead, 2026-10-14 (documents become library items; deleting a notebook asks whether they go too or stay); rag's contract (`DELETE /api/rag/notebooks/{id}/outputs`, the notebook reference set to null by a foreign key when ingest deletes the notebook); the order was this directory's call
**Revisit when:** one service deletes a notebook and its documents together, or the documents' delete can run after the notebook is gone

With "delete them too" the web first calls rag to move the notebook's
documents to the trash, then ingest's notebook delete; with "keep" only
ingest's. When rag fails, the notebook is untouched and the dialog shows
the error, so the user can try again or choose differently.

**Reason:** the two calls go to different services and cannot be one
transaction. In this order a failure leaves the state the user started
from. The other way round, a failed second call would leave the
documents in the library although the user asked for them to go, which
is the outcome of the other button.

**Rejected alternative:** ingest's notebook delete first, then rag's.
Rejected because rag's endpoint takes the notebook id, which no longer
resolves once ingest has deleted the notebook and the foreign key has
set the documents' notebook to null.

