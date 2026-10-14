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

- [agent.md](agent.md) — the agent chat: plan, confirm, then run as the user (no stored tokens, ingest steps inside the confirm request, a 30-minute timeout that fails visibly); tool arguments only from the user's message and library, the planner sees no passage

## B

## C

- [citations.md](citations.md) — citations are mapped by the service, not the model; made-up markers dropped, markers split and renumbered densely, and why an unmatched question still reaches the model (only an empty notebook is refused without it); provenance (verbatim chunk, score, position) on every citation; why marker-shaped text from sources is rewritten before prompts; generated outputs: units checked by word overlap without a model, marked never blocked; the user's instructions steer a generator but never override the rules or the citation rules (and stay visible when shared); a chart's values get an exact number check, not word overlap

- [contracts.md](contracts.md) — why the shared contract types are mirrored locally until the core library ships

- [conversations.md](conversations.md) — several conversations per notebook instead of one history (tags rejected), and how much history the model sees; suggested questions as a text tail of the answer's call

- [credit.md](credit.md) — the credit check before any provider call, and how usage is priced (through core's helpers); every usage row booked under its user action, an output with its judge rounds as one action; without an exchange rate nothing that calls a model runs

## D

## E

## F

## G

## H

## I

## J

- [judge.md](judge.md) — the opt-in judge: another model family than the author, the level-to-model mapping measured (evals/judge, docs/judge-eval.md), low and medium swapped because hidden reasoning made the cheaper-listed model dearer; opt-in with the word check as the default (no judge for charts); at most three rounds of revision, then removal listed in the provenance

## K

## L

## M

## N

## O

- [outputs.md](outputs.md) — generated documents: what a generator sees, why a ready output becomes a generated source, the outputs table as the worker's job queue, and how audio is synthesized and stored; output options per kind (language, voice, speed), cached voice previews, passages balanced across sources for generators; outputs belong to the user (library, trash, origin may be deleted) and rag owns their generated rows; four audio styles (overview, story, conversation, faq) and two voices for a conversation or an FAQ; report style and length and quiz count, difficulty and audience as prompt variants with stored defaults; a shared notebook shows uploads by name and ready outputs as their shared view; a chart in two steps, from candidates the client sends back and rag checks again; a decision: number from the decision model, evidence from the LLM independently, agreement shown; a starter notebook's outputs copied by the worker from a queue row ingest writes; deleting a user removes output files before rows; a shared output is a capability URL whose token reaches access logs (known, mitigated)

## P

- [persistence.md](persistence.md) — why a question and its answer are written together, after the answer exists

- [providers.md](providers.md) — why a model reply without content is a provider failure (502 on ask, retry in the worker), never an empty answer

## Q

## R

- [retrieval.md](retrieval.md) — why the chat lists the notebook's documents and gives generated chunks at most a few slots after the uploads (supersedes uploads-only), why the user's source selection is per request and by link id, and why a scoped question runs without a similarity floor; an answer waits up to 60 s for sources being read, then answers from what is ready; incident: a ready PDF that never retrieved (its text layer was glyph codes), and the unusable-vector guard

## S

## T

## U

## V

## W

## X

## Y

## Z

