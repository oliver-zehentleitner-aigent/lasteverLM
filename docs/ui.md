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

1. **What goes in?** Tiles: PDF, Text, Web page, Image, all active. A
   kind that is not available yet is shown greyed with "Soon.", so the
   extension points stay visible.
2. **How does it get in?** Only the ways that fit the type: drop or
   pick files (several at once), enter a URL, paste text.
3. **What should come out of it?** Tiles of the output kinds, multiple
   selection, "just chat" is allowed. Done.

Step 2 calls `POST /api/ingest/notebooks/{id}/sources` per file, or once
with `{"url"}` for a web page. Step 3
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
│ Create            │  ask about this · print · share      │
│ [Report] [Quiz]   ├──────────────────────────────────────┤
│ [Table] [Mindmap] │ [Chat 1 ×] [Chat 2 ×] [+]            │
│ [Infographic]     │  question … answer with [1] [2]      │
│ [Audio]           │  > ask your sources                  │
├───────────────────┤                                      │
│ Outputs           │                                      │
│  · Report  ready  │                                      │
│  · Quiz    ready  │                                      │
└───────────────────┴──────────────────────────────────────┘
```

- **Sources** (left, top): the uploads (PDF, text, web page, image)
  with status and delete; the add button opens the wizard at step 1.
  Generated documents are not listed here, although the backend keeps
  each one as a source of kind `generated` so the chat can cite it.
- **Create** (left, middle): the output kinds as tiles; a click creates
  an output of that kind for the whole notebook.
- **Outputs** (left, bottom): the generated documents with kind, title
  and status; a click opens the document's tab, × deletes it.
- **Output viewer** (right, top): one tab per output, processing tabs
  show a spinner and poll. Each kind has its own renderer. Three actions
  per document: ask about this, print, share.
- **Chat** (right, bottom): one tab per conversation of the notebook,
  "+" opens a new one, "×" closes one after a confirmation and deletes
  its messages; closing the last tab opens a fresh one, and a notebook
  without conversations gets one when the chat opens, so a question
  always goes to a conversation. In the active tab: question, answer,
  citations as `[n]` that open the cited passage; a citation into a
  generated document opens that tab.

## Viewer, print, share

- **Viewer**: a clean document view with title, date, the sources it was
  made from. Report as Markdown, quiz interactive with reveal, table
  sortable with CSV export, mind map with markmap, infographic as a
  card grid, audio as a player.
- **Print**: a print stylesheet on the viewer and a button; the browser
  produces the PDF. Report and table are the printable kinds.
- **Share**: creates a share token and shows the link `/s/<token>`; the
  page renders the document read-only without login and records a
  visit. Revoke from the same place.
- **Ask about this**: switches the chat scope to the open document
  (`scope.output_id` on `/ask`); a chip above the input shows the scope
  and clears it.

## Login, credit, admin

- Login page: one field, the e-mail address; then "check your mail";
  the link lands on `/auth/callback` and the app is open. An address
  without access is told "This address has no access to lasteverLM."
  and no mail goes out.
- Header: balance in EUR, a voucher button that opens a one-field
  dialog. A 402 anywhere opens the same dialog.
- Admin (only for admins, one page with sections): an overview at the
  top with numbers from the three services' stats endpoints, each group
  loading on its own; users with last login and balance, login log,
  sign-in attempts (allowed or refused, with IP),
  visitor log aggregated per day and path, SMTP settings read-only
  (they come from the deployment) with a test button, allowed sign-in
  (domains and single addresses, one entry at a time), voucher creation
  (5 EUR by default) that shows the codes once, with the list of issued
  vouchers below it (open ones can be deleted).
  Above the blocks and bans, the rate-limit rule as a sentence with
  its four editable numbers and a reset to the deployment defaults.

## Language

The interface is English; sources, questions, answers and generated
documents are in whatever language the user and the sources use.
