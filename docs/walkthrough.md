# Walkthrough script

The ten-minute recorded tour of lasteverLM. The product comes first:
a source goes in, a good question gets a correct answer, the evidence
opens, one compact output is made. Architecture and the way it was
built follow. Times are targets. Everything shown is the deployed
system, nothing is mocked.

## Before recording

- Browser tabs: the app at `https://lasteverlm.zehentleitner.co`, the
  Keep the Why dashboard
  (`https://oliver-zehentleitner.github.io/lasteverLM/keep-the-why-dashboard/`,
  family scope on), and the GitHub repository on the pull-request list.
- A mailbox on an allowed domain, for the magic link, and a fresh
  voucher code.
- One short source with a non-trivial fact in one passage, and one
  detail that is deliberately absent, for example a text with a date,
  a budget, an owner, and an approval that is still pending. A web page
  URL as a second source.
- A terminal with `kubectl get pods -n lasteverlm` and `kubectl get hpa
  -n lasteverlm` typed, not run.
- Do not name the company the assignment came from, not in speech and
  not on screen.

## 0:00 Opening (30 s)

"This is lasteverLM: put sources in, ask questions, get answers that
point to the exact passage they rest on, and turn the sources into
reports, quizzes, flashcards, tables, charts, mind maps, infographics,
decisions and audio. Everything it says can be checked by the person
who reads it."

## 0:30 Sign in and credit (30 s)

- Enter the address, open the mail, click the link. "A magic link,
  for an allowlist of domains and addresses, no passwords."
- The introduction shows the three areas once. The starter notebook
  is already there: lasteverLM explaining itself, with finished
  outputs.
- Redeem the voucher. "Every model call is priced and booked against
  this credit; every paid action shows its price first."

## 1:00 A source and a question (2 min)

- New notebook, add the short text and the web page. "Adding is free.
  A source is read when a question or an output needs it."
- Ask the prepared question. The answer arrives with numbered markers;
  click one, the passage opens in the source, highlighted. "The model
  never writes a citation: numbered passages go in, markers come out,
  and a marker that points at nothing is removed."
- Ask about the absent detail. "It says the sources do not contain
  that, instead of inventing it."
- The badges under the answer: "The word check compares words with the
  cited passage. It is fast and free, and it sees no meaning, no
  negation. That is what the judge is for."

## 3:00 One output, checked (1 min 30 s)

- Create a short report at verification level "Thorough". While it
  runs, the view shows its real step: retrieving, writing, judging
  round one.
- Open it: every paragraph carries its passages, the word check, and
  the judge's verdict. "The judge is a model of another family than the
  writer. A paragraph it does not find in the sources is revised once
  and judged again; what still fails is removed and listed as removed,
  never hidden."
- Point at a green "Judge: supported · citation added" badge and its
  marked citation. "This paragraph cited too little. Before calling it
  unsupported, the judge searched all selected sources, found the
  passage and added it. Only what is in none of the sources stays
  unsupported, and a contradiction is never searched away."
- "How this was made": model, prompt version, the passages that went
  in, tokens, time and cost.
- Share: open the link in a private window. "Read-only, no login, with
  all of its evidence."

## 4:30 Audio and the agent chat (1 min)

- Play the starter's audio for a few seconds; the spoken paragraph is
  highlighted. "Several voices and styles, a conversation and an FAQ
  with two speakers."
- In the chat: "Make flashcards from these sources." It answers with a
  plan, its price, and a question where a choice is open. Nothing runs
  until it is confirmed. "Tool arguments come only from what I typed
  and from my library, never from source text."

## 5:30 Cost and administration (45 s)

- `/prices`: what each action costs, measured from the last 30 days.
- Admin, finance: cost from the platform, the charge to the user, the
  margin, and the infrastructure bill read from Vultr. "The user never
  sees the margin; the admin sees all of it."
- Admin, system: version, every pod, and the live architecture diagram.

## 6:15 Architecture (1 min 30 s)

- README, the directory table. "One repository, six parts, each with
  its own tests, docs, changelog and reasoning: core, account, ingest,
  rag, web, infra."
- `docs/architecture.md`, the diagram. "One vendor: Kubernetes, Managed
  PostgreSQL with pgvector, object storage and every model on Vultr.
  PostgreSQL is the database, the vector store and the job queue."
- Terminal: `get pods`, `get hpa`. "API pods scale horizontally; workers
  claim jobs with `SKIP LOCKED`."
- Actions: the last tag's run. "A release is a tag. Images, Helm,
  migrations, rollout, and a smoke test over the public domain; a fix is
  typically live four minutes after its tag."

## 7:45 How it was built (1 min 30 s)

- The dashboard, family scope: the timeline and one decision with the
  alternatives it rejected, for example web search left out or the
  credit start rule. "Every decision is written down when it is taken,
  with what was rejected and why."
- The pull-request list. "Seven coding-agent sessions over three days,
  one per part and one coordinating, which reviewed and merged every
  pull request. A pull request was merged only when every check passed."
- Who did what, precisely: "The agents wrote and reviewed the code.
  I set the architecture and the product rules, decided every open
  question, tested every release live on the phone and the desktop,
  and gave every go for production data and permissions. Where we
  accepted a risk, it is written down: for example, a user can end
  slightly below zero credit, because an action that has started runs
  to its end."
- One line from the final report: sessions, active hours, pull
  requests, tags.

## 9:15 Close (45 s)

"What it is not: no video output, no web search as a way to add
sources, no approximate vector index yet. Each is named in the docs
with the point at which it would pay off. What it is: a system whose
answers can be checked, that a team could operate, with the reasoning
behind every choice next to the code."

## If something fails on camera

- A source stays in processing: the source shows its state and
  reason; move on to the chat with the other source.
- An output fails: its tab shows the final error with the model and
  the kind of failure, and whether anything was charged.
- The magic link is slow: explain credit on the voucher screen while
  waiting; never show a token.
