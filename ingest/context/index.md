# Context index

Why `ingest/` is built the way it is. Family-wide reasoning lives in the
repository root's `context/`.

## 0

## 1

## 2

## 3

## 4

## 5

## 6

## 7

## 8

## 9

## A

- [accounting.md](accounting.md) — why every configured model needs a price or the service refuses to start; why adding a source is free and processing waits for credit; why processing one source is one billed action keyed by the library id; why an action starts only within its estimated maximum and then runs to the end (superseded: the embedding-only price rule, per-step credit checks, the once-per-read check)
- [admin.md](admin.md) — why the admin statistics read stored bytes from a size column instead of listing the bucket
- [audio-sources.md](audio-sources.md) — why a recording is transcribed whole into one passage without positions; why other formats are converted by a minimal ffmpeg and the MP3 kept beside the original

## B

## C

- [chunking.md](chunking.md) — superseded: the regex-token chunker now lives in core, reasoning kept there
- [core.md](core.md) — superseded: the shared library was mirrored locally until it landed in `core/`

## D

## E

## F

## G

## H

## I

- [image-sources.md](image-sources.md) — why images are read by the platform's chat model through a billed loader in ingest, not OCR and not core; why the frontend shows them, and opens PDFs and texts, through a presigned URL; why a model-made transcript (image, vision page, audio) that loops is asked for once more, then fails; why large images and vision pages are read in tiles

## J

## K

## L

- [library.md](library.md) — why sources live in a per-user library that notebooks link, with chunks per library source and URL dedupe by URL, why deleting goes to a trash, and why the schema came in an expand and a contract migration; why deleting a user removes the objects before the rows; why outputs are library items whose lifecycle rag owns; why a shared notebook shows its sources by name, never their files; why the model that made a source's text is stored on the library row

## M

## N

## O

## P

- [pdf-capture.md](pdf-capture.md) — why PDFs have text, vision and auto capture, what each costs, and why pypdfium2 renders one page at a time; why a PDF over 2000 pages is not read; why a text layer must be legible (glyph-code incident)

## Q

## R

## S

- [seeds.md](seeds.md) — why every new user gets a copy of the admin's starter notebook (ready copies, no charge, rag copies the outputs), and the demo library it replaced

## T

## U

- [url-sources.md](url-sources.md) — why the worker fetches URLs through a guard that connects to public addresses only, and why HTML text comes from the standard library parser; why a changed web page becomes a new version and the old one stays for its citations; why each read keeps an inert snapshot; why structured data (JSON, XML, CSV, YAML) is read as lines that name their key path, element path or column, and how hostile documents are bounded

## V

## W

- [worker.md](worker.md) — polling and stale-claim takeover on the database queue, why the request handler stores the file, and why a failed summary fails the source, why a transient failure is retried after seconds, why a source that stalled every attempt is failed by the claim, and why a job refreshes its claim with every model call; why a source is read when it is used, not when it is added

## X

## Y

## Z

