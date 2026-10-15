# Image sources

## Images are read by the platform's chat model, through a billed loader in ingest

**Id:** a6b20da9-c130-40d8-8897-7bc1276ad2c7
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-13, after a live probe of the inference platform (its model list marks `qwen3.8-27b`, the configured `LLM_MODEL`, as accepting base64 PNG, JPEG, WebP and GIF)
**Revisit when:** a second service needs image input (then the call belongs in core's provider interfaces), or `LLM_MODEL` is switched to a model without image input

An image source becomes text in one chat-completion call to `LLM_MODEL`:
every legible text transcribed verbatim, then a description of the
image, in the language of that text. (Since 2026-10-15 an image over
1.5 MP is read in tiles, one such call per tile: 062573be-f445-432a-a218-d270c1362947.) The call lives in ingest
(`loaders/image.py`) on core's `make_client` and `thinking_body`, behind a
`ModelLoader` protocol that makes the worker record its usage row the
moment it returns (credit is checked once, when the read starts;
accounting.md).

**Reason:** the configured chat model already reads images, so no second
model, price or secret is needed, and one call gives both the text (for
retrieval and citations) and what a chart or photo shows, which OCR
alone would lose. Only ingest needs image input today; core's `LLM`
interface is text-only and core was busy with the audio contract, so
widening it now would have blocked on another service's work for one caller.
A separate protocol, instead of a plain loader that calls the model
quietly, keeps the family rule that every model call is booked.

The first live probe returned an English description of a German
image although the prompt asked for "the language of the text in the
image"; naming the rule with examples (German text, German description)
fixed it on repeated runs. A 12-megapixel, 9 MB JPEG went through in
about seven seconds, so no client-side downscaling was added.

**Alternatives:**
- OCR in the worker (Tesseract): a native dependency in the image, text
  only, no understanding of charts or photos.
- A vision method on core's `LLM` interface: the right home once a
  second service needs it (see Revisit when), not worth a cross-service
  contract change for one caller.
- Calling the model inside a plain `SourceLoader`: the call would be
  neither booked nor covered by the read's credit check.

## The frontend shows an image through a presigned URL of the original

**Id:** 842fded7-0fd7-4886-9651-4323dc3bd090
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request, 2026-10-13: images in the library picker are chosen by seeing them, not by file name; extended by the maintainer, 2026-10-14: the library opens PDFs, texts and URL sources too
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

## A model-made transcript that loops is asked for once more, then fails

**Id:** 6f726417-ccef-4894-bfc4-b68bd46bfe75
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15, after the starter screenshot was read as a few labels and then hundreds of repetitions of one term until the output cap, and outputs were built from it; the detection rules, thresholds and retry settings are the ingest author's
**Revisit when:** a real source fails with the repetition reason although its text is genuine, or the platform's vision or speech model changes

Every model-made transcript (an image, a PDF page read by the vision
model, an audio transcript) is checked for a repetition loop before it is
indexed (loaders/degeneration.py): an n-gram of up to eight words repeated
100 times back to back, a capped answer whose last 200 words are at least
90 % one repetition, or 500 consecutive words with fewer than 25 distinct
ones. An image or page that loops is asked for once more with a
temperature of 0.4 and frequency, presence and repetition penalties. If
it still loops, the source fails with "the model's description
degenerated into repetition". An audio transcript fails at once, because
core's transcriber sends no sampling settings and a second call would
repeat the first. Every call made is billed, and nothing is indexed.

**Reason:** a loop is not a reading of the source. Indexed, it becomes
the ground truth that answers, summaries and outputs are built on, and
nothing downstream can tell it from a real transcript. Failing loudly is
the family rule. The thresholds sit far above what real text does: a
table of identical labels repeats a two-word row dozens of times, a
chorus four or five times, while the observed loop repeated its term
hundreds of times. The distinct-word check runs over windows, because a
long text's share of distinct words falls with its length.

A second attempt costs a second call that the read's estimate does not
include. That overdraw is bounded by one call per image or page (per
tile since tiling, 062573be-f445-432a-a218-d270c1362947), and only for an answer that would otherwise
fail.

**Alternatives:**
- Indexing the loop as it was: the behaviour that built outputs on it.
- Failing at once, without a second attempt: a loop at temperature 0 is
  often one unlucky path, and a second call with penalties may read the
  image; one call more is cheaper than a re-upload.
- Trimming the loop and keeping the start: the model stopped reading
  when it began to repeat, so the rest of the source is missing without
  any sign of it.
- Asking a model whether the text is degenerate: another billed call,
  and not deterministic.

## Large images and vision pages are read in tiles

**Id:** 062573be-f445-432a-a218-d270c1362947
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15, after the vision evaluation (docs/vision-eval.md) showed the platform scales every image to the same small input budget; tile size, overlap and the duplicate rule are the ingest author's
**Revisit when:** the platform reads images at a resolution that depends on their size, or a vision model reads a 2880×1800 screenshot whole as well as in tiles

An image or rendered PDF page over 1.5 MP is cut into the fewest equal
crops of at most 1.5 MP, overlapping by 48 px (loaders/tiles.py). They
are read separately, with the loop check per tile, and joined in reading
order. A line of at least 20 characters that a tile shares with the tile
above or to its left is dropped from the later tile. The upload records
the tile count, and the estimate charges a call per tile.

**Reason:** the platform scales every image to about 400–600 input
tokens, whatever its size. On a large screenshot, small text becomes
unreadable, and every model tested filled it with plausible lines that
are not in the image: wrong numbers, one line copied onto every card, a
label read as another word. A transcript like that is worse than none,
because it is indexed and cited as the source. In tiles, the same models
read the same screenshot and a dense scanned page almost without error.
The cost is about one input budget per tile; the output stays about the
same.

A short line shared by neighbouring tiles is kept, because it may be a
real repetition (a status column of "OK"); a long one is the overlap.

**Alternatives:**
- Switching the vision model: all ten models on the platform invented
  lines on the large screenshot. The cause is the scaling before the
  model, so no model choice fixes it.
- Keeping the full-image read: the loop check cannot catch the failure,
  because invented text varies and looks like a transcript.
- A whole-image description beside the tiles: the downscaled image is
  where the invented lines come from, so its description would bring
  them back.
