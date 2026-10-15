# Context index

Why this project is built the way it is. This is the parent of the
lasteverLM family: what is family-wide lives here, what belongs to one
service lives in that service's own `context/`.

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

- [architecture.md](architecture.md) — one repository with isolated contexts, containers only, Helm with automatic deploy on a tag, PostgreSQL as the job queue, rate limiting with blocks and bans, everything on Vultr (Kubernetes, Managed PostgreSQL with pgvector, Object Storage, Serverless Inference), microservices across repositories, the shared core library, self-built citations, usage rows as the debit, magic-link auth, audio through presigned URLs with the storage client in core, fail loud instead of silent fallbacks, everything derived from a user's input checkable by that user, the cheaper path by default with extra cost only on the user's action; the Supabase decision it superseded

## B

## C

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

- [naming.md](naming.md) — why the project is called lasteverLM and which descriptive names lost

## O

## P

## Q

## R

## S

- [scope.md](scope.md) — what the MVP included and left out (superseded), scope growing on the maintainer's orders and the feature freeze, the three-day time budget, the account service with sponsored credit and admin panel

## T

## U

## V

## W

- [workflow.md](workflow.md) — seven parallel coding-agent sessions, agent A reviewing and merging every change for the whole build, one shared agent account with per-agent commit identity, fork-and-PR integration, reading the family's context/ before building, black as the Python formatter, one audit per directory against a shared checklist before the handover

## X

## Y

## Z
