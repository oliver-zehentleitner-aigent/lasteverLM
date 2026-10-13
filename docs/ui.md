# User interface

Status: v1 draft, under review. Owner: Agent E (web), with rag (Agent D)
for everything the viewer and the wizard call.

## Principle

Few fields, big choices. Every screen asks one question. The layout is
two columns, not NotebookLM's three: the product is about turning
sources into documents and talking about both, so the documents get the
space.

## The wizard: adding sources

Three steps, one question each, large tiles instead of a form.

1. **What goes in?** Tiles: **From library** first, for something
   added before to another notebook, then PDF, Text, Web page, Image. A
   kind that is not available yet is shown greyed with "Soon.", so the
   extension points stay visible.
2. **How does it get in?** Only the ways that fit the type: drop or
   pick files (several at once), enter a URL, paste text. For PDFs a
   **Capture** choice: Auto (text layer where present, the vision model
   for scanned pages), Text (text layer only, scanned pages fail) or
   Vision (every page through the vision model, one model call per
   page), preset from the preference and sent as `capture` with the
   upload. The same file in another mode is a separate library entry.
   A failed upload (a storage outage answers 503) shows the service's
   sentence at this step; the files that went in leave the list, the
   rest stays selected for a retry.
   For the
   library, a filterable list of the entries not yet in this notebook to
   tick.
3. **What should come out of it?** Tiles of the output kinds, multiple
   selection, "just chat" is allowed. Done.

Step 2 calls `POST /api/ingest/notebooks/{id}/sources` per file, once
with `{"url"}` for a web page, or with `{"library_id"}` per picked
library entry. The same file or URL again links the existing library
entry (nothing is processed twice); when it was in this notebook
already (200), step 3 says so. Step 3
calls `POST /api/rag/notebooks/{id}/outputs` per selected kind; rag
waits for the sources itself, so the wizard works even when the browser
is closed. After the wizard the notebook view opens.

## The notebook view

```text
┌───────────────────┬──────────────────────────────────────┐
│ Sources           │ Output viewer                        │
│  · report.pdf  ✓  │  [Report] [Quiz] [Table] [Mindmap]   │
│  · notes.txt   ✓  │                                      │
│  + add            │  (the selected document)             │
├───────────────────┤                                      │
│ Output format     │  ask about this · print · share      │
│ [Report] [Quiz]   ├──────────────────────────────────────┤
│ [Table] [Mindmap] │ [Chat 1 ×] [Chat 2 ×] [+]            │
│ [Infographic]     │  question … answer with [1] [2]      │
│ [Audio]  [Create] │  > ask your sources                  │
├───────────────────┤                                      │
│ Outputs           │                                      │
│  · Report  ready  │                                      │
│  · Quiz    ready  │                                      │
└───────────────────┴──────────────────────────────────────┘
```

- **Sources** (left, top): the uploads (PDF, text, web page, image)
  with status and remove; the add button opens the wizard at step 1.
  Removing only detaches the source from this notebook, it stays in the
  library. Deleting a notebook detaches its sources the same way.
  Generated documents are not listed here, although the backend keeps
  each one as a source of kind `generated` so the chat can cite it.
- **Output format** (left, middle): the output kinds as tiles. A click
  (or Enter on a focused tile) only selects one, highlighted, and the
  selection stays while the notebook is open; the **Create** button
  at the right edge below the tiles starts the job for the selected
  format over the whole notebook.
  The button is disabled without a selection or while no source of the
  notebook is ready, with a one-line hint on the left saying which.
  Between the tiles and the button, the selected format's options as
  rag's `GET /outputs/options` lists them per kind: language for every
  kind ("same as the sources" or one of the listed languages), voice
  (grouped female and male) and speed for audio, with a "sample" button
  that plays a short sentence pair in that voice, speed and language
  (the interface language when "same as the sources" is chosen); the
  sample is fetched on click only, since the first one per combination
  is synthesized. They start from the
  user's preferences, else rag's defaults, and go into `options` of the
  create request with only the keys the kind takes. The viewer and the
  shared page show what a document was made with ("Deutsch · Ryan ·
  1.25×").
- **Outputs** (left, bottom): the generated documents with kind, title
  and status; a click opens the document's tab, × deletes it.
- **Output viewer** (right, top): one tab per output, processing tabs
  show a spinner and poll. Each kind has its own renderer; the audio
  player sits centred in the pane, and the mind map fills the pane and
  re-fits whenever its size changes (full view, divider, window).
  Actions per document: ask about this, print, share, full view.
- **Column dividers** between the notebook list, the left column and
  the right column: drag them (or arrow keys when focused) to change the
  widths, remembered per browser in pixels; a double-click (or Home)
  returns to the default. The notebook list stays between 160 and 420
  px, the left column between 240 and 720 px, and the right column
  keeps at least 360 px. Hidden on narrow screens.
- **Tab bars** (documents and chats) scroll sideways when the tabs do
  not fit: the active tab is scrolled into view, a mouse wheel scrolls
  the bar, and the arrow keys, Home and End move between tabs (only the
  active tab is in the Tab order). In the chat bar only the tabs
  scroll; "+" and the height presets stay in place.
- **Divider** between viewer and chat: drag it (or arrow keys when it
  has focus) to change the split; the split is remembered per browser,
  a double-click (or Home) resets it to half and half. Three presets
  at the right end of the chat tab bar, **1x 2x 3x**, give the chat 15,
  30 or 45 % of the right column; they set the same ratio the divider
  does, the matching one is highlighted, a drag moves off it. Divider
  and presets are hidden on narrow screens, where the columns stack.
- **Full view**: the open document over the whole window, for tall or
  wide documents such as the mind map; the viewer's tabs stay, so
  another document is one click away. The chat is behind a "chat"
  toggle in the bar at the top right and opens in the lower part;
  "ask about this" opens it too. Esc closes that chat first, then the
  full view; × leaves it as well. Leaving returns to the two panes with
  the split as it was, and the focus goes back to the full-view
  button.
- **Chat** (right, bottom): one tab per conversation of the notebook,
  "+" opens a new one, "×" closes one after a confirmation and deletes
  its messages; closing the last tab opens a fresh one, and a notebook
  without conversations gets one when the chat opens, so a question
  always goes to a conversation. In the active tab: question, answer,
  citations as `[n]` that open the cited passage; a citation into a
  generated document opens that tab.

## Viewer, print, share

- **Provenance**: a click on `[n]` (in the answer or in the citation list
  under it) opens a panel under the answer: source name and kind, page,
  "chunk 12 of 43", the similarity of that chunk to the question as a
  number and a bar, and the chunk text verbatim, with the sentence that
  shares the most words with the cited statement marked (a best guess:
  the backend sends no span). "open in source" highlights the source in
  the list, or opens a generated document's tab. The citation list shows
  page and similarity inline, e.g. `[1] linux_-_vi.pdf p. 2 · 0.71`.
  Citations from before this carry no position or similarity; the panel
  completes the position and the full text from `GET /api/rag/chunks/{id}`
  when the chunk still exists. Shared documents carry no citations, so
  the shared page has no panel.
- **Viewer**: a clean document view with title, date, the sources it was
  made from. Report as Markdown, quiz interactive with reveal, table
  sortable with CSV export, mind map with markmap, infographic as a
  card grid, audio as a player.
- **Print**: a print stylesheet on the viewer and a button; the browser
  produces the PDF. Report and table are the printable kinds.
- **Share**: creates a share token and shows the link `/s/<token>`; the
  page renders the document read-only without login and records a
  visit. Revoke from the same place.
  The shared page is as tall as the window: report, quiz and
  infographic sit in a centred reading column, the mind map and the
  table use the full width, the audio player is centred.
- **Ask about this**: switches the chat scope to the open document
  (`scope.output_id` on `/ask`); a chip above the input shows the scope
  and clears it.

## Settings

`/settings` (in the header next to Library): interface language
(browser default, English, Deutsch), language of generated documents
(same as the sources, or one of rag's languages) and the voice for
audio (default, or one of rag's voices, with the same sample button),
and the days a deleted
library source stays in the trash (1–365, empty for 14), and how PDFs
are read by default (Auto, Text or Vision). Saved together with
`PUT /api/account/me/preferences`; an empty choice clears the value.
The preferred language and voice are preselected in the output options
and used by the wizard, which has no option menus. The interface
language is stored here and applied by the translation layer. The
shared demo account cannot change settings (403, shown as the
service's sentence).

## Library

`/library` (in the header next to Admin): every upload and URL of the
user, once, newest first, with kind, status, size, date and the
notebooks it is in as links (or "not in any notebook"). Filters by kind
and by part of the name or address. Delete moves the entry to the
trash, out of every notebook, after a confirmation that names those
notebooks. The **Trash** view next to it lists deleted entries with
the date they are purged (after the trash days set in the settings,
14 by default; "settings" links to that field): restore puts one back in the library in no notebook,
"delete for good" removes the file and its passages at once. Uploading
the same file or URL again restores it too. Generated documents are not in the library;
they live in their notebook.

A new account starts with four example sources in its library (a PDF,
a Markdown glossary, an image and a Wikipedia page), marked "demo"
there, in the wizard's library picker and in a notebook's source list.
The library page polls while entries are still processing, so they
turn ready on their own. In a notebook that holds demo sources, an
empty chat offers a first question ("How did Ida Vennholt find her way
in the fog, and what is that method called?"); a click puts it into
the question field.

A citation whose source is no longer in the notebook (detached, or
deleted from the library) stays readable with its quote and is marked
"source removed".

## Login, credit, admin

- Login page: one field, the e-mail address; then "check your mail";
  the link lands on `/auth/callback` and the app is open. An address
  without access is told "This address has no access to lasteverLM."
  and no mail goes out.
- Header: balance in EUR, a voucher button that opens a one-field
  dialog. A 402 anywhere opens the same dialog.
- Admin (only for admins): pages under `/admin` with a sub-navigation;
  each page loads only its own data, every page has its own URL.
  - **Overview** (`/admin`): the heading with one muted meta line,
    "v0.7.1 · b44f38a · 3 services healthy" with a status dot per
    service, linked to System. One row of six equal tiles, a number and
    a short label each: Users, Logins 24 h, Cost 24 h (the total as a
    detail), Open vouchers, Sources (ready; failed as a detail),
    Documents (failed as a detail); a service whose stats do not load
    shows a dash. An **attention strip** only when something needs an
    action, one line each with its page: active bans and rate-limit
    blocks (Security), a service that is not reachable or reports no
    version (System). Red appears there and nowhere else on the page;
    failed sources and documents have no admin page to act on, so they
    stay a muted detail. Below, the charts in a two-column grid of equal
    cards and one shared time range (7 days while everything happened
    in the last week, else 30, with a 7 / 30 toggle): cost and credit
    granted per day next to logins and visits, chat messages and
    documents next to sources added per day by kind, documents by kind
    (donut) next to cost by model (all time), the top users (all time)
    across both columns. A chart without data in the range is not
    drawn; one quiet line names those ("No data yet: …").
  - **Users** (`/admin/users`): users with credit granted, used and
    balance and their last login, the login log, sign-in attempts
    (allowed or refused, with IP).
  - **Access** (`/admin/access`): allowed sign-in, domains and single
    addresses, one entry at a time.
  - **Credits** (`/admin/credits`): voucher creation (5 EUR by default)
    that shows the codes once as chips with a copy button each ("copy
    all" for several; without the clipboard API the text is selected
    instead), next to the form when there is room; the list of issued
    vouchers below (open ones can be deleted).
  - **Security** (`/admin/security`): the rate-limit rule as a sentence
    with its four editable numbers and a reset to the deployment
    defaults, then blocks, bans (with lift) and the raw access log.
  - **Visits** (`/admin/visits`): visitor log aggregated per day and path.
  - **Mail** (`/admin/mail`): SMTP settings read-only (they come from the
    deployment) with a test button.
  - **System** (`/admin/system`): per service a card with version,
    commit and health, then the cluster's pods (name, service, image
    tag, ready, restarts, node, started) and deployments (replicas,
    ready, updated); a local run without a cluster says so instead. The
    overview shows the build ("lasteverLM 0.6.1 · 5e320ae") under its
    heading, linked to this page.

The running build is also the tooltip of "lasteverLM" in the header, for
everyone, from the public `/api/account/healthz`.

## Language

The interface is English or German: the user's `ui_language`
preference decides, and before login (or without a preference) the
browser's language, English when it is neither. Every visible string of
the web goes through `t()` (`web/src/i18n/`, one map per language);
German addresses the user with "du". Messages that come from the
services (an `{"error"}` text) stay as the service wrote them, in
English. Sources, questions, answers and generated documents are in
whatever language the user and the sources use, or the one picked in
the output options.
