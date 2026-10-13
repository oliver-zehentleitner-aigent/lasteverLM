# Context index

Why `account/` is built the way it is. Family-wide reasoning lives in the
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

- [admin-settings.md](admin-settings.md) — the allowlist seed is applied once (an empty one is re-seeded); SMTP comes from the environment only, shown read-only (the plain-text password workaround is superseded)

- [auth.md](auth.md) — the former core mirror in `contracts.py` (superseded), admin addresses bypassing the allowlist (domains and single addresses), shape-only e-mail validation, the demo user's special status, refused sign-in requests answered with 403 `not_allowed`

## B

## C

- [core.md](core.md) — core installed from `../core` as a uv path source; the account service purges core's rate-limit tables at start; the superseded tuple-row detour; the rate-limit rule written by account and read by every service

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

## P

- [privacy.md](privacy.md) — visitor hashing with a daily salt (shared via secret or per process), browser family only, retention at service start; sign-in attempts keep the plain client address

## Q

## R

## S

- [storage.md](storage.md) — one repository interface with PostgreSQL and in-memory implementations, atomic operations as single calls

## T

## U

## V

## W

## X

## Y

## Z

