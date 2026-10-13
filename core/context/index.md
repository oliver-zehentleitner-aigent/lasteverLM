# Context index

Why `core/` is built the way it is. Family-wide reasoning lives in the
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
- [auth.md](auth.md) — one resolver for session JWT and demo token, why both schemes may be active at once and why there is no audience claim

## B

## C

- [chunking.md](chunking.md) — why the token-window chunker lives in core with regex tokens and serves both parsed sources and generated documents; why its window is 420 regex tokens after measuring German text

## D
- [database.md](database.md) — why core has no database driver, types connections structurally and ships every helper sync and async; why usage has no foreign keys; why the SQL is tested against a throwaway container with a two-column ledger

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

## P
- [packaging.md](packaging.md) — why services install core by path from the same checkout instead of a uv workspace, a lockfile or a published package
- [pricing.md](pricing.md) — why an unpriced model fails the call and the start instead of costing zero, and why the shipped default prices are empty
- [providers.md](providers.md) — why embeddings request their width and why completions run with reasoning off by default; which switch the platform honours

## Q

## R
- [ratelimit.md](ratelimit.md) — why the window is counted over access_log excluding 429s, why the middleware is plain ASGI, which header is trusted, and why an active ban survives the purge for at most ninety days

## S
- [storage.md](storage.md) — why ingest and rag share one synchronous S3 client from core and why presigned URLs are signed with SigV4

## T

## U

## V

## W

## X

## Y

## Z

