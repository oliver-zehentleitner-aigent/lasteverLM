# The project

lasteverLM turns material into understanding you can check. PDFs, text,
web pages, images and audio go in; questions, reports, quizzes, tables,
mind maps, infographics, spoken overviews and decisions come out, and
every sentence can be traced to the passage it came from. This page is
the whole picture in one place: what it does, how it is built, the
principles behind it, how it was made, and what it deliberately leaves
out. Details live in the linked pages; the reasoning behind every
decision is in the [Keep the Why dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/).

## What it does

### Sources

- **Five kinds:** PDF, text, web page, image, audio.
- **PDF capture:** the text layer, the vision model for scanned pages,
  or `auto` (vision only for pages without a legible text layer; a
  layer of glyph codes counts as not legible).
- **Images** are transcribed and described by the vision model.
- **Audio** is transcribed by a speech-to-text model. MP3 and WAV go in
  as they are; M4A, AAC, OGG, Opus, FLAC, WebM, the audio track of MP4,
  and WAV over the platform's 25 MB cap are converted to MP3 first by a
  minimal ffmpeg. The converted file and the original stay available to
  play and download, so the transcribed audio can be checked.
- **Library per user:** every source is stored once (deduplicated by
  content or normalised URL), linked into any number of notebooks,
  deleted into a trash for a user-defined number of days. Nothing is
  shared between users.
- **Adding is free, processing costs:** without credit a source is
  stored and waits; it is processed as soon as credit is there.
- **Starter notebook:** every new user gets their own copy of a notebook
  about lasteverLM itself: the complete technical handbook as a PDF, an
  FAQ, the public price list as a web page, a screenshot of the app, and
  finished outputs of every kind, ready to ask and to check.

### Outputs

- **Kinds:** report, quiz, flashcards, data table, chart, mind map,
  infographic, audio, decision.
- **Options:** output language, for audio the style (overview, story,
  conversation with two voices), voice and speed; for reports style
  and length; for quizzes number of questions, difficulty and audience;
  for every kind free notes that steer focus and tone but never the
  citation rules.
- **Decision:** a question weighed against the sources. The platform's
  decision model gives the number (a probability, a choice with its
  distribution, or a level on a scale); the language model writes the
  evidence for and against independently from the same passages; both
  go through the support check, and their agreement is shown
  (consistent, conflicting, unclear, or "the sources do not decide
  this").
- **Chart:** "Find charts" proposes number series from the sources as
  small previews; the user picks which are drawn. Every value is
  checked exactly against its passage (in any notation: 1.906, 1906,
  1,9 Mio., percent); a computed value is marked as computed, never as
  supported.
- **Judge (optional):** a model of another family than the author
  checks each claim's meaning against its passages (supported,
  contradicted, not in the source), in three levels whose models were
  chosen by a published evaluation ([judge evaluation](https://github.com/oliver-zehentleitner/lasteverLM/blob/main/rag/docs/judge-eval.md)).
  At generation, failing claims are revised and judged again, at most
  three rounds; a claim that still fails is removed and listed as
  removed. On an existing output or chat answer the judge annotates
  only.
- **Outputs belong to the user**, live in the library, survive the
  deletion of the notebook they were made in, and can be added to
  other notebooks as sources.
- **Sharing:** a single output or a whole notebook as a read-only link,
  readable without login, with all its evidence.

### Chat

Conversations per notebook as tabs, scoped to the sources the user
selects, with numbered citations into verbatim passages, the same
support check as the outputs, copy, thumbs up and down, and three
suggested follow-up questions. The chat can also act on its notebook:
asked to add a web page, take entries from the library, create an
output and explain it, it answers with a plan (steps, estimated
prices, invalid steps struck through with the reason) and runs it only
after the user confirms; tool arguments come only from the user's
message and library, never from source text.

### Viewer

Sources and outputs the user opens appear as tabs. A source tab shows
the original (PDF inline at the cited page, image, audio) and the text
as the system read it, chunk by chunk; a citation highlights its
chunk.

### Administration

Users and roles (user, viewer with a read-only admin panel, admin),
who may sign in and who starts as viewer (domains and single addresses
for both), a finance area (below), rate limits, blocks and bans with their rules editable at runtime,
sign-in attempts, visits, mail configuration, and a System page with
the installed version, every pod and a live architecture diagram that
colours each component by its state.

### Finance

Every booking keeps the measured cost in US cents (the platform's
currency), the EUR/USD rate applied, the cost in euro and the price
charged to the user, all fixed at booking time, so a later change of
rules never rewrites history. The charge is the cost plus a margin,
set globally and per action (a chat answer, each output kind, each
source kind, the judge, a decision), optionally with a fixed fee per
action. Users see the charged price before every paid action, a public price
list, and their own Credits page (balance, voucher redemption, spending
by day, by action and entry by entry). The
admin sees costs, prices with a live preview, revenue against paid and
free vouchers, and profit after the platform's infrastructure costs,
which are read daily from Vultr's billing API. Voucher codes are
encrypted at rest with a separate key, so an admin can show them again
and send them by mail. Adding a source is free; processing it waits
for credit.

## Principles

**Everything derived from a user's input can be checked by that
user.** Every unit of every output (a report paragraph, a table row, a
mind-map node, a sentence of an audio transcript, a piece of evidence
in a decision) carries the passages it rests on and a support status
from a deterministic check: `supported`, `unsupported`, or
`unverified` when the output was written in another language than the
material. Units that fail are marked, never dropped. Every output
carries its generation log: retrieval candidates and which entered the
prompt, the model, the prompt version, usage, timing and the check's
counts. The shared page shows all of it.

**Fail loud.** A wrong or missing value stops the process instead of
falling back silently: a service without a price for its model does
not start, a loader that extracts no text fails the source, a provider
answer without usage is an error.

**Measure, do not assume.** Five billing facts were corrected by a
measurement instead of the documentation: text-to-speech is charged
per second of speech, not per character; the decision model reports
input tokens, although the catalog says completion; speech-to-text is
charged per second; the main model's input price differs from its
output price; the platform prices in US dollars while credits are in
euro. Each is recorded with the measurement. The judge's models were
chosen by an evaluation rather than by reputation: on 24 hand-written
claims the word check alone caught none of the negated, swapped or
off-by-one claims; no judge level missed a negation, and two of the
three scored every claim correctly (details and limits in the
evaluation).

**One platform.** Kubernetes, PostgreSQL with pgvector, object storage
and every model run on Vultr. Web search was considered and left out
because it would add a second vendor.

## Architecture in short

Six parts in one repository, each with its own context: `core` (the
shared library), `account` (sign-in, credit, administration), `ingest`
(sources, library, extraction, chunks, embeddings), `rag` (retrieval,
chat, outputs, sharing), `web` (React), `infra` (OpenTofu for the
platform, Helm for the application, the pipeline). PostgreSQL is the
database, the vector store and the job queue. A Git tag builds and
deploys; a smoke test over the public domain closes every deploy.
Details: [Architecture and API contract](architecture.md),
[The RAG pipeline](rag-pipeline.md), [User interface](ui.md).

## Security

TLS with HSTS and an enforced Content-Security-Policy with hashed
inline scripts; magic-link sign-in with one-day sessions and an
allowlist; roles checked in every service; rate limits, blocks and
bans per address (IPv6 by /64) behind the PROXY protocol, so a client
cannot choose its address; SSRF protection on URL sources; HTML from
models sanitised before rendering; pods without root, with read-only
file systems and NetworkPolicies; secrets in Kubernetes Secrets only; voucher codes encrypted at rest
with a separate key; e-mail addresses and answer texts masked for
read-only viewers at the server; no paid model call without a configured exchange
rate, so nothing is paid upstream and left unbooked; actions pinned by
commit with Dependabot, images with provenance and SBOM; code scanning
at zero open alerts.

## How it was built

One maintainer and seven coding-agent sessions over three days: one
agent coordinating, reviewing and merging, one per part of the system.
Every change went through a pull request that was merged only when
every check had passed; every decision was written down with the
alternatives it rejected, and is browsable in the
[Keep the Why dashboard](https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/).
More than three hundred pull requests and over twenty-five tags; a fix is
typically live four minutes after its tag. The
[walkthrough](walkthrough.md) is the script for a guided tour.

## Deliberately not built

- **Web search as a way to add sources:** a second vendor and search
  quality outside the system's control; the plug-in point is described
  in the architecture.
- **Approximate nearest-neighbour index, reranker, model tokenizer for
  chunking:** named in the RAG pipeline with the size at which they
  would pay off.
- **Node autoscaling** waits for the database's private network
  attachment.
