# Worker

## The request handler stores the file; the worker starts from a source id

**Id:** 964f1308-92b8-4d6f-a93e-5639a92d476e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12; maintainer review pending in the first pull request
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

The credit check runs in the handler, so the user gets a 402 before
anything is stored, and again in the worker before each model call,
because the balance can change in between.

## A failed summary fails the source, even though its chunks are written

**Id:** f11ae1b9-3c5a-4eb7-bc8d-52c1344805ef
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12; maintainer review pending in the first pull request
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
