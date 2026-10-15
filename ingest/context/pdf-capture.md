# PDF capture

## PDFs are read by text layer, by the vision model, or by both per page

**Id:** d4e19116-b0bf-4968-9e2c-e57eb73978d7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request, 2026-10-13 (modes, default, renderer choice); measurement on two scanned A4 pages the same day
**Revisit when:** the vision model's price or quality changes enough that `vision` should be the default, or scans of more than 100 pages are uploaded regularly

A PDF upload has a capture mode: `text` (text layer only), `vision`
(every page rendered and transcribed by the vision model, like an image)
and `auto`, the default (text layer where a page has one, the model for
the pages that have none). Web sends the user's preference explicitly,
so ingest needs nothing from account. The mode is stored on the library
source and is part of a PDF's dedupe key: the same bytes captured by
text and by vision are two library sources, because their chunks differ.

**Reason:** a scanned PDF had no text layer and failed; a mixed PDF lost
its scanned pages silently. `auto` makes both work and pays only for
the pages that need it: `vision` costs one model call per page (about
515 input and 960 output tokens per A4 page in the measurement), `auto`
costs nothing on a PDF with a text layer on every page. The text layer is
exact where it exists; the model's transcription of a scan is good but
misread a running header in the measurement, which is why `auto`
prefers the layer.

"Has a text layer" means a legible one, not any characters: a page
needs 20 visible characters, and at least 60 % of them letters (see the
incident below for why).

Pages are rendered at 150 dpi with the long edge capped at 2000 px:
legible for the model without paying for pixels it does not need. pdfium
is not thread-safe (the first version rendered in worker threads and
crashed the test run with a segmentation fault), so pages are rendered
one at a time and only the model calls run in parallel, four at once.
Every answered call is billed as it returns. The credit was first
checked before each batch, so a long scan stopped when it ran out;
since 2026-10-15 a scan that has started is read to the end and the
credit is checked once, before it starts (accounting.md).

**Alternatives:**
- PyMuPDF as the renderer: AGPL, would taint an MIT repository.
- pdf2image: needs the poppler binary in the image.
- OCR (Tesseract) instead of the vision model: a native dependency, text
  only, no description of figures; the vision path already existed for
  images.
- One dedupe key per content regardless of mode: a second upload in
  another mode would silently return the first mode's chunks.

## A PDF of more than 2000 pages is not read at all

**Id:** ed97ff40-9590-4220-951a-17f613db28ef
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security and quality audit, 2026-10-14; the number decided by the maintainer
**Revisit when:** users upload legitimate documents longer than 2000 pages, or jobs get a time limit of their own

Every capture mode starts by extracting the text layer of every page, so
a PDF's page count bounds the worker time it takes; within the 20 MB
upload cap a file can hold far more tiny pages than any real document.
Above 2000 pages the source fails before any page is read, with the cap
in the message, the way the vision cap of 100 pages fails.

**Reason:** without a cap, worker time per source was bounded only by
the file size; the stalled-attempt rule would end a source that hangs a
worker, but only after three claim timeouts. 2000 pages is beyond any
book a user would reasonably add, so the cap costs no real use.

**Alternatives:**
- No cap, relying on the claim timeout and the stalled-attempt rule:
  half an hour of three workers per hostile file.
- A setting like `PDF_VISION_MAX_PAGES`: no deployment has a reason to
  differ yet; a constant can become one when one does.

## Incident: a text layer of glyph codes was indexed as text

**Id:** bc473b1e-6480-4baf-ac0a-09b63d9a3200
**Type:** incident
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's screenshots, 2026-10-14: a citation into linux_-_VNC-Server.pdf page 2 (chunk 9 of 17) showing "&MM,:N K OP&M,MM P2QL +457$$$ LL R! 3'.SM" at similarity 0.34, and linux_-_vi.pdf page 1 cited as clean text
**Verification:** corroborated
**Revisit when:** a real page with a legible layer is sent to the model or skipped, or a glyph-code layer passes the check

A page of the VNC document carries a text layer whose font has no usable
ToUnicode map, so pypdf returned the glyph codes. The only test was 20
visible characters, so in `auto` the page never reached the vision
model: the salad was chunked, embedded and cited. This is the observed
cause of the incident in which questions about that document were
answered from the other PDF in the notebook (rag's incident entry
54626e80-33da-49e5-8bfd-2a92673a654a, closed with an inferred cause):
its chunks for those pages could not match any question. The two
candidates that entry names, the upload race and the 0.5.0 re-keying,
are not needed to explain it.

The fix is a letter share (`str.isalpha`, so umlauts and other scripts
count) among the visible characters, at least 0.6. Measured: the
screenshot's salad 0.50, uniform glyph codes over printable ASCII
0.45–0.56, the demo PDF's pages 0.94–0.95, German prose with umlauts
0.93, a page of shell commands 0.76. The PDF bytes themselves were not
read; the fixtures are built from the screenshot's text. Known cost: a
page of bare numbers (a table without words, about 0.2) fails too;
`auto` has the model read it, `text` skips it. Library rows indexed
before the fix stay as they are: the dedupe key carries the capture
mode, so a re-upload is a new source, and the demo reset clears the old
ones.

**Alternatives:**
- The share of letters and digits: the salad is 0.65 on it, too close to
  real text with numbers.
- The share of vowels among letters (the salad has almost none): only
  works for Latin scripts.
- Asking the model whether a layer is readable: a billed call for every
  page of every PDF.
