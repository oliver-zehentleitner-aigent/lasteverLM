# Worker

## Workers poll the queue and take over stale claims

**Id:** 4f6e16de-3395-4ae3-ae7b-95ba0d08aa13
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12, on top of the family decision to queue in PostgreSQL with `FOR UPDATE SKIP LOCKED`
**Revisit when:** upload volume makes a two-second pickup latency or the polling load on the database noticeable

The family decided that source processing leaves the API process and
that the queue is the `sources` table itself (`processing` rows claimed
with `FOR UPDATE SKIP LOCKED`, no broker). Two details are this service's
own: an idle worker polls every `WORKER_POLL_SECONDS` (default 2), and a
claim older than `CLAIM_TIMEOUT_SECONDS` (default 600) counts as free
again, so a source whose worker died mid-job is picked up by the next
one instead of staying `processing` forever.

**Reason:** the frontend already polls `GET /sources` for the status,
so a pickup latency of a couple of seconds is invisible to the user, and
one cheap indexed query every two seconds per worker is noise on the
database. The stale takeover is the only recovery path for a crashed
worker, because nothing else ever looks at a claimed row.

Not every failure is retried. A failure a retry cannot change — an
unreadable file, no extractable text — fails the source at once,
because three more attempts would only delay the answer the user needs.
(Credit exhausted was in this list until 2026-10-14; since then such a
source is not failed but waits in the queue, unclaimed and with no
attempt counted: 8b4d8fdd-3b1f-4f35-be45-452e15385df9.) A failure that may pass next time — object storage, the
embedding or summary request, anything unexpected — leaves the row
`processing` with the error, so the stale-claim timeout hands it to the
next worker; the third attempt that fails ends it as `failed`, the
family's rule (since 2026-10-13 the next attempt follows within
seconds instead of after the stale-claim timeout: b53c94f0-b1e7-47ca-bc17-59b8fd3b967b); since 2026-10-14 a row whose worker died or hung on every attempt is failed by the claim: 094ed85d-4934-4809-b9ad-b6871eb38c37). Retrying everything three times was the alternative;
rejected because a bad PDF would then sit at `processing` for half an
hour before the user learns it is unreadable.

**Rejected alternative:** `LISTEN`/`NOTIFY` for instant pickup. Rejected
for now because it needs a dedicated long-lived connection per worker
with its own reconnect handling, for a latency gain nobody would see; the
loop is one function and can switch to it if the revisit condition
triggers. A heartbeat column instead of the timeout was not seriously in
contention: a job is bounded by the upload cap, so a fixed timeout is
enough and one write per job cheaper than one per heartbeat. (Vision capture since made jobs longer than the timeout; since 2026-10-14 the job refreshes its claim with every model call instead: e3b21110-c7ed-4f74-afba-fb60ae41df3e.)

## The request handler stores the file; the worker starts from a source id

**Id:** 964f1308-92b8-4d6f-a93e-5639a92d476e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12
**Revisit when:** uploads grow beyond what a request should hold in memory

`POST /notebooks/{id}/sources` writes the source row and uploads the
file to the bucket before it answers; the pipeline
(`worker.process_source`) then takes only a source id, loads the bytes
back from the bucket and does everything else. The contract's wording
("processing runs after the upload response: store the file, parse,
...") is read as the user-visible sequence, not as a constraint that the
storing happens in the worker.

**Reason:** the worker runs in its own pods and claims jobs from the
database. A worker that needs the upload's bytes from the request's
memory cannot exist in that shape; one that needs only a source id can.
The cost is one upload on the request path, acceptable at the size cap
in force. (The first version ran the pipeline as an in-process background
task; the function was written for the pod shape from the start, so the
move was the claiming loop and nothing in the pipeline.)

**Rejected alternative:** hand the bytes to the worker and let it upload.
Saves the round trip through the bucket, rejected because it ties the
worker to the API process and makes a crashed upload leave a
`processing` row with no file behind it.

The credit check first ran in the handler (a 402 before anything was
stored) and again in the worker before each model call. Since 2026-10-14
adding a source needs no credit (8b4d8fdd-3b1f-4f35-be45-452e15385df9),
and credit is checked once, before a read starts
(1bbd3b8d-5e0b-48a1-b9be-2dccca4c4a32).

The order inside the handler is part of the decision: the object goes to
the bucket first and the claimable row is written after it. A
`processing` row is in the queue the moment it exists; with the row
first, a worker polling in that instant claimed it and found no object
(`NoSuchKey`, the v0.7.1 smoke failure, 2026-10-13). A failed upload now
leaves no row at all (503), instead of a row marked failed. (Since
2026-10-14 a new row is `added` and not claimable until the source is
used: d80fd88e-9269-4b75-bcb2-f215e4fcd1f7. The handler keeps the
object-first order, so a failed upload still leaves no row.)

## A failed summary fails the source, even though its chunks are written

**Id:** f11ae1b9-3c5a-4eb7-bc8d-52c1344805ef
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12
**Revisit when:** a retry endpoint for a single source exists, or the output generators learn to work without a summary

The summary is the last step of processing. When the model call for it
fails, the source ends as `failed` with the error, although its chunks
are in the database and the embedding has been paid for.

**Reason:** the output generators in the rag service take the summaries
of a notebook's sources as their input. A source that is `ready` without
a summary would make them work on incomplete input without anyone
noticing; a `failed` source is visible to the user and to the generator's
"wait for processing" logic alike. Failing visibly beats degrading
silently, and the embedding cost of a re-upload is small at the upload
cap in force.

**Rejected alternative:** set `ready` and leave `summary` null, logging
the failure. Keeps the chat usable for that source immediately, rejected
because the gap would surface only as weaker generated outputs, with no
trace of why.

## A transient failure releases the claim with a short, growing backoff

**Id:** b53c94f0-b1e7-47ca-bc17-59b8fd3b967b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the v0.7.1 smoke failure, 2026-10-13: an attempt failed with `NoSuchKey` and no second attempt came within 15 minutes; the backoff values are the ingest author's
**Revisit when:** a provider's rate limit or outage outlasts 20 seconds often enough that three attempts within that window fail sources that would have passed later

After a transient failure the worker keeps the row `processing` with the
error, drops its claim and sets `retry_at`: 5 seconds ahead after the
first failure, 15 after the second. The claim query skips a row until its
`retry_at` has passed. The third failure fails the source for good.

**Reason:** before, a failed attempt kept its claim, so the next attempt
waited for the stale-claim timeout of ten minutes, and the user watched a
source sit at `processing` for that long after a hiccup that would have
passed in seconds. Releasing at once would spend the three attempts
within one poll interval, before a short outage is over; a growing
backoff gives it seconds, not minutes.

**Alternatives:**
- Release the claim at once: the three attempts are gone within a few
  seconds of an outage.
- Keep waiting for the stale-claim timeout: the user waits ten minutes
  per hiccup (the behaviour this replaces).
- Set `claimed_at` into the past so the stale rule fires early: no new
  column, but it hides a retry inside the crash-recovery rule and makes
  `claimed_at` mean two things.

## A source that stalled every attempt is failed, not taken over again

**Id:** 094ed85d-4934-4809-b9ad-b6871eb38c37
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security and quality audit of the service, 2026-10-14, requested by the maintainer; the failure mode was found in the code, not observed live
**Revisit when:** jobs get a time limit of their own (a subprocess or a per-job deadline), which would end a hung job before its claim goes stale

The claim first fails every `processing` row whose claim is stale and
that has had `MAX_ATTEMPTS` claims, then claims among the rows with
fewer. The error says the processing did not finish in that many
attempts.

**Reason:** the stale takeover (4f6e16de-3395-4ae3-ae7b-95ba0d08aa13)
counted attempts but never acted on them: only a job that returned could
fail its row. A source that kills its worker (out of memory in a
renderer) or hangs it (a parser loop) would be taken by the next worker
after every claim timeout, without end, and with several such sources
every worker would be stuck in turn. The rule for three attempts already
held for failures that return; this applies it to the ones that do not.

**Alternatives:**
- A per-job time limit (the job in a subprocess, killed at a deadline):
  would also end a hung job early instead of after three claim
  timeouts, but needs the pipeline to run in a child process with its
  billing and status writes; larger than an audit fix.
- Leaving the claim as it was: the queue's only failure mode with no
  end.

A per-job time limit is the known next step (accepted in the audit,
2026-10-14): until then a hung job holds its worker for up to three
claim timeouts, and after a takeover two workers can write the same row
(the results are the same; the double billing is what the claim refresh
prevents).

## A job in progress refreshes its claim with every model call

**Id:** e3b21110-c7ed-4f74-afba-fb60ae41df3e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security and quality audit of the service, 2026-10-14, requested by the maintainer; derived from the vision PDF timings measured live on 2026-10-13 (about 515 input and 960 output tokens per page), not observed as a double takeover
**Revisit when:** a single model call can take longer than `CLAIM_TIMEOUT_SECONDS`, or jobs get a time limit of their own

Every answered call a model loader bills (an image, a PDF page) and
every embedding batch moves the row's `claimed_at` to now
(`refresh_claim`). The stale-claim rule is unchanged; it now measures
time since the job last made progress, not since it started.

**Reason:** the earlier rejection of a heartbeat (in
4f6e16de-3395-4ae3-ae7b-95ba0d08aa13) assumed a job is bounded by the
upload cap. Vision capture broke that: a PDF of 100 pages is 25 rounds of
four parallel calls, each round as long as its slowest page, which can
exceed the 600-second timeout. A second worker would then take the row
over while the first is still reading, and every page would be read and
billed twice. The refresh rides on calls the job makes anyway, so it
costs one indexed update per call instead of a timer.

**Alternatives:**
- A longer `CLAIM_TIMEOUT_SECONDS`: delays the recovery of a source
  whose worker really died by the same amount, for every source.
- A separate heartbeat thread: refreshes even while the job is hung,
  which would keep a hung job's claim alive forever and defeat the
  stalled-attempt rule.

## A source is read when it is used, not when it is added

**Id:** d80fd88e-9269-4b75-bcb2-f215e4fcd1f7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's decision, 2026-10-14 (analysis starts only when a source is used); the stored status and the endpoint chosen by the ingest author with rag's author
**Revisit when:** users expect their sources to be ready the moment they add them, or the wait before a first answer grows long

Adding a source only stores it, as `added`, stored in
`library_sources.status`; no worker claims it. Rag asks for the sources
an answer or an output uses (`POST /sources/process`), and the web asks
for one with "read now"; those move to `processing` and are read and
billed as before. A source nobody uses costs nothing. The upload keeps
the page count of a PDF and the length of an MP3 or WAV, so the cost of
reading can be estimated before anything is read.

The status is stored, not derived: the claim query needs no change,
workers of the previous release go on claiming only `processing`, and
rag tells unread sources apart in its own SQL.

**Alternatives:**
- Processing at add time, the previous behaviour: every upload was read
  and billed whether it was ever used; the maintainer wants the analysis
  to start only when a source is used.
- A request flag beside `processing` (a nullable `process_requested_at`):
  every reader of the status would have to combine two columns to tell
  unread from waiting.

