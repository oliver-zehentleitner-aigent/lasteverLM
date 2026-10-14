# Context index

Why `rag/` is built the way it is. Family-wide reasoning lives in the
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

## B

## C

- [citations.md](citations.md) — citations are mapped by the service, not the model; made-up markers dropped, markers split and renumbered densely, and why an unmatched question still reaches the model (only an empty notebook is refused without it); provenance (verbatim chunk, score, position) on every citation; why marker-shaped text from sources is rewritten before prompts

- [contracts.md](contracts.md) — why the shared contract types are mirrored locally until the core library ships

- [conversations.md](conversations.md) — several conversations per notebook instead of one history (tags rejected), and how much history the model sees

- [credit.md](credit.md) — the credit check before any provider call, and how usage is priced (through core's helpers)

## D

## E

## F

## G

## H

## I

## J

## K

## L

## M

## N

## O

- [outputs.md](outputs.md) — generated documents: what a generator sees, why a ready output becomes a generated source, the outputs table as the worker's job queue, and how audio is synthesized and stored; output options per kind (language, voice, speed), cached voice previews, passages balanced across sources for generators; outputs belong to the user (library, trash, origin may be deleted) and rag owns their generated rows; deleting a user removes output files before rows; a shared output is a capability URL whose token reaches access logs (known, mitigated)

## P

- [persistence.md](persistence.md) — why a question and its answer are written together, after the answer exists

- [providers.md](providers.md) — why a model reply without content is a provider failure (502 on ask, retry in the worker), never an empty answer

## Q

## R

- [retrieval.md](retrieval.md) — why the chat lists the notebook's documents and gives generated chunks at most a few slots after the uploads (supersedes uploads-only), why the user's source selection is per request and by link id, and why a scoped question runs without a similarity floor; incident: a ready PDF that never retrieved (its text layer was glyph codes), and the unusable-vector guard

## S

## T

## U

## V

## W

## X

## Y

## Z

