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

- [citations.md](citations.md) — citations are mapped by the service, not the model; made-up markers dropped, markers split and renumbered densely, and why the refusal skips the model; provenance (verbatim chunk, score, position) on every citation

- [contracts.md](contracts.md) — why the shared contract types are mirrored locally until the core library ships

- [conversations.md](conversations.md) — several conversations per notebook instead of one history (tags rejected), and how much history the model sees

- [credit.md](credit.md) — the credit check before any provider call, and how usage is priced while the core library is pending

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

- [outputs.md](outputs.md) — generated documents: what a generator sees, why a ready output becomes a generated source, the outputs table as the worker's job queue, and how audio is synthesized and stored

## P

- [persistence.md](persistence.md) — why a question and its answer are written together, after the answer exists

- [providers.md](providers.md) — why a model reply without content is a provider failure (502 on ask, retry in the worker), never an empty answer

## Q

## R

- [retrieval.md](retrieval.md) — why an unscoped question is answered from the uploads only (pending the maintainer's confirmation), and why a scoped one runs without a similarity floor

## S

## T

## U

## V

## W

## X

## Y

## Z

