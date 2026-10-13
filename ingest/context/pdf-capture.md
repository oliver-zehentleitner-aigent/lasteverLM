# PDF capture

## PDFs are read by text layer, by the vision model, or by both per page

**Id:** d4e19116-b0bf-4968-9e2c-e57eb73978d7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's request through the fleet lead, 2026-10-13 (modes, default, renderer choice); measurement on two scanned A4 pages the same day
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

Pages are rendered at 150 dpi with the long edge capped at 2000 px:
legible for the model without paying for pixels it does not need. pdfium
is not thread-safe (the first version rendered in worker threads and
crashed the test run with a segmentation fault), so pages are rendered
one at a time and only the model calls run in parallel, four at once.
Every answered call is billed as it returns and the credit is checked
before the next batch, so a long scan stops when the credit runs out
instead of overspending it.

**Alternatives:**
- PyMuPDF as the renderer: AGPL, would taint an MIT repository.
- pdf2image: needs the poppler binary in the image.
- OCR (Tesseract) instead of the vision model: a native dependency, text
  only, no description of figures; the vision path already existed for
  images.
- One dedupe key per content regardless of mode: a second upload in
  another mode would silently return the first mode's chunks.
