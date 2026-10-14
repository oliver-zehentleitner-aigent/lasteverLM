# User interface

Status: v1 draft, under review. Owner: Agent E (web), with rag (Agent D)
for everything the viewer and the wizard call.

## Principle

Few fields, big choices. Every screen asks one question. The layout is
two columns, not NotebookLM's three: the product is about turning
sources into documents and talking about both, so the documents get the
space.

## The wizard: adding sources

Three steps, one question each, large tiles instead of a form, for a
new notebook. Opened from an existing notebook (the add button) it has
two: it ends after the sources, with a short note and "Done" when some
were in the notebook already.

1. **What goes in?** Tiles: **From library** first, for something
   added before to another notebook, then PDF, Text, Web page, Image,
   Audio (MP3, WAV, M4A, OGG, FLAC, WEBM or MP4 audio, up to 60 MB;
   anything but MP3 and WAV is converted first, then what is said is
   transcribed). A
   kind that is not available yet is shown greyed with "Soon.", so the
   extension points stay visible.
2. **How does it get in?** Only the ways that fit the type: drop or
   pick files (several at once), enter a URL, paste text; from the
   library, a list with one row per entry (checkbox, the name on one
   line with an ellipsis, images with a 2rem thumbnail in front, a URL
   shortened to host and path, the kind and
   demo badges in a fixed slot on the right, a generated document as
   "Generated", so a document made in one notebook becomes a source in
   another; the whole row toggles) and
   "n selected" next to the add button. For PDFs a
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
3. **What should come out of it?** (new notebook only) Tiles of the
   output kinds, multiple selection; "Create n documents", or "Skip" to
   just chat.

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

- **Sources** (left, top): the uploads (PDF, text, web page, image,
  audio), each with its kind as a badge
  with status and remove; the add button opens the wizard at step 1,
  without the output step. An audio source has a play button (see
  "Checking an audio source" under Library).
  Removing only detaches the source from this notebook, it stays in the
  library. Deleting a notebook detaches its sources the same way. A
  document made in another notebook and added from the library is
  listed here too, with the kind "Generated". Deleting a notebook that
  has generated documents asks first: "N generated documents: delete
  them too, or keep them in the library?" (Cancel, Keep in library,
  Delete all N too). "Delete too" moves them to the trash in rag
  (`DELETE /api/rag/notebooks/{id}/outputs`) before ingest deletes the
  notebook, so a failure there leaves the notebook untouched; "keep"
  only deletes the notebook, and the documents stay in the library with
  their origin noted. Without generated documents the plain
  confirmation as before.
  This notebook's own generated documents are not listed here (they are
  under Outputs), although the backend keeps each one as a source of
  kind `generated` so the chat can cite it.
  Each row has a checkbox: the chat and new documents use only the
  ticked sources. All are ticked by default, "all / none" sits in the
  header from two sources on, and the browser remembers per notebook
  which ones are off (so a source added later starts ticked). With none
  ticked, the chat and Create say to tick one; a question or a
  document then sends `source_ids` (the ticked link ids) and none while
  all are ticked.
- **Output format** (left, middle): the output kinds as tiles, always
  three by two (Report, Quiz, Data table / Mindmap, Infographic,
  Audio) at a fixed 8rem width; the column starts at, and cannot be
  dragged below, the width of that grid (27rem). Only on a phone,
  where the columns stack, do the three tiles share the width. A click
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
  is synthesized. For audio also a **Style**: Overview (the default),
  Story or Conversation (`audio_style`); with Conversation a **Second
  voice** select appears with its own sample button (`audio_voice_2`,
  sent for a conversation only), starting with the next voice of the
  first one's language, as rag would pick it, and never the same as the
  first (changing the first to the second's voice moves the second on).
  They start from the
  user's preferences, else rag's defaults, and go into `options` of the
  create request with only the keys the kind takes. The viewer and the
  shared page show what a document was made with ("Deutsch · Ryan ·
  1.25×", "Conversation · Ryan & Aiden · 1×").
- **Outputs** (left, bottom): the generated documents, one row each:
  the kind and the status in fixed slots, the title between them, and
  below the title when it was made ("14 min ago", the date and time as
  tooltip; the absolute time once it is older than a day) with its
  language code and, for audio, the voice, and "from 3 sources" when it
  was made from a selection (`Output.options.sources`; the names as
  tooltip, a removed source counted as removed). A sort control above the
  list: newest first (the default, since a kind is often made again
  from the same sources), oldest first, by kind, by language, by
  status. From six documents on, kind chips filter the list. A click
  opens the document's tab, × deletes it.
- **Output viewer** (right, top): one tab per output (its header shows
  "from 3 sources" when it was made from a selection), processing tabs
  show a spinner and poll; the pane says "Generating…" with a small
  ASCII figure walking beside it (decorative, still under reduced
  motion). Each kind has its own renderer; the audio
  player sits centred in the pane, and the mind map fills the pane and
  re-fits whenever its size changes (full view, divider, window). A
  small bar on the map's top right zooms in (+), out (−) and fits it
  again (⤢); with the map focused, the keys +, − and 0 do the same.
  Actions per document: ask about this, print, share, full view.
- **Column dividers** between the notebook list, the left column and
  the right column: drag them (or arrow keys when focused) to change the
  widths, remembered per browser in pixels; a double-click (or Home)
  returns to the default. The notebook list stays between 160 and 420
  px, the left column between 378 px (the 3 x 2 format grid) and 720 px,
  and the right column
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
- **Chat** (right, bottom): one tab per conversation of the notebook
  ("Chat N" by default; a double-click or F2 renames a tab in place,
  Enter or leaving the field saves, Esc cancels, an empty name keeps the
  old one), "+" opens a new one, "×" closes one after a confirmation and deletes
  its messages; closing the last tab opens a fresh one, and a notebook
  without conversations gets one when the chat opens, so a question
  always goes to a conversation. With not all sources ticked, a muted
  "3 of 5 sources" line sits above the question field; a question about
  one document ("ask about this") ignores the selection. In the active tab: question, answer,
  citations as `[n]` that open the cited passage; a citation into a
  generated document opens that tab.

## Viewer, print, share

- **Provenance**: a click on `[n]` (in the answer or in the citation list
  under it) opens a panel under the answer: source name and kind, page,
  "chunk 12 of 43", the similarity of that chunk to the question as a
  number and a bar, and the chunk text verbatim, with the sentence that
  shares the most words with the cited statement marked (a best guess:
  the backend sends no span). For an upload "open in source" opens it in
  a new tab through its `preview_url` (a PDF with `#page=<n>`, so the
  browser's viewer lands on the cited page; without a page, at the
  start) and highlights the source in the list; a source without a
  preview is only highlighted. For a generated document the link reads "open
  document": it opens that document's tab and shows the passage: in a
  report, quiz, table or infographic the text block sharing the most
  words with the chunk scrolls into the middle and flashes; a mind map
  fits and flashes the node whose label matches the chunk's first line
  (or only fits). Also in the full view. The citation list shows
  page and similarity inline, e.g. `[1] linux_-_vi.pdf p. 2 · 0.71`.
  Citations from before this carry no position or similarity; the panel
  completes the position and the full text from `GET /api/rag/chunks/{id}`
  when the chunk still exists. Shared documents carry no citations, so
  the shared page has no panel.
- **Viewer**: a clean document view with title, date, the sources it was
  made from. Report as Markdown, quiz interactive with reveal, table
  sortable with CSV export, mind map with markmap, infographic as a
  card grid, audio as a player with the transcript under it (a
  narrator's paragraphs as text; a conversation with each turn's speaker,
  named by its voice, in front; documents made before transcripts have
  none).
- **What a document rests on** (rag's `provenance`; documents made
  before it have none and show none of this). A report's `[n]` markers
  are buttons, as in a chat answer; an infographic's facts and sections
  and an audio transcript's turns carry their markers after the text. A
  click opens the chat's provenance panel under the document for that
  passage (source, page, chunk position, similarity, the chunk with the
  sentence closest to the claim marked, "open in source"). A claim the
  check did not back has a red "unsupported" badge, one written in
  another language than its sources an amber "not checkable"; the claim
  stays. The head says "7 of 9 claims supported" (the check's method and
  threshold as tooltip). Under the document, folded: **Sources (n)**, the
  passages it cites, and **How this was made**: model, prompt version,
  options, the retrieval query, usage, when and how long, the check's
  counts, the retrieval candidates with similarity and whether they went
  into the prompt, and the whole log as a JSON download. The share page
  shows all of it read-only, without "open in source". Stage 1: report,
  infographic, audio; table, quiz and mind map follow.
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
user, once, newest first, with kind, status (a failed entry's reason on
one line next to the badge, in full as its tooltip), size ("unknown" for
entries added before sizes were recorded), date and the
notebooks it is in as links (or "not in any notebook"). Filters by kind
and by part of the name or address. **Open** (a row action, and the
name itself) shows the entry in a new tab: a web page at its address,
an upload (PDF, text, image, audio, which the browser plays) through
its presigned `preview_url`; an
image also keeps the hover preview below. Only `http(s)` addresses are
linked, and without a preview the action is disabled with a note.
**Checking an audio source** (here and in a notebook's Sources list): a
play button per audio row mounts a player for that row only (nothing
loads before; one player at a time, a second click closes it), with a
download link "transcribed audio" (the file that was transcribed: the
converted MP3, or the upload itself for MP3 and WAV) and, when the
upload was converted first, "original" (`original_url`). Open still
takes the transcribed file.
Each row has a checkbox ("all / none" in the column header acts on the
rows the filter shows; ticks survive a filter change). With rows
ticked a bar above the table offers **New notebook from n sources** (a
title field in the bar next to the button, Enter or the button creates,
Escape clears it; preset with the first file's name without its
extension, else the first web page's title or, from its address, host
and last path segment, "en.wikipedia.org · Dead reckoning", never the
raw address; the notebook is created, each entry added from the library one by one,
then the notebook opens) and **Delete n** (one confirmation naming every
notebook the entries leave, then one delete per entry with "n of m" in
the bar; after a failure the rest stays ticked).
Delete moves the entry to the
trash, out of every notebook, after a confirmation that names those
notebooks. The **Trash** view next to it lists deleted entries with
the date they are purged (after the trash days set in the settings,
14 by default; "settings" links to that field): restore puts one back in the library in no notebook,
"delete for good" removes the file and its passages at once. Uploading
the same file or URL again restores it too.

**Outputs** (a view between Sources and Trash): every generated document
of the user, newest first (`GET /api/rag/library/outputs`), with title,
kind (and status when not ready), the notebook it was made in (its
current title; once that notebook is deleted, "deleted notebook
"test1"" with the title it had) and the date. **Open** goes to that
notebook with the document selected; when the notebook is deleted it
shows the document read-only on this page, as the share page does, with
print where the kind has it and no sharing. Checkboxes with "all /
none", and **Delete n** in a bar (one confirmation, then one delete per
document with progress), or delete per row: a document moves to the
trash, leaves every notebook and its share link stops working. The
**Trash** view lists trashed documents under the trashed sources, with
restore (back into the notebook it was made in, if that still exists;
other notebooks need it added again) and delete for good.

Image entries show a small square thumbnail in front of their name in
the library, the trash and the wizard's picker, loaded lazily from the
entry's `preview_url`. Hovering the thumbnail or the name, or focusing
the thumbnail, shows a preview up to 320 px next to it, kept inside the
window; leaving or Esc hides it. On touch a tap on the thumbnail opens
it without ticking the row, a tap elsewhere closes it.

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
  and no mail goes out. Under it, "Have a sign-in code from the mail?"
  takes the code the mail prints under the link (the same single-use
  token, for another device): 43 characters of letters, digits, `-`
  and `_`, counted while typing, Continue enabled once it matches, an
  eye toggle to show it; it is exchanged like the link, and an unknown,
  used or expired code says so.
- Header: balance in EUR, a voucher button that opens a one-field
  dialog. A 402 anywhere opens the same dialog.
- Narrow screens: no page scrolls sideways. Below 900 px the notebook's
  columns stack (sources and documents, then viewer, then chat); below
  640 px the header takes two lines, brand and account (theme, balance,
  sign out) above, the navigation below, and leaves out the e-mail
  address. The architecture diagram on Admin > System scales to its
  card; wide admin tables scroll inside theirs.
- Admin (for the roles `admin` and `viewer`): pages under `/admin` with
  a sub-navigation; each page loads only its own data, every page has
  its own URL. A **viewer** reads everything: the heading carries a
  "read-only" badge, and every write control (voucher create and
  delete, allow-list add and remove, viewer domains, rate-limit save and
  reset, lifting a ban, the SMTP test, role changes) is disabled with a
  tooltip saying changes need an admin; the server answers a viewer's
  writes with 403 as well. Without a `role` from the account service
  the role follows `is_admin`.
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
  - **Users** (`/admin/users`): users with their role (for an admin a
    select: user, viewer, admin, after a confirmation, `PATCH
    /api/account/admin/users/{id}`; the service's refusal for the last
    admin or the demo user is shown as its sentence), credit granted,
    used and balance and their last login, and for an admin a "delete"
    action: a dialog names the address and what goes with the account
    (notebooks, sources, generated documents, credit history) and enables
    its button only once the address is typed out; `DELETE
    /api/account/admin/users/{id}`. A refusal (409: one's own account,
    the demo user) shows the service's sentence, a failed step (502
    `{step, message}`) names the step and says the user is still there;
    either way the dialog stays open. Viewers see no delete action. Then
    the login log, sign-in attempts (allowed or refused, with IP).
  - **Access** (`/admin/access`): allowed sign-in, domains and single
    addresses, one entry at a time; below, the **viewer domains**: a new
    user from one of them (also allowed to sign in) starts as viewer.
  - **Credits** (`/admin/credits`): voucher creation (5 EUR by default)
    that shows the codes once as chips with a copy button each ("copy
    all" for several; without the clipboard API the text is selected
    instead), next to the form when there is room; the list of issued
    vouchers below (open ones can be deleted).
  - **Security** (`/admin/security`): the rate-limit rule as a sentence
    with its four editable numbers and a reset to the deployment
    defaults, then blocks, bans (with lift) and the raw access log.
    Blocks and bans are keyed by an IPv4 address or an IPv6 /64 prefix
    (`2001:db8:1:2::/64`), shown as is; lifting sends the key as a query
    parameter (`DELETE /api/account/admin/bans?ip=<key>`), so the slash
    of a prefix never reaches the path.
  - **Visits** (`/admin/visits`): visitor log aggregated per day and path.
  - **Mail** (`/admin/mail`): SMTP settings read-only (they come from the
    deployment) with a test button.
  - **System** (`/admin/system`): per service a card with version,
    commit and health; **Architecture and monitoring**, a diagram (plain SVG, static
    layout, live numbers): the browser and the ingress at the top, web
    and the three API services below, the ingest and rag workers under
    their services, and PostgreSQL with pgvector, the object storage and
    the inference API as external boxes at the bottom, with arrows for
    the flows (ingress to the services, the services and the workers'
    job queues to PostgreSQL, the workers to storage and the models, rag
    to the models for answers); each deployment's box shows its
    replicas ready of total, its restarts when there are any, and its
    build, coloured by its state: green when every replica is ready and
    no pod restarted; amber while a rollout is under way (the
    deployment's Progressing condition, else fewer replicas updated than
    wanted, or two image tags among its pods), when it is partly ready
    (4 of 5) or its pods have restarted; red only for failure: a pod
    crash-looping, erroring or killed for memory, restarts that grew
    since the last refresh, nothing ready outside a rollout, or a healthz
    that does not answer; grey when nothing is known (the state and why
    as tooltip). A rollout is never red. The lines into a red box are
    dashed red. The external boxes take the state the services' healthz
    report for them (`dependencies`: red when one says down, green when
    all that report say ok) and stay grey with "not probed" until one
    does. A legend under the
    diagram; the page reloads the data every 15 s while the tab is
    visible (the time of the last refresh under it), colours change with
    a short transition, none with reduced motion. Then the cluster's pods (name, service, image
    tag, ready, restarts, node, started) and deployments (replicas,
    ready, updated); a local run without a cluster says so instead, and
    in a cluster where both lists come back empty (the account service
    is a pod itself, so the Kubernetes API was not readable) the page
    says that the read role for pods and deployments is missing and
    points to "The chart" in `infra/docs/operations.md` (`kubernetesRead`). The
    overview shows the build ("lasteverLM 0.6.1 · 5e320ae") under its
    heading, linked to this page.

The running build is also the tooltip of "lasteverLM" in the header, for
everyone, from the public `/api/account/healthz`.

## Theme

Light or dark: a `theme` preference "system" (the default, following the
operating system's setting), "light" or "dark". A toggle in the header
switches between light and dark only, starting from what is on screen
(its icon shows what a click gives; under "system" a click sets the
explicit opposite), and applies at once; "system" is chosen on the
Settings page; both read and write one theme store
(`lib/theme.ts`), so the toggle always shows what Settings saved and the
other way round. The choice is kept in this browser
(read by a small script in `index.html` before the first paint, so a
dark choice never flashes light) and, when signed in, in the account,
so it follows the user to other browsers; the shared demo account keeps
it in the browser only. Every colour goes through the tokens in
`styles.css` (one block per theme), the charts and the mind map
included; the charts read the tokens again when the theme changes. A
test computes the WCAG contrast of the token pairs in both themes (4.5:1
for text, 3:1 for chart colours). Printing is always light.

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
