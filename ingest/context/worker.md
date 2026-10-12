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
