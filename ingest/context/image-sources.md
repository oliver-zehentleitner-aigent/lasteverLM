# Image sources

## Images are read by the platform's chat model, through a billed loader in ingest

**Id:** a6b20da9-c130-40d8-8897-7bc1276ad2c7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-13, after a live probe of the inference platform (its model list marks `qwen3.8-27b`, the configured `LLM_MODEL`, as accepting base64 PNG, JPEG, WebP and GIF); maintainer review in the pull request
**Revisit when:** a second service needs image input (then the call belongs in core's provider interfaces), or `LLM_MODEL` is switched to a model without image input

An image source becomes text in one chat-completion call to `LLM_MODEL`:
every legible text transcribed verbatim, then a description of the
image, in the language of that text. The call lives in ingest
(`loaders/image.py`) on core's `make_client` and `thinking_body`, behind a
`ModelLoader` protocol that makes the worker check the credit before it
and record its usage row after it.

**Reason:** the configured chat model already reads images, so no second
model, price or secret is needed, and one call gives both the text (for
retrieval and citations) and what a chart or photo shows, which OCR
alone would lose. Only ingest needs image input today; core's `LLM`
interface is text-only and core was busy with the audio contract, so
widening it now would have blocked on another agent for one caller.
A separate protocol, instead of a plain loader that calls the model
quietly, keeps the family rule that every model call is credit-checked
and recorded.

The first live probe returned an English description of a German
image although the prompt asked for "the language of the text in the
image"; naming the rule with examples (German text, German description)
fixed it on repeated runs. A 12-megapixel, 9 MB JPEG went through in
about seven seconds, so no client-side downscaling was added.

**Alternatives:**
- OCR in the worker (Tesseract): a native dependency in the image, text
  only, no understanding of charts or photos.
- A vision method on core's `LLM` interface: the right home once a
  second service needs it (see Revisit when), not worth a cross-agent
  contract change for one caller.
- Calling the model inside a plain `SourceLoader`: the call would be
  neither credit-checked nor accounted.

## The frontend shows an image through a presigned URL of the original

**Id:** 842fded7-0fd7-4886-9651-4323dc3bd090
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request through the coordinating agent, 2026-10-13: images in the library picker are chosen by seeing them, not by file name; extended by the maintainer, 2026-10-14: the library opens PDFs, texts and URL sources too
**Revisit when:** uploaded images grow large enough that loading the originals in a list is slow, or the bucket becomes reachable only through the API

Every listing that names an image source (a notebook's sources, the
library, the trash) carries `preview_url`: a presigned GET of the
stored object, valid for an hour, signed when the list is served
(`api/deps.py`, `preview_url`). Since 2026-10-14 the same holds for PDF
and text sources, so the library can open a document: the object was
always stored with its type (`application/pdf`,
`text/plain; charset=utf-8`), so the browser shows a PDF in its viewer
and a text as text. A URL source carries its URL; a generated row
`null`. The object key itself stays out of the API (`storage_path` is
excluded from the response models).

**Reason:** an `<img>` element cannot send the bearer token, and a
presigned URL needs no further call to ingest; rag hands out its audio
the same way, so the frontend has one mechanism. Signing is local to the
S3 client, so a listing costs no extra round trip. The originals are
small enough to show directly.

**Alternatives:**
- An ingest endpoint that streams the object: every thumbnail would pass
  through the API and need the token, which an `<img>` cannot send.
- Thumbnails rendered at upload: a second object per image and a resize
  step, for originals that are already small.
