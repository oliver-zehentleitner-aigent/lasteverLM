# Walkthrough script

The ten-minute recorded tour of lasteverLM: what it does, how it is
built, how it was built. Times are targets; the live part comes first
because it is what a viewer remembers. Everything shown is on the
deployed system, nothing is mocked.

## Before recording

- Two browser tabs: the app at `https://lasteverlm.zehentleitner.co`
  and the repository's Keep the Why dashboard
  (`https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/`,
  family scope on).
- A third tab with the GitHub repository on the pull-request list and
  the Actions page.
- A mailbox on an allowed domain open, for the magic link.
- Two sample sources ready: one PDF of a few pages and one web page URL.
  Pick sources whose content yields a non-trivial question with an
  answer that sits in one passage, so the citation lands visibly.
- A terminal with `kubectl get pods -n lasteverlm` and `kubectl get hpa
  -n lasteverlm` typed, not run.
- The notebook from the rehearsal deleted, so the wizard starts empty.
- Do not name the company the assignment came from, not in speech and
  not on screen; the repository does not name it either.

## 0:00 Opening (30 s)

"This is lasteverLM: provide documents, ask questions, get answers with
citations into the sources, and turn the sources into reports, quizzes,
tables, mind maps, infographics and audio. One repository, six services,
running on Kubernetes at Vultr. I built it in three days with a fleet of
seven coding-agent sessions and I will show that part at the end."

## 0:30 Login and credit (45 s)

- Enter an address on an allowed domain. "Login is a magic link,
  restricted to the domains the admin allows; no passwords anywhere."
- Open the mail, click the link, land in the app.
- Redeem the voucher. "Every account starts with a ten-euro voucher;
  every model call is priced and debited against it, so the sponsor
  knows what the demo costs."

## 1:15 The wizard (1 min)

- Click add. Step 1, what goes in: pick PDF. Step 2, drop the file.
  "A second kind in the same wizard: a web page." Add the URL.
  "The fetch happens in a worker behind a guard that refuses private
  addresses, so nobody uses the service to reach the cluster from
  inside."
- Step 3, what should come out: select report, quiz, mind map, audio.
  Done.
- "Three steps, one question each. The outputs are queued now; the
  workers pick them up when the sources are ready, even if I close the
  browser."

## 2:15 The notebook (2 min 15 s)

- Left column: the sources turn ready. "Parsing, chunking, embeddings,
  one summary per source."
- Right column: the report tab opens. Scroll once. "Generated from the
  summaries and the passages that match the report's own focus query."
- Quiz tab: answer one question, reveal. Mind map tab: expand a node.
- Chat: ask the prepared question. The answer arrives with `[1]`
  markers; click one, the cited passage opens in the source. "The
  citations are built here, not by the model: numbered passages go in,
  markers come out, and a marker that points at nothing is dropped."
- "Ask about this" on the report: one question about the document, the
  answer cites the report itself.
- Audio tab: play two seconds. "Text-to-speech on the same inference
  platform; the file lives in object storage behind a short-lived URL."
- Print: the print view of the report. Share: copy the link, open it in
  a private window. "Read-only, no login, revocable."

## 4:30 Admin (45 s)

- Open the admin panel. Mail: "SMTP is configured here, not in a
  config file; the password is stored encrypted." Vouchers: create one.
- Visitors: "Daily unique visitors, counted from a salted hash that
  rotates every day; no raw addresses in this table."
- Access: the access log, the blocked and banned addresses. "One hundred
  and twenty requests a minute, then fifteen minutes blocked; three
  blocks in a day and the address is banned until an admin lifts it."
  Lift nothing.

## 5:15 Architecture (2 min)

- Switch to the repository README, the directory table. "One
  repository, used as an umbrella: the root holds the contract, each
  directory is a service with its own tests, docs, changelog and its own
  reasoning. Core is the shared library: models, auth, rate limiting,
  usage accounting, the provider interfaces."
- `docs/architecture.md`, the overview diagram. "Everything on one
  Vultr account: Kubernetes, Managed PostgreSQL with pgvector, Object
  Storage, Serverless Inference. No other vendor."
- Terminal: run `kubectl get pods`, then `get hpa`. "Every process
  scales horizontally; the API pods sit behind autoscalers, the workers
  are Deployments that claim jobs from PostgreSQL with `SKIP LOCKED`.
  PostgreSQL is the only state and also the queue."
- Actions tab: the last tag's deploy run. "Delivery is containers only:
  images in GitHub's registry, one Helm chart, a release is a tag. Rate
  limiting runs in a core middleware every service mounts; the ingress
  only terminates TLS."

## 7:15 How it was built (1 min 30 s)

- The Keep the Why dashboard tab, family scope: the seven projects, the
  timeline, the authors view. "Seven agent sessions, one per directory
  plus one head. Every decision each agent took is recorded with the
  alternatives it rejected, committed the moment it was taken, so the
  timeline is the real order of events."
- Click one entry: the embedding-dimension decision or the citation
  renumbering. "This is what a reviewer reads when the code alone does
  not explain itself."
- Pull-request list, merged. "Fifty-odd pull requests in two days.
  The head agent reviewed and merged every one; the maintainer read
  none of them and tested the result."
- One line of numbers from the final report: sessions, active hours
  summed, tokens, which model each agent ran on.

## 8:45 Close (30 s)

"What it is not yet: no video output, English UI only, one voice.
What it is: a cited-answers system a team could operate, with the
reasoning behind every choice in the repository next to the code.
The repository, the live system and the dashboard are linked in the
description."

## If something fails on camera

- A source stays in processing: show the worker log
  (`kubectl logs deploy/lasteverlm-ingest-worker`), say what it waits
  for, move on to the chat with the other source.
- The magic link is slow: use the voucher screen to explain credit while
  waiting; never show the demo token.
- An output fails: open its tab, the error is readable; "the failure is
  recorded, the retry is three attempts, then it stays failed and the
  user sees why."
