# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Sources are read when used: a new source is "added · read when used" (neutral) with a small "read now" (its price first); Create and Ask list reading the unread selected sources and re-reading pages as their own lines under the price and say "reading 2 sources…" while a question waits; each selected web page has "cached (fetched 3 h ago) | fetch again" above Create and the question field (`url_refresh`); a page shows when it was fetched, "v2" once it changed, and ↻ to fetch again.

### Fixed

- Sources list: a source stays on one line, the name cut with an ellipsis (full name as tooltip) and kind, capture, status, play and × as one compact group; a narrow row moves the whole group below the name. The status badge is short, with a failed source's error and a waiting one's reason in its tooltip instead of under the row.

## [0.18.7] - 2026-10-14

### Added

- A first-login introduction: three steps (add sources, pick a format, Create; without credit "Redeem a voucher first"), each outlining its area with an arrow, Next/Back/Skip; shown once per user (the account's `tour_done`, this browser's note for the demo user), again from Settings.

### Changed

- "+ add" only adds sources: the dialog returns to the source tiles after each batch to add more, until it is closed; the output step at the end is gone (outputs are made in the Output format area).
- A source waiting for credit shows a muted badge "added · processed when you have credit" instead of the amber "waiting for credit", which read as an error; the voucher hint stays by Create.
- `/prices`: the rules (adding is free, processing costs, the price shows before every action, credit does not expire) are in the intro paragraph before the tables, not under them.

### Fixed

- Notebook list: a row stays on one line, the name cut with an ellipsis (full name as tooltip) and the icons together at the right; a narrow row moves the whole icon group below the name instead of wrapping the × alone.

## [0.18.5] - 2026-10-14

### Added

- Chat: an answer that is a plan (rag's agent) shows as a card: numbered steps with label and estimated price, the total, a web page's processing on its own line, Run and Cancel; while running each step's state live (polled), done steps opening what they made as a viewer tab, the lists reloading as steps finish. The question field reads "Ask, or tell me what to add and create…".
- Flashcards, a ninth format (rag's `flashcards`): cards (5–50), difficulty, audience, notes and judge as options with the price; one card at a time that turns on a click or Space, arrows to move, Shuffle, Knew it / Again with a progress line for the session, a list of all cards, the passages' [n] markers and the check's badge on the back, and a CSV for Anki (front;back); also on the share page.
- `/credits`: the user's own credit (the account service's `GET /api/account/me/credit`): the balance with credited and spent, a voucher field, spending per day and per action for 7, 30 or 90 days, and every entry linked to its notebook or output; opened from the header's balance and from Settings' new "Credits and prices" row.
- Chat: under each answer Copy (the answer with its [n] markers and the cited passages), 👍 and 👎 (with an optional one-line comment; changeable); under the last answer its follow-up questions as cards that ask on a click; an empty chat's "Suggest questions" with its price loads the notebook's questions as the same cards. Admin overview: answer feedback of the last 30 days with the newest down-rated answers.
- Sources open in the viewer: a click on a source's name (or "open in source" on a citation) opens it as a tab with two views, **Original** (image, audio player, the PDF inline at the cited page, a web page's address) and **As read** (the extracted text chunk by chunk with numbers and pages, the cited chunk marked; from ingest's `GET /sources/{id}/chunks`). The new-tab link stays as a small ↗.
- Starter notebook: admins mark one of their notebooks with ☆ "Use as starter notebook" (the account service's `PUT /admin/settings/starter-notebook`); it carries a "Starter" badge in the notebook list, and Admin > Access shows it with a link, who set it and Remove.

### Changed

- Admin overview: a viewer sees the answer feedback's counts and "Details for admins only." in place of the down-rated answers (rag's `detail`).
- The header's balance opens Credits instead of the voucher dialog (a 402 still opens it); Settings shows "Credits and prices" (balance, View credits, Price list) instead of the price list line.
- The viewer's tabs are what the user opened, sources and outputs, in the order opened, each closable, kept per notebook for the browser session; no longer every output of the notebook. Empty: "Sources and outputs you open appear here as tabs." The policy allows frames from the media sources (`frame-src`) for the inline PDF.
- The "demo" badge on copied entries reads "Starter" (ingest's `starter` flag, `demo` still read); the demo sources' first question in an empty chat is gone.
- Admin: Finance comes right after Overview in the sub-navigation (Overview · Finance · Users · Access · Security · Visits · Mail · System).

### Fixed

- Admin > Finance > Infrastructure: "Vultr connected" only after a successful sync; with a key that has not worked yet "Key set · last successful sync: never", the last attempt, and the failed sync's message from Vultr in red (account's `configured`, `last_success_at`, `last_attempt_at`, `last_error` replace `vultr` and `last_sync`).
- Admin: the top users and the allow-list addresses no longer use an address as a row's key, so two addresses the account service masks alike for a viewer still show as two rows.
- A source tab no longer fetches its file again whenever the source list reloads: it keeps the presigned address it opened with and takes a new one only before it expires.
- Admin > Finance > Vouchers: the create form is a card above the list (Amount | Count | Paid voucher, then "Send to an address right away" opening the full-width recipient, message and sign-in fields below it, Create at the bottom right, stacked on a phone); checkboxes no longer stretch away from their text, and the recipient field is full width. In the list the paid toggle keeps its word on one line, and a voucher without a kept code says "code not kept (before 0.18)" with the full sentence as tooltip.
- `/prices` shows the app's normal header (Library, Settings, Prices, Admin, theme, balance, sign out) when signed in; the reduced header (brand, Prices, Sign in) only without a session.
- `/prices` follows the account service's new rows: PDF (Text) and PDF (Vision) per page, image, web page, audio outputs per output; a price range when there is one, "+ … per source", "estimated" muted for an estimated price, "no price yet" when none could be made, and "Typical per action" as the history column's heading.
- Admin > System: the ingress box is coloured from the account service's outside probe (red down, amber when the certificate ends within 14 days, grey without a probe) with "TLS until <date>" and the probe in its tooltip; the web box shows its pods' image tags as its build.
- Admin overview: the meta line read "vv0.18.3"; the version keeps the Git tag's own "v" and gets one only when it has none.

## [0.18.4] - 2026-10-14

### Fixed

- Admin > Finance: the range bar's day pills, labels and date fields share one height and line; every money cell, tile and total follows one rule (two decimals from 1 € up, two to four below, the exact value in the tooltip) instead of €0.90 next to €0.622125.

## [0.18.3] - 2026-10-14

### Fixed

- Sources and the library: a source still processing or waiting for credit shows its `error`; the missing exchange rate ("pricing has no exchange rate, ask an admin") as it comes, in amber, instead of "Retrying after: …", which only a real retry still says.

## [0.18.2] - 2026-10-14

### Added

- `/prices`: the public price list (no login) from the account service's `GET /api/account/prices`: Sources, Chat, Outputs and Extras as tables with the price per unit (unit translated), the typical range (p25–p75, median) and the model, "no experience yet" below five runs, the exchange rate with its ECB date and the rules in plain words; linked from the login page, the header and Settings; the judge per level ("Judge, low", "Judge, medium", "Judge, high") under Extras, with a note that a judge chosen while creating an output is in that output's price.
- Admin > Finance > Prices: the exchange rate's origin as a line ("1 EUR = 1.1188 USD · ECB 2026-10-13 · checked 14:05"), amber with a sentence when the account service reports it stale, the last check's error under it, and an automatic | manual switch: automatic (the ECB's rate, hourly, with Check now) leaves the rate field read-only, manual makes it editable.

## [0.18.1] - 2026-10-14

### Added

- Prices: the estimated charge from rag's `POST /api/rag/estimate` next to every billed action, in whole euro cents rounded outwards ("≈ €0.03–€0.09", "up to €0.01"): before Create (the kind with its options, judge level included), next to Check with a judge (the chosen level), Find charts and under the chat's Ask; the voice sample's tooltip. Without an exchange rate it says "no price set yet"; any other failed estimate says "price unavailable" with the error in its tooltip.

## [0.18.0] - 2026-10-14

### Added

- Admin > Finance replaces Credits: Costs (cost and charge per day, action, model, user or service, with the measured USD cost), Prices (the USD per EUR rate, a margin and per-action margins and fixed fees with a live preview of what users would pay), Revenue and profit (charged, paid and free vouchers, outstanding credit, profit per month or day with a chart), Infrastructure (Vultr's charges, or how to connect it, and lines entered by hand) and Vouchers (as before, plus paid or free); a date range shared by the pages, the overview's money tiles linking here.
- Judge: an option "Check with a judge" (off, low, medium, high) for every kind but the chart, and a "Check with a judge" action on an existing output and on a cited chat answer (annotates only). Each judged claim shows a second badge (supported, contradicted, not in source; amber-outlined where the word check disagrees) whose click opens the passage with the judge's reason and decisive quote; "Removed after judging" lists the claims taken out, never folded; the head says "Judge (level, model): N of M passed after K rounds"; "How this was made" lists the rounds. Also on the share page.
- Admin > Credits: every voucher's code is shown masked, and for an admin "show" fetches it again with a copy button ("not recoverable" for vouchers made before codes were kept); an open voucher can be mailed from a dialog (recipient, an optional note, also allowing the address to sign in, on by default), and the row then says to whom and when; the create form can mail each new voucher right away. Refusals (mail quota, no mail server, the mail server's error, already redeemed) are shown in the dialog or the form.

### Changed

- Admin > Security: the ban cap ("a ban holds at most N days", 1–365) is a fifth editable number of the rate-limit rule, saved with the others; only the retention still comes from the deployment.
- Admin > Access: the viewer block mirrors the sign-in block: both have a heading ("Sign-in", "Viewer (read-only admin panel)") and their line, then Domains | Single addresses side by side, stacked on a phone; viewers can now also be single addresses (`viewer_addresses`).

## [0.17.1] - 2026-10-14

### Added

- Chart, an eighth output kind: "Find charts" proposes number series from the sources as small previews (title, type, values, how many backed) to tick; the output draws each chart with recharts in the overview's style, backed values filled, unbacked ones hollow, computed ones as a diamond ("computed from [n]"), a click on a value opening its passage, with PNG and CSV per chart and "N of M values supported" in the head.

## [0.17.0] - 2026-10-14

### Added

- Output options from rag's catalogue: a report's style and length, a quiz's number of questions, difficulty and audience, and for every kind optional notes (`instructions`, up to 500 characters) with the hint that a shared output shows them; the line under a title names the new choices, and the share page and "How this was made" show the notes as "The author's instructions".
- Share a notebook: a button in the notebook list's row creates, copies or revokes a read-only link; the public page `/shared/notebook/<token>` shows the title, the sources by name and kind (no files) and every output as on its own share page.
- Rename in place: a double-click (or F2) on a notebook in the notebook list, an output's row or an output's tab edits its title, as on the chat tabs (Enter or leaving saves, Escape cancels).
- Library: a ready output's row has "share", opening the viewer's share card under the row (create the read-only link, copy or revoke it); the card is one component for the viewer and the library.

### Changed

- Library and trash rows stay one line: no thumbnail in the row (an image's preview shows on hovering or focusing its name, loaded only then), long names end in an ellipsis with the full name as tooltip, and the demo badge follows the name without overlapping it.
- "Redeem a voucher" moved out of the rows: in a notebook it sits in the hint next to Create ("No credit: sources wait, outputs cannot be created.", Create disabled), in the library in one notice above the table ("N sources wait for credit"); the amber "waiting for credit" badge stays in the rows.
- Wording: the library's view selector reads All | Sources | Outputs, and the library, its trash and the notebook-delete dialog say "output(s)" instead of "(generated) documents", the notebook's own term. German says "Ausgaben" for outputs everywhere (the notebook's heading, the library pill, dialogs, trash, tooltips, the admin charts), since "Dokumente" collided with sources.

### Fixed

- Code scanning findings: the CSP build script finds inline scripts with a closing tag in any case or with whitespace or other junk before its `>`, as browsers accept it (and skips any `src`), and the mind map test cleans labels with the app's own DOMPurify sanitizer (in jsdom) instead of a regex stand-in.

## [0.16.0] - 2026-10-14

### Changed

- Library redesigned as one table: the Sources and Outputs tabs are gone (Library | Trash stay); a view selector (All, Sources, Documents) and filters by kind, notebook and name; documents sit next to uploads with their kind, status and "made in …", and open as before (in their notebook, or read-only once it is gone). Ticked rows across both can start a notebook, be added to an existing one ("Add to notebook…" shows per notebook how many are in it already, adds only the missing ones in one call and says "2 added, 1 was already in test1"), or be deleted.
- Admin > System: the diagram's card is called "Architecture" again (the whole page is monitoring); in the light theme the external boxes and the dashed lines are drawn thicker and with longer dashes, so they stay visible on white. The dark theme is unchanged.
- Sources without credit: adding a source is no longer refused for lack of credit (ingest's `waiting_for_credit`); the notebook's Sources list and the library show "waiting for credit" with "redeem a voucher", which opens the voucher dialog, and keep polling until processing starts. Creating documents still needs credit.

## [0.15.0] - 2026-10-14

### Added

- Decision, a seventh output kind: a question weighed against the sources. The tile's options take the question (required, up to rag's 500 characters) and the answer type (yes/no by default, a choice of 2–8 options, or a scale of 3–7 levels preset "very unlikely … very likely"). The document shows the decision model's answer as a gauge, a bar per option or a segmented scale, the verdict, whether model and evidence agree (a disagreement in amber, never hidden), the evidence for and against with markers and badges, and what the sources do not say; "How this was made" lists both calls.

## [0.14.0] - 2026-10-14

### Added

- Provenance on tables, quizzes and mind maps: a table row's markers in a last column that follows sorting, a quiz question's after the question, a mind map node's in its label, each with the unsupported or not checkable badge, opening the same passage panel.
- Chat: a cited answer is checked like a document; a paragraph the check did not back gets the "unsupported" badge ("not checkable" when written in another language than its sources) and the answer says "N of M claims supported" under it (`Message.units`, `Message.check`).
- Admin > System, "Architecture and monitoring": the diagram's boxes are coloured by the live state: green all ready; amber while rolling out, partly ready or restarted; red only for failure (a crash-looping, erroring or OOM-killed pod, restarts climbing between refreshes, nothing ready outside a rollout, healthz not answering); grey unknown; the reason as tooltip. Restarts appear under the replicas, the lines into a red box are dashed red, a legend explains the colours, and the data reloads every 15 s while the tab is visible. The external services take the state the services' healthz report (`dependencies`) and stay grey ("not probed") until they do; pod reasons and the Progressing condition are used when `/admin/system` reports them.
- Provenance on generated documents (report, infographic, audio): each claim's `[n]` markers open the chat's provenance panel for that passage, a claim the check did not back is badged "unsupported" (or "not checkable" when written in another language than its sources), the viewer head says "N of M claims supported", and under the document a folded list of the cited passages and a folded "How this was made" (model, prompt version, options, retrieval query and candidates, usage, timing, check) with a JSON download. Also on the share page, read-only.

### Changed

- Theme: the header toggle switches light and dark for this browser session only and no longer saves to the account (so the demo account gets no refusal); the lasting choice is made in Settings (light, dark or like the system), where a note says when the session differs from it, with "Use saved". With nothing chosen the app is light (before: following the system).
- Login: the new tagline, "Material in. Understanding out." in bold and what goes in and comes out as the line under it.

### Fixed

- Stacked layout (below 900 px): the Sources and Outputs lists showed about a row and a half, cut off mid-line (`flex: 1; min-height: 0` in a column without a height of its own). Stacked, both take their content's height, and their lists scroll beyond half the screen.

## [0.13.0] - 2026-10-14

### Added

- Audio styles: the Audio tile's options have a Style select (Overview, Story, Conversation; `audio_style`), and for a conversation a Second voice select with its own sample button (`audio_voice_2`, starting with the next voice of the first one's language and never the same). The player shows the transcript under it (`content.transcript`), a conversation with each speaker named by its voice; the line under the title names the style and both voices.
- Generated documents belong to the user and are in the library: an Outputs view between Sources and Trash lists them with kind, the notebook they were made in ("deleted notebook "…"" once it is gone) and date; open goes to that notebook with the document selected, or shows it read-only when the notebook is deleted; tick several or one to move them to the trash, where they are restored or deleted for good. Deleting a notebook with generated documents asks whether they go too or stay in the library. In the wizard's library step a document is listed as "Generated", so it can be added to another notebook as a source, where the Sources list shows it. Deleting a document in the viewer moves it to the trash.

## [0.12.0] - 2026-10-14

### Added

- Admin > Users: delete a user (admins only, no button for viewers). A dialog in the voucher dialog's style names the address and what goes with the account (notebooks, sources, generated documents, credit history), and its button stays disabled until the address is typed out; `DELETE /api/account/admin/users/{id}`, the row disappears on 204. A 409 (one's own account, the demo user) shows the service's sentence, a 502 names the failed step and its message (`{step, message}`); the dialog stays open either way. `ApiError` carries the failed response's JSON body for this.
- Checking an audio source: in the library and in a notebook's Sources list an audio row has a play button that mounts a player for that row on demand (nothing loads before, one player at a time), with download links "transcribed audio" (`preview_url`, the converted MP3 or the upload as it came) and, when the upload was converted, "original" (`original_url`, new on `Source` and `LibraryEntry`).

### Changed

- Audio sources: the wizard's Audio tile accepts M4A, AAC, OGG, Opus, FLAC, WEBM and MP4 besides MP3 and WAV (`.mp3,.wav,.m4a,.aac,.ogg,.oga,.opus,.flac,.webm,.mp4,audio/*,video/mp4,video/webm`), converted by ingest before transcription; the hint names the 60 MB upload cap and the conversion.

## [0.11.1] - 2026-10-14

### Fixed

- Stacked layout (below 900 px, also a narrowed desktop window): opening a notebook scrolled the page to its bottom, away from the notebook list. The chat brought its newest message into view with `scrollIntoView`, which scrolls the page too, and its question field took the focus. Now only the messages pane scrolls, and the field takes the focus on its own only where the chat is on screen (wider than 900 px); every focus call uses `preventScroll`.
- Stacked layout (below 900 px, a phone): the chat under the viewer had no messages area, only its tabs and the question field; the chat wrapper's `flex: 1 1 0` gave it zero height in a column without a height of its own. Stacked, the wrapper takes its content's height, the messages get at least 40vh (at most 60vh as before), and an open document's body at least 40vh (at most 50vh).

## [0.11.0] - 2026-10-14

### Added

- Audio sources: the wizard has an Audio tile (MP3 or WAV, `.mp3,.wav,audio/mpeg,audio/wav,audio/x-wav`, the 25 MB cap named in the hint), the kind `audio` is in the library's kind column and filter and in the wizard's library picker, and the open link plays the file in a new tab through its `preview_url` like a PDF (no thumbnail: those stay images-only). Every source in a notebook's Sources list now shows its kind as a badge. A citation into an audio source has no page, so "open in source" opens the file without an anchor. The admin overview's sources-per-day chart has an audio series; a day without a kind may now omit it.

## [0.10.3] - 2026-10-14

### Fixed

- Library and wizard: a thumbnail only for images. Since `preview_url` also carries a PDF's or text's presigned original and a web page's own address, every such entry was loaded as an `<img>`: the viewer's browser fetched each added web page from its host (an `http:` one tripped the CSP's `img-src`), and PDFs and text showed as broken thumbnails. `ImageName` now takes the entry's kind and renders the picture for `image` only; the open link is unchanged.

## [0.10.2] - 2026-10-14

### Changed

- Library, "New notebook from n sources": the title is a field in the selection bar next to the button (Enter or the button creates, Escape clears) instead of a browser prompt, and its preset is never a raw address: the first file's name without its extension when a file is selected, else the first web page's title, derived from its address as host and last path segment with `_` and `-` as spaces ("en.wikipedia.org · Dead reckoning") while ingest stores no page title.

### Fixed

- Narrow screens (a phone at about 412 px): the page no longer scrolls sideways. The stacked notebook columns and the workspace grid take at most the screen's width (`minmax(0, 1fr)`, before `1fr`, which a wide child could stretch); below 640 px the header wraps onto two lines, the navigation under brand and account, the e-mail address left out, so "Sign out" stays on screen; the architecture diagram on Admin > System scales to its card instead of keeping a 560 px minimum, and every admin table scrolls sideways inside its card; the Library's status column shows a failure's reason on one line with the full text as tooltip, instead of wrapping it over several lines.

## [0.10.1] - 2026-10-14

### Changed

- "Open in source" on a citation into an upload opens the source in a new tab through its `preview_url` (as the library's open link does), a PDF with `#page=<n>` so the browser's viewer lands on the cited page; it still highlights the source in the list, and a source without a preview is only highlighted, as before.

### Fixed

- Notebook sources list: each row showed only its checkbox, centered, and nothing else; the global `width: 100%` for inputs applied to the new source checkbox, which then took the whole row. Checkboxes and radios now keep their own width.
- Sign-in code: the form under the sign-in ("Have a sign-in code from the mail?") exchanges the code from the mail like the link (`GET /api/account/auth/callback?token=…`) and stores the returned JWT; before, it stored the pasted value as the Bearer token, so the mail's code led to a 401 on every request and nothing visible. The code's format (43 characters of letters, digits, `-` and `_`) is checked while typing with a count, Continue waits for it, an eye toggle shows the code, an unknown, used or expired code and a network or server failure are shown under the form. The field no longer takes a raw Bearer token (`demo` included); docs/development.md says how to use one in the browser.

## [0.10.0] - 2026-10-14

### Added

- Library multi-select: a checkbox per row with "all / none" for the rows shown, and a bar for the selection with "New notebook from n sources" (title prompt preset with the first name; created, filled entry by entry, opened) and "Delete n" (one confirmation naming every notebook affected, one delete per entry with progress, the rest kept ticked after a failure).
- Library: an entry can be opened in a new tab, from an "open" action in its row or by its name: a web page at its address, a PDF, text or image through its presigned `preview_url` (only `http(s)` addresses are linked; without a preview "open" is disabled with a note).
- Read-only admin access: the admin panel shows for the roles `viewer` and `admin` (`User.role`, falling back to `is_admin`); for a viewer a "read-only" badge sits in the heading and every write control is disabled with a tooltip. The Users page has a role column, a select for admins (`PATCH /api/account/admin/users/{id}`, refusals shown as the service's sentence); the Access page lists the viewer domains, added and removed like the sign-in lists.
- Source selection: a checkbox per source (all ticked by default, "all / none" in the header), remembered per notebook in this browser; the chat shows "3 of 5 sources" above the question and sends `source_ids`, Create sends them with the new document, and the outputs list and the viewer show "from 3 sources" with the names as tooltip (`Output.options.sources`). With none ticked, asking and Create are blocked with a hint.
- Content-Security-Policy: the full policy is enforced (`default-src 'self'`, the inline theme script by hash, no inline scripts otherwise, `object-src 'none'`, `base-uri 'none'`), after a clean headless-browser run of the report mode against the live API; the image build arg `CSP` picks `enforce` (default), `report` (Report-Only) or `off` (`frame-ancestors` only, as before); `scripts/csp.mjs` writes the nginx line with the sha256 of the inline theme script taken from the built `index.html`, so the hash cannot drift, and adds `API_BASE_URL`'s origin to `connect-src`.

### Changed

- Image: nginx-unprivileged 1.27 → 1.29 (1.29.8), and both base images (`node:24-alpine`, `nginx-unprivileged:1.29-alpine`) pinned by digest, with the refresh steps in the Dockerfile; `server_tokens off`, so neither the `Server` header nor an error page names the nginx version.
- Dependencies pinned to the exact versions the lockfile already installed (no version changes); the `@types/dompurify` stub removed, since DOMPurify ships its own types.
- Wizard: opened from an existing notebook it ends after the sources (two steps, with a note and "Done" when some were in the notebook already); the output step is for a new notebook only and has a "Skip" button instead of "Just chat".

### Fixed

- Lifting a ban sends its key as a query parameter (`DELETE /api/account/admin/bans?ip=<key>`), so an IPv6 /64 key such as `2001:db8:1:2::/64` works; through the path its slash (`%2F`) would have been decoded into a separate segment.

### Security

- Mind map: the node labels (the model's text) were rendered by markmap as raw HTML, so markup in a label (an `<img onerror>`, say) could run in the app and on the shared page; every node is now passed through DOMPurify, and a line break in a label no longer starts a node of its own.

## [0.9.1] - 2026-10-13

### Added

- A small ASCII figure walks beside "Generating…" while a document is processing: monospace frames every 250 ms on a fixed-width track in the muted colour, aria-hidden, still when the system asks for reduced motion.
- Admin System: an architecture diagram of the running system (plain SVG): browser, ingress, web and the three API services, the two workers, and PostgreSQL with pgvector, object storage and the inference API with the flows between them; each deployment shows its replicas ready of total and its build, an unhealthy one in the attention colour. The tables stay below it.

### Changed

- Outputs list: rows in a grid with the kind and the status in fixed slots and, under the title, when the document was made (relative within a day, absolute after, the exact time as tooltip) with its language and, for audio, its voice; a sort control (newest first by default, oldest, kind, language, status) and kind chips from six documents on.
- Theme toggle in the header: light and dark only, starting from the theme on screen, its icon showing what a click gives; "system" is chosen in Settings.

### Fixed

- Provenance on a citation into a generated document: "open document" (was "open in source", which did nothing visible because the tab was already open) opens the document's tab and shows the passage: the best-matching text block in a report, quiz, table or infographic scrolls into view and flashes; a mind map fits and flashes the matching node. Uploads keep "open in source".

## [0.9.0] - 2026-10-13

### Added

- Image thumbnails: image entries in the library, the trash and the wizard's library picker show a 2rem thumbnail (lazy, from `preview_url`) and a preview up to 320 px on hover, focus or tap, placed inside the window and closed on leave, Esc or a tap elsewhere.
- Chat tabs can be renamed in place: double-click or F2 turns the title into a field with the text selected, Enter or leaving it saves (`PATCH /api/rag/conversations/{id}`), Esc cancels, an empty or unchanged name keeps the old one, the field is as wide as its text (up to 80 characters).
- Mind map controls: a small bar on the map (zoom in, zoom out, fit) and the keys +, − and 0 on the focused map, through markmap's `rescale()` and `fit()`; in the viewer, the full view and on the shared page.

### Changed

- Output format tiles: always three columns by two rows at a fixed width; the middle column's default and minimum width (27rem, 378 px) come from that grid, so the divider cannot squeeze it into another layout. On a phone the three tiles share the width. A test keeps the stylesheet and the divider's minimum equal.
- Admin System: the "no read role" notice points to "The chart" in `infra/docs/operations.md`, where `kubernetesRead` and the check of the grant are described.

### Fixed

- Form controls: selects get the same border, padding and background as text fields, and every single-line control (select, text, number, search, e-mail) one height, so controls side by side line up. In the library the two filters sit in one grid row with their labels on one line (the Kind label sat lower than the Name label).
- Library: the size of an entry added before sizes were recorded reads "unknown" (muted, with a tooltip) instead of a dash.

## [0.8.1] - 2026-10-13

### Fixed

- Wizard, adding from the library: a proper list instead of rows that laid out like a table: a fixed checkbox column, the name on one line with an ellipsis (full name or URL as the tooltip, URLs shortened to host and path), the kind and demo badges right-aligned in a fixed slot, an even row height, a hover highlight, the whole row toggles; "n selected" next to the add button.
- Theme: the header toggle and the Settings page share one theme store; saving a theme in Settings now changes what the toggle shows and offers next (it kept its own state before), and saving "like the system" switches back to the system's setting at once (it stayed on the previous theme).
- Admin System: instead of "nothing yet" under Pods and Deployments, the page says why: not running in a cluster, or (in a cluster with both lists empty) no read role for pods and deployments.

## [0.8.0] - 2026-10-13

### Added

- Theme switch: "system" (default), light or dark, from a toggle in the header and the Settings page; applied before the first paint from this browser's last choice and synced with the account's `theme` preference after sign-in. All colours, charts and mind map included, come from the theme tokens; a test checks the WCAG contrast of the token pairs in both themes.

### Changed

- Colours adjusted for contrast in the light theme: accent `#2b66cc` (was `#2f6fdd`), warning `#a06000`, chart orange and yellow darker; button text uses a new `--on-accent` token, which is dark in the dark theme (white on the light blue accent was below 4.5:1); the dialog backdrop is a token.

## [0.7.2] - 2026-10-13

### Changed

- Admin Overview redesigned: the heading with one meta line (build and service health with status dots, linked to System) instead of the version link, one row of six equal KPI tiles instead of three groups of 18, an attention strip only for what needs an action (bans, blocks, a service down or without a version) as the only red on the page, failures without an admin page as muted details. The charts share one time range (7 days while the data is young, else 30, with a toggle) in a two-column grid of equal cards paired by topic; a chart without data is listed on one line instead of drawn empty.
- Wizard: after a failed upload (a storage outage now answers 503) the files that went in leave the list and the rest stays selected for a retry, with a line saying how many are left.
- Library trash: "settings" in the note links to the settings page, scrolled to and focused on the trash-days field.

## [0.7.0] - 2026-10-13

### Added

- Demo sources: a "demo" badge on the example sources a new account starts with (library, trash, the wizard's library picker, the source list); the library page polls while entries are processing; an empty chat in a notebook with demo sources offers a first question to ask.
- Admin System page (`/admin/system`, from `GET /api/account/admin/system`): per service version, commit and health, the cluster's pods and deployments, or a note for a local run; the overview shows the build under its heading. The build is the tooltip of the brand in the header for everyone (from the public `healthz`).
- Voice sample: a "sample" button next to the voice in the audio options and in the settings plays a short sentence pair in that voice, speed and language (`POST /api/rag/outputs/voice-sample`, fetched on click only).
- The interface in German and English: every visible string goes through `t()` with one map per language (`src/i18n/`, the German map typed against the English keys, so a missing key fails the typecheck); `ui_language` decides, the browser's language before login; dates, numbers and amounts are formatted in that language. Messages from the services stay in English.
- PDF capture mode: the wizard offers Auto, Text or Vision for PDF uploads with a line on each (cost included), preset from the `pdf_capture` preference and sent as `capture`; the settings page sets the default; the source list and the library show the mode on PDF entries.

### Changed

- Admin Credits: new voucher codes are compact chips with a copy button each and "copy all" for several ("copied" for a second; the text is selected when the clipboard API is not available), placed next to the create form when there is room.
- Wizard: "From library" is the first tile.

## [0.6.1] - 2026-10-13

### Added

- Library trash: a Trash view next to the sources lists deleted entries with when they are purged; restore puts one back in the library (in no notebook), "delete for good" removes it at once after a confirmation. The settings page sets the days an entry stays there (`trash_days`, empty for 14).
- Column dividers between the notebook list, the left column and the right column: drag or arrow keys, widths remembered per browser, double-click or Home for the default, minimum widths kept.

### Changed

- Library delete moves the entry to the trash instead of removing it; the confirmation says so.

### Fixed

- The document and chat tab bars scroll sideways when the tabs do not fit (columns no longer grow with them); the active tab scrolls into view, the mouse wheel scrolls the bar, arrows, Home and End move between tabs. In the chat bar "+" stays in place.

## [0.6.0] - 2026-10-13

### Added

- Output options under the format tiles, from rag's `GET /outputs/options`: language for every kind, voice (grouped female and male) and speed for audio; preset from the user's preferences, sent as `options` with only the keys the kind takes. The wizard uses the preferences too. The viewer and the shared page show what a document was made with.
- Settings page `/settings` (header link): interface language, language of generated documents, voice for audio, saved through `PUT /api/account/me/preferences`.
- Citation provenance panel: a click on `[n]` shows source and kind, page, chunk position ("chunk 12 of 43"), the similarity to the question as a number and a bar, and the full chunk text with the sentence closest to the cited statement marked; "open in source" as before. The citation list shows page and similarity inline. Older citations get position and full text from `GET /api/rag/chunks/{id}` where the chunk still exists.
- Admin overview charts of the last 30 days under the headline numbers: cost and credit granted per day, logins and visits, chat messages and documents, documents by kind, sources added per day by kind, cost by model, top users by usage. Each chart loads on its own; recharts 3.10.1 in its own chunk, loaded only on the overview, behind an error boundary; colours from the theme (`--chart-1` … `--chart-6`, light and dark).
- Chat height presets 1x, 2x, 3x at the right end of the chat tab bar: the chat gets 15, 30 or 45 % of the right column. They set the divider's ratio (stored the same way), the matching preset is highlighted, a drag moves off it.
- Admin Users: a "Granted" column (the user's ledger sum) next to used and balance; the overview's "Credit granted" tile links to the Users page and "Vouchers open" to Credits.

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

