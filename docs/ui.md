# User interface

Status: v1 draft, under review. Owner: Agent E (web), with rag (Agent D)
for everything the viewer and the wizard call.

## Principle

Few fields, big choices. Every screen asks one question. The layout is
two columns, not NotebookLM's three: the product is about turning
sources into documents and talking about both, so the documents get the
space.

## Adding sources

A dialog, "Add sources", opened by the Sources list's "+ add" and
right after a notebook is created. It only adds sources: two questions,
large tiles instead of a form. After each batch it returns to the tiles
with "3 sources added. Add more, or close." (and how many were in the
notebook already), and the list behind it shows the new ones at once;
it stays open until the user closes it ("Done", or "Close" before
anything was added). Outputs are made in the Output format area, never
here.

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
   starter badges in a fixed slot on the right, a generated document as
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

The second step calls `POST /api/ingest/notebooks/{id}/sources` per
file, once with `{"url"}` for a web page, or with `{"library_id"}` per
picked library entry. The same file or URL again links the existing
library entry (nothing is processed twice); when it was in this
notebook already (200), the note after the batch says so.

**Introduction.** Once per user, the notebook view opens with a short
tour. A new user lands in a notebook so the tour has its view: the
first notebook of the list (the starter notebook, which ingest copies
into the first list), or, without any notebook, a first one the
workspace makes ("My first notebook", without the add-sources dialog
over it, since the tour's first step points at "+ add"). A user who has
done the tour lands where they always did (the notebook open last, else
the first, else the empty state). The tour: three steps over a dimmed page, each outlining its area with a
card and an arrow beside it: 1 "Add one or more sources" (the Sources
panel and "+ add"), 2 "Pick an output format" (the format tiles; set
options or keep the defaults), 3 "Create" (the Create row; without
credit "Redeem a voucher first: the link is next to Create"). Next,
Back, Skip; done in three clicks. Finishing or skipping sets the
account's `tour_done` preference, and a note in this browser for an
account that cannot keep it (the shared demo user, or an account
service before the preference). Not shown over the add-sources dialog.
Settings has "Show the introduction again", which clears both and
opens the notebook.

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
│ [Audio] [Decision]│  > ask your sources                  │
│          [Create] │                                      │
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
  "Checking an audio source" under Library). Each source is one line:
  its checkbox, the name cut with an ellipsis (the full name as
  tooltip), then kind, capture and status as compact badges, the play
  button and × as one group at its natural width. The row never wraps
  on a desktop: the name gives way first; in a narrow pane the badges
  shorten instead (below 24rem the kind as a code, PDF, TXT, WEB, IMG,
  AUD, and no capture badge; below 18rem the status as an icon, ✓ … +
  € !, its word in the tooltip). In the stacked phone layout (below 900
  px) a row may put the whole group, × included, under the name. The
  status badge is short
  ("ready", "reading", "added", "failed"); what it means, a failed
  source's error and why a waiting one is not moving are its tooltip.
  **Read when used**: a new source is "added" (neutral; "added · read
  when used"), read only when an output or a question first uses it; a
  small **read now** asks ingest's price for it (`POST
  /api/ingest/sources/estimate`) and, after a confirmation naming it,
  reads it (`POST /api/ingest/sources/process`). Without credit the
  source being read waits as before. A web page shows how long ago it
  was fetched after its name ("3 h ago"), "v2" once it changed, and ↻
  (fetch again: `POST /api/ingest/sources/{id}/refetch`, after a
  confirmation; read again only if it changed).
  Removing only detaches the source from this notebook, it stays in the
  library. Deleting a notebook detaches its sources the same way. A
  document made in another notebook and added from the library is
  listed here too, with the kind "Generated". Deleting a notebook that
  has outputs asks first: "It has N outputs: delete
  them too, or keep them in the library?" (Cancel, Keep in library,
  Delete all N too). "Delete too" moves them to the trash in rag
  (`DELETE /api/rag/notebooks/{id}/outputs`) before ingest deletes the
  notebook, so a failure there leaves the notebook untouched; "keep"
  only deletes the notebook, and the documents stay in the library with
  their origin noted. Without outputs the plain
  confirmation as before.
  A source added without credit is listed with a muted, neutral badge
  "added · processed when you have credit" (not amber: it is no error);
  it is processed once there is credit again, and the
  list keeps polling until then. Adding is never blocked by credit;
  creating outputs is: without credit the hint next to Create says "No
  credit: sources wait, outputs cannot be created." with "redeem a
  voucher" (the voucher dialog), and Create is disabled.
  A source still processing or waiting for credit has the service's
  `error` as its status badge's tooltip: "pricing has no exchange rate,
  ask an admin" as it comes, the badge then amber (nothing was tried; it
  runs once an admin sets the rate), any other error while processing as
  "Retrying after: …", and while waiting for credit as it comes.
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
  three to a row (Report, Quiz, Data table / Mindmap, Infographic,
  Audio / Decision, Chart) at a fixed 8rem width; the column starts at, and cannot be
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
  Story, Conversation or FAQ (`audio_style`; FAQ is questions and
  answers in two voices); with Conversation or FAQ a **Second voice**
  select appears with its own sample button (`audio_voice_2`, sent for
  those two only; in an FAQ the first voice asks, the second answers),
  starting with the next voice of the
  first one's language, as rag would pick it, and never the same as the
  first (changing the first to the second's voice moves the second on).
  For a report a **Style** (Briefing, Detailed, Executive summary,
  Explainer, Academic) and a **Length** (short, medium, long); for a quiz
  the number of **Questions** (5–30), a **Difficulty** (easy, medium,
  hard) and an **Audience** (children, teens, adults, experts); for
  flashcards the number of **Cards** (5–50, 15 by default) with the
  same Difficulty and Audience (the flashcards' own lists and defaults
  from rag's catalogue); all from rag's catalogue with its defaults. Every kind has an optional **Notes
  for this output** field (the `instructions`, up to 500 characters,
  counted), with the hint that whoever the output is shared with sees
  it; blank notes are not sent. The share page and "How this was made"
  show them as "The author's instructions".
  They start from the
  user's preferences, else rag's defaults, and go into `options` of the
  create request with only the keys the kind takes. The viewer and the
  shared page show what a document was made with ("Deutsch · Ryan ·
  1.25×", "Conversation · Ryan & Aiden · 1×").
- **Notebook list** rows never wrap on a desktop: the name (with the
  Starter badge) gives way and cuts with an ellipsis, shown in full as
  tooltip, and its icons (☆ for an admin, share, ×) keep their width at
  the right. In the stacked phone layout a row may put the whole icon
  group under the name, never one icon alone. The **Outputs** rows keep
  the kind and status at their natural width with the title between
  them, cut with an ellipsis.
- **Renaming**: a double-click (or F2) on a notebook in the notebook
  list, on an output's row in Outputs or on its tab in the viewer turns
  the title into a field, as on the chat tabs: Enter or leaving the
  field saves (`PATCH /api/ingest/notebooks/{id}`, `PATCH
  /api/rag/outputs/{id}` with `{title}`, up to 200 characters), Escape
  cancels; an empty or unchanged title saves nothing. An output is
  renamed once it is ready (before, the worker would overwrite it). The new title
  shows at once and the old one returns if the service refuses it.
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
- **Viewer** (right, top): one tab per output or source the user
  opened (an output from the Outputs list, a new output on Create, a
  source by clicking its name in the Sources list, either from a
  citation), in the order opened; the lists stay the index. Opening one
  that is open brings its tab to the front; each tab has a ×, and
  closing the active one shows its right neighbour, else the left. The
  set and the active tab are kept per notebook for the browser session
  (sessionStorage), so a reload keeps them; a deleted output's or
  removed source's tab goes. Without tabs: "Sources and outputs you
  open appear here as tabs." A source tab shows the kind before the
  name; its view has the name, kind, an **Original | As read** switch
  and a small ↗ that opens it in a new browser tab. **Original**: an
  image inline, audio in a player, a PDF in the browser's viewer in an
  iframe (at the cited page when a citation opened it), a web page as
  the snapshot of the version that was read (`snapshot_url`, one
  self-contained HTML file without scripts or images) in a sandboxed
  iframe (no scripts, no same origin; its links open in a new tab)
  under "Snapshot from 14.10.2026 14:05, version 2 · live page ↗" (the
  live page at its address after redirects; before the page is read
  "No snapshot yet" and the live link alone), a text or Markdown file inline (`GET
  /api/ingest/sources/{id}/text`, also before it is read: plain text in
  monospace, Markdown rendered and sanitized like a report; over 2 MiB
  the service's sentence with a link to the file). The tab keeps the presigned
  address it opened with, a web page its snapshot's (a re-listed source
  gets a new one, and a new `src` would fetch the file again) and takes the list's only after 50
  minutes, before it expires, or after a reload, when it has none. **As read**: the text the system
  extracted and answers from (`GET /api/ingest/sources/{id}/chunks`),
  50 chunks a page with previous/next, each with its number ("Chunk
  12", and the page for a PDF); opened from a citation it loads the page
  the cited chunk is on, marks it and scrolls it into view. A source not
  read yet says "Not read yet: it is read when you ask or create." with
  **read now** and its price (ingest's estimate; the basis beside it). As read is
  the default for text and web pages, Original for images, audio and
  PDFs. An output's header shows
  "from 3 sources" when it was made from a selection, processing tabs
  show a spinner and poll. While an output is made (waiting or
  processing) the pane shows, centred, a small muted skeleton in its
  kind's shape with a slow shimmer (report: a heading and lines; table:
  a grid; mind map: three connected nodes; audio: a pulsing waveform;
  flashcards: a card turning; quiz: question lines with option dots;
  chart: bars; decision: a scale with its mark; infographic: blocks),
  static under reduced motion, in the theme's line colour. Under it what
  is really happening, from the output's `phase` (only what the worker
  wrote): "Reading the sources: a.pdf", "Choosing the passages",
  "Weighing the decision", "Writing", "Checking against the sources",
  "Judging, round 2 of 3", "Revising round 1", "Speech, segment 3 of
  8", "Indexing for the chat", "Attempt 2 of 3 follows (glm-5.3:
  timeout)", then " · 1:42", the time since the output was created.
  Without a phase (queued, or an older row) "Generating…" or "Waiting:
  its sources are read first…" with the time; a retry's error shows
  under it unless the phase already says it. Each kind has its own renderer; the audio
  player with its transcript sits centred in the pane while it fits and
  starts at the top once the transcript is longer, so the player is
  visible without scrolling and nothing runs over the header or under
  "How this was made", and the mind map fills the pane and
  re-fits whenever its size changes (full view, divider, window). A
  small bar on the map's top right zooms in (+), out (−) and fits it
  again (⤢); with the map focused, the keys +, − and 0 do the same.
  Actions per document: ask about this, print, share, full view.
- **Column dividers** between the notebook list, the left column and
  the right column: drag them (or arrow keys when focused) to change the
  widths, remembered per browser in pixels; a double-click (or Home)
  returns to the default. The notebook list stays between 160 and 420
  px, the left column between 378 px (the format grid, three tiles a row) and 720 px,
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
  generated document opens that tab. rag checks a cited answer like a
  document: a paragraph whose words the cited passages lack gets the red
  "Word check: words missing" badge after it (amber "Not word-checked
  (other language)" when the answer is in another language than its
  sources, followed by **Have it judged · €x**, which opens the answer's
  Check with a judge at Medium, priced there),
  the paragraph stays, and "Word check: words match in N of M
  paragraphs" sits under the answer (method and threshold as tooltip).
  "Supported" is the judge's word: the word check claims no meaning.
  Every word-check badge has the same tooltip: "The word check compares
  words only: it sees no meaning and no negation. That is what the judge
  is for." A paragraph with a judge's verdict shows only the judge's
  badge; the word check's result is the last line of its tooltip. A
  judge without a usable answer ("no answer") leaves the word-check
  badge shown.
  Above Basic, rag checks an answer at the user's **Verification by
  default** inside the request (Standard: a low judge on the paragraphs
  the word check doubts; Thorough: the medium judge on every
  paragraph; marking only): while it waits the chat says "answering and
  checking (Standard)…", and the answer's judged paragraphs carry the
  judge's badges, with "Judge (low, model): 1 of 2 doubted paragraphs
  supported" (or "N of M supported" when all were judged) under it. The
  agent asks "How thoroughly should the new documents be checked?" with
  each level's price as its choices, and notes "Basic check only" at
  Basic, both through the plan card as any question.
  Answers without citations and older messages show neither. Under
  every answer a row: **Copy** (the answer with its `[n]` markers, then
  "Sources:" and one line per cited passage, `[n] name, p. x: "…"`;
  without the clipboard API the answer is selected), 👍 and 👎 (`POST
  /api/rag/messages/{id}/feedback`; the rating shows pressed and can be
  changed; 👎 opens a one-line comment field, optional, sent with Send
  or Enter, Esc closes it; a down-rating's comment shows beside it).
  Under the last answer its follow-up questions (`suggestions`, up to
  three) as cards; a click asks it. An empty chat has **Suggest
  questions** with its price (`chat_answer` with `suggestions`), which
  loads the notebook's questions (`GET
  /api/rag/notebooks/{id}/suggestions`) as the same cards, or says
  there are none until a source is ready. It is a click, not automatic:
  the first call is billed. The question field says "Ask, or tell me
  what to add and create…": an answer can be a **plan** (rag's agent,
  `plan` on the answer and on its message). It shows as a card under
  the answer: the steps numbered, each with its label and estimated
  price ("free" for a listing; an invalid step struck through with its
  reason, it never runs), "Total ≈ €…", and a web page's processing as
  its own line beside the total, not in it ("Process the web page ≈ €…",
  billed by ingest at the price list's price). **Run** confirms it,
  **Cancel** ends it (every step skipped). While it runs the card polls
  every 2.5 s and each step shows queued, running, waiting, done, failed
  or skipped with its error; a step that added a source or made an
  output links to it and opens it as a viewer tab; a listing shows what
  it found, a library add how many it added. Each done step reloads the
  Sources and Outputs lists and the conversation, where an explanation
  arrives as a normal cited answer and, at the end, the plan's summary.
  After a reload the card shows the plan as it stands. A plan can first
  **ask** (status `asking`, `plan.question`): its question with two to
  four choices as buttons, the preselected one outlined in the accent,
  each with the plan's price if taken; a text field too when the
  question allows one. Run stays disabled until it is answered (`POST
  …/plans/{id}/answer`), then the card shows the updated steps and
  total and every question answered so far as a line, "question →
  answer", in order (`plan.answered`). The first use is the judge:
  "With a judge (High, your default)" or "Without a judge". The plan's
  notes (`plan.notes`, e.g. "Without a judge: …") show under it, and
  what its outputs read, documents and pages alike (`plan.sources`,
  "Reads: a.pdf, b.txt, Wikipedia (as of 15 h ago)"). Web pages a plan
  reads come as such a question too ("use the versions already read" or
  "fetch them again", the extra cost in its label), one question after
  the other. The plan's later summary message shows the outputs it made
  as their titles, each opening its tab, instead of the card again.

## Viewer, print, share

- **Output ID**: every output can be named by its ID, the output's UUID,
  shown as its first 8 lowercase hex characters (core's `short_id`):
  "ID 3f9c21ab ⧉", where ⧉ copies the full ID (without a clipboard it
  selects it for Ctrl+C). It stands in the viewer's head after the kind
  and the date (also in the library's read-only view of a
  document whose notebook is gone), in full as the first row of **How this was made**, at
  the end of every output error (failed, and a retry's error while it
  is made), next to each output a plan made in the chat (its step and
  the summary message), and in the Outputs list only in the row's
  tooltip. The share page shows no ID.
- **Provenance**: a click on `[n]` (in the answer or in the citation list
  under it) opens a panel under the answer: source name and kind, page,
  "chunk 12 of 43", the similarity of that chunk to the question as a
  number and a bar, and the chunk text verbatim, with the sentence that
  shares the most words with the cited statement marked (a best guess:
  the backend sends no span). For an upload "open in source" opens its
  source tab in the viewer at the cited page and chunk (see Viewer) and
  highlights the source in the list; a small ↗ next to it still opens
  the source in a new browser tab through its `preview_url` (a PDF with
  `#page=<n>`). For a generated document the link reads "open
  document": it opens that document's tab and shows the passage: in a
  report, quiz, table or infographic the text block sharing the most
  words with the chunk scrolls into the middle and flashes; a mind map
  fits and flashes the node whose label matches the chunk's first line
  (or only fits). Also in the full view. The citation list under an
  answer, like a document's **Sources**, has one row per source with
  its page and passage numbers, e.g. `handbook.pdf · p. 27 1 2 · p. 31 5`
  and `faq.txt 4 7`, headed "Sources (4) · 8 passages"; each number
  opens its passage, its tooltip gives the similarity.
  Citations from before this carry no position or similarity; the panel
  completes the position and the full text from `GET /api/rag/chunks/{id}`
  when the chunk still exists. Shared documents carry no citations, so
  the shared page has no panel.
- **Viewer**: a clean document view with title, date, the sources it was
  made from. Report as Markdown, quiz interactive with reveal, table
  sortable with CSV export, mind map with markmap (labels wrap at
  280 px; fitted once drawn and on every size change of the pane, never
  while it has no size; built again only when its content changes),
  infographic as a
  card grid, audio as a player with the transcript under it (a
  narrator's paragraphs as text; a conversation or an FAQ with each turn's speaker,
  named by its voice, in front; documents made before transcripts have
  none). The player stays at the top while the transcript scrolls, on
  an opaque bar (the panel colour, a line under it) the full width of
  the transcript. With
  per-entry times (`start`, `end` in seconds within the MP3) the entry
  being spoken is marked and kept in view as it plays, and a click (or
  Enter) on an entry plays from its start; a citation marker in it stays
  a citation. Older audio without times marks nothing. **Flashcards** one card at a time: "Card 3 of 15" over a large
  card that a click (or Space or Enter, with the cards focused) turns
  between front and back; ← and → (buttons and keys) move, wrapping;
  **Shuffle** mixes the order. A card with a hint offers "Show a hint"
  on its front. On the back the passages' `[n]` markers and the check's
  badge, as in the quiz (the back is the claim, checked with its
  front), and **Knew it** / **Again**, which mark the card for this
  session and move on; "7 known · 2 again · 6 open" above the cards.
  **List** shows every card, front over back with its markers, a mark
  as a green or amber edge. **CSV for Anki** downloads `front;back`, one
  card a line, both fields quoted. Nothing is saved; the share page
  shows the same, read-only by nature.
- **Verification**. Every kind but the chart has the option
  **Verification** (`verification`, from rag's catalogue): Basic (words
  and negation: the word check and the negation check, no model),
  Standard (also a low judge on every paragraph those doubt, marking
  only), Thorough (the medium judge on everything, revising and removing
  up to three rounds), and Bulletproof once rag lists it. Each level
  names its full price from the estimate's `levels`, with a line on what
  it does; it starts at the user's **Verification by default** and is
  sent only above Basic. The negation check marks a paragraph whose words
  match but whose statement is reversed: amber "Word check: possible
  contradiction", counted in the head ("· 2 possible contradictions").
  At Standard the head reads "Judge (low, model): 2 of 3 doubted
  paragraphs supported" and "How this was made" lists that one pass.
  Where rag offers no verification yet, the older **Check with a judge**
  option shows instead: Off (default), Low, Medium or High (the model
  per level from rag's catalogue), with a line on what the level does. A judge reads
  each claim against its passages while the output is made; claims it
  fails are revised or taken out. In the output each claim gets a second
  badge next to the word check's: supported (green), contradicted (red),
  not in source (dashed) or no answer (dashed; the judge gave no usable
  answer twice, its reason in the tooltip, never counted as a
  disagreement), amber-outlined where the word check reads it the other
  way. A click on it opens the provenance panel at the
  claim's first passage with the judge's verdict, reason and decisive
  quote. Under the document a list **Removed after judging (N)** (text,
  verdict, reason, round) is always shown when there is one; the head
  says "Judge (medium, model): N of M passed after K rounds", and "How
  this was made" lists the rounds (judged, verdicts, tokens, revisions)
  and any later judgings. **Check with a judge** on an existing output
  (in the viewer's head) and under a cited chat answer: a level and
  Check, one billed call that annotates every claim and removes nothing;
  the line under the level says so for every level, since revising
  happens only while an output is made.
  The share page shows all of it. The estimated charge of the chosen
  level stands next to Check (see "Prices").
- **Chart** ("number series from the sources, drawn and checked"). Under
  the tiles: the optional notes, how many charts at most (1–12, 6 by
  default) and **Find charts**, one billed model call (`POST
  /api/rag/notebooks/{id}/charts/propose` with the selected sources and
  the pages to fetch again, as Create sends them; without credit the
  voucher dialog). Candidates belong to the notebook, the selection,
  those pages and the notes they were found for: when any of these
  changes they are dropped, never sent, and the area says "The sources
  or the notes changed: find charts again for the current selection"
  (also what rag's `chart_out_of_scope` refusal on Create reads). The candidates come back as small previews, each with its
  title, type, number of values and how many the check backed, and a
  checkbox (all ticked to start); none at all says why ("the sources
  contain no number series"). Create sends the ticked ones as proposed.
  The output draws each chart with recharts in the overview's style and
  colours (bar, stacked bar, line, pie, scatter): a value the check
  backed is filled, one it did not is hollow, one computed from other
  values (a share, a sum) is a diamond; a click on a value opens its
  passage in the provenance panel, a computed one at the first value it
  was computed from. Each chart has PNG and CSV downloads and its values
  as a folded table with their markers ("computed from [3] [5]",
  "unsupported"); the head says "N of M values supported" (and no word
  check line: a chart has values, not paragraphs). Recharts is
  loaded only when a chart is proposed or opened. Read-only on the share
  page.
- **Decision** ("a question weighed against the sources"). Its options
  under the tiles: the question (required, multi-line, counted against
  rag's 500 characters), "Answer as" Yes / No (default), Choice or Scale;
  for Choice an editable list of 2–8 options, for Scale 3–7 ordered
  levels, lowest first, preset "very unlikely … very likely". Create
  waits for a valid form and says what is missing. The document: the
  question as its title (not repeated as a heading under it while the
  title is the question), then the decision model's answer in a panel:
  yes/no as the answer in words over a horizontal bar, yes filled from
  the left, "Yes 77 %" and "No 23 %" at its ends, a mark at 50 %; a choice as one bar per option with the model's answer
  highlighted and its confidence, a scale as segments with the level it
  lands on filled and a mark at the weighted position; under it the
  verdict, and whether the decision model and the evidence agree
  (green), disagree (amber, never hidden, with "model: B, evidence: A"
  when they name different options), cannot be told, or the sources do
  not decide it, with rag's one-sentence reason. When the sources do
  not decide it (agreement "undecided", rag's `model_answer` null) the
  panel, dashed, says only "No decision: the sources do not contain what
  is needed." with the reason: no number, no bar, no verdict line, for
  older documents with numbers too. Then Evidence for and
  Evidence against side by side (stacked on a phone) with their markers
  and badges, and "What the sources do not say". "How this was made"
  lists both calls (decision and evidence: model, prompt, duration, the
  passages and characters the decision model read) and "Model's answer
  without evidence (not from the sources)" when rag stores it. The bars grow in on
  opening, not under reduced motion; only the theme tokens colour it.
  Printable; on the share page read-only like every kind.
- **What a document rests on** (rag's `provenance`; documents made
  before it have none and show none of this). A report's `[n]` markers
  are buttons, as in a chat answer; an infographic's facts and sections
  and an audio transcript's turns carry their markers after the text. A
  click opens the chat's provenance panel under the document for that
  passage (source, page, chunk position, similarity, the chunk with the
  sentence closest to the claim marked, "open in source"). A claim the
  check found too few words for has a red "Word check: words missing"
  badge, one written in another language than its sources an amber
  "Not word-checked (other language)" with **Have it judged · €x**
  (opens Check with a judge in the viewer's head, at Medium; not in a
  mind map's labels and not on the share page); the claim stays. A
  claim with a judge's verdict shows only "Judge: …", the word check in
  its tooltip. The head says
  "Word check: words match in 7 of 9 paragraphs · 2 in another
  language" (the check's method and
  threshold as tooltip). Under the document, folded: **Sources (n) · m passages**,
  the passages it cites grouped by source (one row per source, its pages
  and passage numbers, each opening its passage), and **How this was made**: model, prompt version,
  options, the retrieval query, usage, when and how long, the check's
  counts, the retrieval candidates with similarity and whether they went
  into the prompt, and the whole log as a JSON download. The share page
  shows all of it read-only, without "open in source". A table row's
  markers sit in a narrow last column (they follow the row when it is
  sorted; the CSV has no such column), a quiz question's after the
  question, a mind map node's in its label (a click on a marker shows
  the passage; the node's circle still folds it).
- **Print**: a print stylesheet on the viewer and a button; the browser
  produces the PDF. Report and table are the printable kinds.
- **Share**: creates a share token and shows the link `/s/<token>`; the
  page renders the document read-only without login and records a
  visit. Revoke from the same place.
  The shared page is as tall as the window: report, quiz and
  infographic sit in a centred reading column, the mind map and the
  table use the full width, the audio player is centred.
- **Share a notebook**: the ⤴ button in a notebook's row of the notebook
  list (accent while shared) opens a card under it to create the
  read-only link `/shared/notebook/<token>` (`POST
  /api/ingest/notebooks/{id}/share`, the same token until revoked), copy
  it or revoke it. The public page, without login: the notebook's title,
  its sources by name and kind (no files), a list of its outputs to jump
  to, then each output oldest first as on its own share page (passages,
  how it was made, no source to open; `GET
  /api/rag/shared/notebooks/{token}`).
- **Ask about this**: switches the chat scope to the open document
  (`scope.output_id` on `/ask`); a chip above the input shows the scope
  and clears it.

## Settings

`/settings` (in the header next to Library): first a row **Credits and
prices**, "Balance €X · View credits · Price list" (two plain links);
"Show the introduction again" (see Adding sources); then interface language
(browser default, English, Deutsch), language of generated documents
(same as the sources, or one of rag's languages) and the voice for
audio (default, or one of rag's voices, with the same sample button),
and the days a deleted
library source stays in the trash (1–365, empty for 14), and how PDFs
are read by default (Auto, Text or Vision). Saved together with
`PUT /api/account/me/preferences`; an empty choice clears the value.
The preferred language and voice are preselected in the output options
and used by the wizard, which has no option menus. **Verification by
default** (`verification_level`: the levels rag offers, a stored one rag
does not offer yet kept in the list) preselects new outputs'
verification when rag offers that level, and is the level chat answers
are checked at; changing it for one output does not change the
preference. Against a rag without verification levels the older **Judge
by default** (`judge_default`) shows instead. The interface
language is stored here and applied by the translation layer. The
shared demo account cannot change settings (403, shown as the
service's sentence).

## Library

`/library` (in the header next to Admin), two views: **Library** and
**Trash**. The library is one table of every upload, URL and
output of the user, once, newest first (`GET /api/ingest/library?kind=all`).
Above it a view selector (All, Sources, Outputs, pills like the output
kind chips) and filters by kind (source kinds, and the output kinds for
outputs), by notebook (or "not in any notebook") and by part of the
name or address. Columns: kind (an output's kind, from rag's
list of the user's outputs joined by `output_id`), name, status (a
failed entry's reason on one line next to the badge, in full as its
tooltip; a processing or waiting entry's `error` on the same line, as
in the notebook's source list; "added · processed when you have credit" muted; no notice about
credit: an action waits for credit with the sources it uses, and the
voucher hint is at Create and Ask), size ("unknown"
for entries added before sizes were recorded, none for outputs), date,
and the notebooks it is in as links (or "not in any notebook"); a
output also says where it was made ("made in test1", or "made in
deleted notebook "test1"" once that notebook is gone). **Open** works
per type: an upload in a new tab (a web page at its address, an upload
through its presigned `preview_url`; the name too; only `http(s)`
addresses are linked, without a preview the action is disabled with a
note); an output goes to the notebook it was made in with it selected,
or, when that notebook is deleted, shows it read-only on this page as
the share page does (print where the kind has it, no sharing). A ready output's row also has
**share** ("shared" once it has a link): it opens the viewer's share
card under the row (create the read-only link, or copy and revoke it).
**Checking an audio source** (here and in a notebook's Sources list): a
play button per audio row mounts a player for that row only (nothing
loads before; one player at a time, a second click closes it), with a
download link "transcribed audio" (the file that was transcribed: the
converted MP3, or the upload itself for MP3 and WAV) and, when the
upload was converted first, "original" (`original_url`). Open still
takes the transcribed file.
Each row has a checkbox ("all / none" in the column header acts on the
rows the filters show; ticks survive a filter change), across sources
and outputs. With rows ticked a bar above the table offers:
**New notebook from n** (a title field in the bar next to the button,
Enter or the button creates, Escape clears it; preset with the first
file's name without its extension, else the first web page's title or,
from its address, host and last path segment, "en.wikipedia.org · Dead
reckoning", never the raw address; the notebook is created, the entries
linked in one call, `POST /notebooks/{id}/sources/bulk`, then it opens);
**Add to notebook…** (a list of the user's notebooks, each saying "2 of
3 already in it"; a click links only the missing ones in one call, and
a line says "2 added, 1 was already in test1"; a notebook that has them
all is disabled and says so; outputs that are not ready are left out,
since ingest refuses the whole call for one); and **Delete n** (one
confirmation naming every notebook the entries leave, then one delete
per entry with "n of m" in the bar, an upload through ingest's trash, a
output through rag's; after a failure the rest stays ticked).
Delete moves the entry to the trash, out of every notebook, after a
confirmation that names those notebooks; an output's share link stops
working while it is there. The **Trash** view lists deleted uploads with
the date they are purged (after the trash days set in the settings, 14
by default; "settings" links to that field): restore puts one back in
the library in no notebook, "delete for good" removes the file and its
passages at once (uploading the same file or URL again restores it
too); and, under them, the trashed outputs, with restore (back into
the notebook it was made in, if that still exists; other notebooks need
it added again) and delete for good.

In the library and the trash every row stays one line: a long name (a
URL, say) is cut with an ellipsis and shows in full as tooltip, and the
starter badge follows it without overlapping. An image entry there has no
thumbnail; hovering or focusing its name shows a preview up to 320 px
next to it, kept inside the window (loaded only then), and leaving or
Esc hides it. In the wizard's picker an image keeps a small square
thumbnail in front of its name, loaded lazily from the entry's
`preview_url`, with the same preview on hovering the thumbnail or the
name or focusing the thumbnail; on touch a tap on the thumbnail opens it
without ticking the row, a tap elsewhere closes it.

A new account gets a copy of the starter notebook, if an admin has set
one: the notebook with its sources, ready, and its outputs a few
seconds later. While the open notebook has starter sources and no
outputs, its outputs list is fetched again every 2 s, for at most 60 s,
until they appear. The copied entries are marked "Starter" in the library,
the wizard's library picker and the notebook's source list (ingest's
`starter` flag; `demo`, its earlier name, counts too). For admins and
viewers the starter notebook carries a "Starter" badge in the notebook
list; an admin's other notebooks have a ☆ button, "Use as starter
notebook", which asks for confirmation and sets it (`PUT
/api/account/admin/settings/starter-notebook`); a refusal (sources not
all ready, a notebook an admin does not own) shows the service's
sentence. Admin > Access has a **Starter notebook** card: the notebook
(its title when it is one of this admin's, else its id) as a link that
opens it, who set it and when, and Remove (after a confirmation; the
notebook stays); without one, "new accounts start empty". The library
page polls while entries are still processing, so they turn ready on
their own.

A citation whose source is no longer in the notebook (detached, or
deleted from the library) stays readable with its quote and is marked
"source removed".

## Login, credit, admin

- Login page: under the name the tagline, its first part bold
  ("Material in. Understanding out.") and the rest as a muted line;
  one field, the e-mail address; then "check your mail";
  the link lands on `/auth/callback` and the app is open. An address
  without access is told "This address has no access to lasteverLM."
  and no mail goes out. Under it, "Have a sign-in code from the mail?"
  takes the code the mail prints under the link (the same single-use
  token, for another device): 43 characters of letters, digits, `-`
  and `_`, counted while typing, Continue enabled once it matches, an
  eye toggle to show it; it is exchanged like the link, and an unknown,
  used or expired code says so.
- Header: the balance in EUR as a pill that opens **Credits**; a 402
  anywhere opens the one-field voucher dialog. When there is credit, just
  not enough for an output or a plan (rag's `credit_insufficient`), the
  dialog and the error say "This needs up to €X, you have €Y.", with
  "(€Z is held by work still running.)" when started work holds some;
  otherwise "Your credit is used up".
- **Credits** (`/credits`, signed in; from the header's balance and
  from Settings): the user's own credit from `GET
  /api/account/me/credit`. On top the balance, large, with what was
  credited and spent in the chosen range, a "Redeem a voucher" field
  (the existing redeem call; the balance and the page reload after it)
  and a link to the price list. **Spending**, with 7 / 30 / 90 days:
  a small bar per day (spent, the day's amounts as tooltip) and a table
  per action (what, count, total; the action named as on the price
  list, the judge per level). **Entries**, newest first, 50 at a time
  with "Show more": date, what ("Report in notebook test1", "Source
  linux_vi.pdf processed", "Question to your sources in notebook Fog",
  "Voucher redeemed", "Credit granted"; a deleted notebook, output or
  source named as deleted) and the amount (charges with a minus,
  credits with a plus). A line links to its notebook, and to its output
  in a tab, while they exist. End prices only, no costs or margins.
- **Prices** (`/prices`, no login, linked under the login page's forms,
  in the header next to Settings and at the top of Settings): the
  public price list from `GET /api/account/prices`. With a session
  (a token in storage) it sits under the app's normal header, Prices
  marked active; without one under a reduced header: the brand,
  Prices and Sign in. A title and one intro paragraph, before the
  tables: where the prices come from (the last N days' actions at
  today's prices) and the rules in plain words (adding a source is
  free, processing it costs as listed below, the estimate for one's own
  choice is shown before every action, credit does not expire); then
  one table per group: **Sources** (text, PDF (Text),
  PDF (Vision) per page, image, audio per minute, web page), **Chat**
  (per question), **Outputs** (every kind, per output), **Extras** (the
  judge per level, "Judge, low", "Judge, medium", "Judge, high", from
  the `judge:<level>` rows and their `level`, low to high; then Find
  charts and the rest; under the table a note that these are the judge
  asked for on an existing output or chat answer, and that a judge
  chosen while creating an output is in that output's price). The
  group is the action's prefix (`source:`, `output:`, `chat_answer`,
  everything else), a way of reading a kind (`source:pdf:vision`) right
  after the kind, so an action the web does not know yet is still
  listed, by its code, last in its group. Columns: what; the price per
  unit (the unit translated: per question, per output, per page, per
  image, per web page, per minute of audio, …), as a range "€0.01–€0.05"
  when the service sends a minimum and a maximum that differ as shown,
  "+ €0.01 per source" when a source has a part paid once, and
  "· estimated", muted, when the price is an estimate rather than
  history (its tooltip says so); "no price yet" when none could be
  made. Then "Typical per action" (p25–p75 and the median of whole
  actions from history; "no experience yet" below five runs) and the
  model, muted, hidden on a phone. Prices from ten cents up show whole
  cents; below that two significant digits (€0.0035, €0.035). Under
  the tables the exchange rate ("1 EUR = 1.1188 USD, ECB reference rate
  of 2026-10-13"). No margins, fees or costs: the service sends end
  prices only.
- Reading on use: Create and Ask send the notebook (and the selection)
  with their estimate, and rag lists reading each unread selected
  source ("Read a.pdf", its basis as tooltip) and re-reading each page
  to fetch again on their own lines under the price ("+ Read a.pdf ≈
  €0.03"), not in it: ingest bills them apart. Above Create (once a
  format is picked) and above the chat's question field, each selected
  web page that was read has its own choice, **cached (fetched 3 h ago)
  | fetch again**, cached by default; the pages to fetch again go as
  `url_refresh` (library ids); the chat has no such line (it listed
  only the pages and could not change an answer already given): an
  answer that cited a web page says "Web page <name> as of 15 h ago"
  under it (`web_pages`), with **fetch again**, which asks the same
  question again with that page in `url_refresh`. A selected source rag cannot read (its
  estimate's `blocked`, e.g. "Source '…' could not be read: the page has
  no text without a browser") stands in for the price with its reason,
  "turn it off" (deselects it) and, for a web page, "fetch the page
  again" (adds it to `url_refresh`); Create stays disabled while any is
  listed, since rag would refuse it (409). Above the question field the
  same lines show, but Ask stays: the answer uses the rest and says what
  it could not read. While a question reads sources the chat
  says "reading 2 sources…"; an output waiting for its sources says so;
  both reload the Sources list after.
- Prices: before anything billed runs, its estimated charge from rag's
  `POST /api/rag/estimate` stands next to the button that starts it, in
  euro as the balance: before Create (for the kind with its options, a
  judge level included, asked 400 ms after the options stop changing),
  next to Check with a judge (for the chosen level and the output's kind,
  a quiz with its question count; a chat answer sends no kind, so rag
  assumes a report's claims), next to Find charts, and under the chat's
  Ask ("per question"); the voice sample's tooltip has it for a sample
  not played before (one played before is free). Shown in whole cents,
  rounded outwards: "≈ €0.03–€0.09", "≈ €0.05" when both ends meet,
  "up to €0.01" when the low end is under a cent; the tooltip says it is
  an estimate and the booking counts what is really used. While pricing
  has no exchange rate (503) it says "no price set yet" in red, with
  "ask an admin" in the tooltip, since the action fails the same way;
  any other failure (options that do not fit yet, 422) says "price
  unavailable" muted, with the error in the tooltip and that the action
  still costs credit, so a missing price never reads as a free one. The
  voice sample's tooltip says either instead of the price.
  One request per distinct question for five minutes.
- Narrow screens: no page scrolls sideways. Below 900 px the notebook's
  columns stack (sources and documents, then viewer, then chat); below
  640 px the header takes two lines, brand and account (theme, balance,
  sign out) above, the navigation below, and leaves out the e-mail
  address. The architecture diagram on Admin > System scales to its
  card; wide admin tables scroll inside theirs.
- Admin (for the roles `admin` and `viewer`): pages under `/admin` with
  a sub-navigation (Overview · Finance · Users · Access · Security ·
  Visits · Mail · System); each page loads only its own data, every page has
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
    stay a muted detail. Then **Answer feedback, last 30 days: 👍 n · 👎
    m** (`GET /api/rag/admin/feedback`), which unfolds the newest
    down-rated answers (time, question, answer, comment); a viewer sees
    the counts and "Details for admins only." in place of the list. Below, the
    charts in a two-column grid of equal
    cards and one shared time range (7 days while everything happened
    in the last week, else 30, with a 7 / 30 toggle): cost and credit
    granted per day next to logins and visits, chat messages and
    documents next to sources added per day by kind, documents by kind
    (donut) next to cost by model (all time), the top users (all time)
    across both columns. A chart without data in the range is not
    drawn; one quiet line names those ("No data yet: …").
  - **Users** (`/admin/users`): on top **Find an output by ID**: the ID
    a user quoted, at least 6 hex characters (hyphens and case ignored;
    Find stays disabled until then), `GET
    /api/rag/admin/outputs?id_prefix=…`. Each match shows title, kind,
    status, trash, the full ID with copy, the user (e-mail masked for
    viewers by rag) and id, the notebook (or "(deleted)"), created and
    finished, the attempts count, the public error and a table of the
    failed attempts (attempt, when, service, model, failure kind,
    provider HTTP status, message); none says so; more than 20 says to
    type more. Below, users with their role (for an admin a
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
  - **Access** (`/admin/access`): "Who gets in" in two blocks that read
    the same way, a heading and its line, then Domains | Single
    addresses side by side (stacked on a phone), one entry at a time:
    **Sign-in** (who may sign in) and **Viewer (read-only admin
    panel)**: a new user at one of those domains or addresses (also
    allowed to sign in) starts as viewer.
  - **Finance** (`/admin/finance`, in the menu right after Overview):
    pills for its five pages, each with its own URL under
    `/admin/finance/`, and one date range for those that take one
    (7, 30 or 90 days, or two dates), in one row at one height: the day
    pills, the labels and the date fields are all 2.3rem, like the
    selects. Every amount is in euro, as core books it, and every money
    cell, tile and total follows one rule: two decimals from 1 € (or $1)
    up, below that two to four decimals (€0.90, €0.6221, $0.0034;
    "<€0.0001" rather than zero), the exact value in its tooltip. The
    overview's cost and voucher tiles link here.
    - **Costs** (the default): grouped by day, action, model, user or
      service; per row the calls, actions, cost, the cost as measured
      in USD, the charge and the margin, with totals.
    - **Prices** (`/admin/finance/prices`): the exchange rate first,
      as a line "1 EUR = 1.1188 USD · ECB 2026-10-13 · checked 14:05"
      (the check's date too when it was not today; "set by hand" for a
      manual rate, "starting value" for the seeded one). It is amber,
      with a sentence saying the rate may be out of date, when the
      account service reports it stale (automatic mode, no successful
      ECB check for three days); a failed check's error is shown under
      it. An **automatic | manual** switch next to it (`PUT
      /admin/settings/pricing/rate-mode`): automatic is the ECB's rate,
      fetched at once and then hourly, with **Check now** (`POST
      …/pricing/rate/sync`), and leaves the rate field read-only;
      manual makes the field editable and pauses the update. Saving the
      form with another rate turns manual by itself (the account
      service does that). The switch keeps the rest of an unsaved
      draft. Then the margin on every action and, per action, a margin
      and/or a fixed fee (empty follows the default); 400 ms after
      typing stops the table previews, per action, the last 30 days'
      count, the average cost and what the user pays. Save, and "no
      margin, no fees", which keeps the rate.
    - **Revenue and profit**: tiles (charged, of which demo, paid and
      free vouchers issued and redeemed, outstanding credit), a chart
      per month or day (charged, model cost and infrastructure as bars,
      profit as a line) and its table; a value without a rate says
      "needs a rate" with a link to Prices.
    - **Infrastructure**: with a key set (`configured`), "Vultr
      connected · last successful sync <time>" only when a sync has
      worked and the last attempt did not fail; otherwise "Key set ·
      last successful sync: <time or never>". A last attempt later than
      the last success is added ("last attempt <time>"), then Sync now.
      A failed attempt's `last_error` (Vultr's own message, with where
      to allow the address for an IP refusal) stands under it in red.
      Without a key "Vultr is not configured." and how to set it; the lines with source and
      amount in their currency and in euro; lines entered by hand can
      be added and deleted, Vultr's cannot.
    - **Vouchers** (`/admin/finance/vouchers`; the old
      `/admin/credits` opens it): voucher creation as a form card above
    the list, at most 40rem wide: Amount (EUR, 5 by default) | Count |
    "Paid voucher" in one row; then, for an admin, "Send to an address
    right away", which opens below it, full width, the recipient's
    e-mail, a message with its counter and "also allow this address to
    sign in" (on by default), and mails each created voucher at once;
    Create at the bottom right. Every checkbox is one clickable unit
    with its text beside it. On a phone the row stacks and Create is
    full width. The codes are shown once under the card as chips with
    a copy button each ("copy all" for several; without the clipboard
    API the text is selected instead). The list of issued vouchers
    below: the code masked, and for an admin "show" (fetched once, with
    copy and hide; a voucher made before codes were kept says "code not
    kept (before 0.18)", the full sentence as tooltip), "sent
    to … , date" under the status once mailed; open ones can be sent
    (a dialog with the same three fields; a refusal for the quota of 5
    mails per address and hour, a missing mail server, the mail server's
    error or an already redeemed voucher stays in the dialog) and
    deleted. "Paid" on the create form and per voucher (in the list a
    checkbox with "Paid" or "Free" beside it on one line): paid is sold
    for its face value and counts as revenue, free is a gift and counts
    as a marketing cost.
  - **Security** (`/admin/security`): the rate-limit rule as a sentence
    with its five editable numbers (the ban cap, 1–365 days, among them) and a reset to the deployment
    defaults, then blocks, bans (with lift) and the raw access log.
    Blocks and bans are keyed by an IPv4 address or an IPv6 /64 prefix
    (`2001:db8:1:2::/64`), shown as is; lifting sends the key as a query
    parameter (`DELETE /api/account/admin/bans?ip=<key>`), so the slash
    of a prefix never reaches the path.
  - **Visits** (`/admin/visits`): visitor log aggregated per day and path.
  - **Mail** (`/admin/mail`): SMTP settings read-only (they come from the
    deployment) with a test button.
  - **System** (`/admin/system`): per service a card with version,
    commit and health; **Architecture**, a diagram (plain SVG, static
    layout, live numbers): the browser and the ingress at the top, web
    and the three API services below, the ingest and rag workers under
    their services, and PostgreSQL with pgvector, the object storage and
    the inference API as external boxes at the bottom, with arrows for
    the flows (ingress to the services, the services and the workers'
    job queues to PostgreSQL, the workers to storage and the models, rag
    to the models for answers); each deployment's box shows its
    replicas ready of total, its restarts when there are any, and its
    build (web, which has no healthz build, its pods' image tags, both
    while rolling out), coloured by its state: green when every replica is ready and
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
    does. The ingress box takes the account service's outside probe of
    the public URL (`ingress`, at most once a minute): red when it does
    not answer, amber when the certificate ends within 14 days, green
    otherwise, grey without a probe; under its title "TLS until
    2027-01-12", and as tooltip the URL, the time of the check and any
    error. In the light theme the external boxes and the dashed lines are
    drawn heavier, so they stay visible on white. A legend under the
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

Light or dark: a `theme` preference "light" (the default when nothing is
chosen), "dark" or "system" (following the operating system's setting),
chosen on the Settings page and saved in the account when signed in, so
it follows the user to other browsers, and in this browser. The toggle
in the header switches between light and dark for this browser session
only (sessionStorage; nothing is saved in the account, so the shared
demo account can use it too), starting from what is on screen (its icon
shows what a click gives; under "system" a click sets the explicit
opposite). On load the session's choice wins, else the saved one, else
light; a small script in `index.html` applies it before the first paint,
so a dark choice never flashes light. While the session differs from
the saved choice, the Settings page says so ("this session is on Dark;
your saved choice is Light") with "Use saved", which drops the
session's choice. One theme store (`lib/theme.ts`) holds both. Every colour goes through the tokens in
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
