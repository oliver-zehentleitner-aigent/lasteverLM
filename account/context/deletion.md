# Deleting a user

## Deleting a user is an orchestrated hard delete, account first asks rag and ingest, then deletes its own rows

**Id:** 47151eae-6a79-49e0-b31c-2422150b49aa
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision (deletion in the admin panel), 2026-10-14
**Revisit when:** a fourth service holds user data, or a deletion must survive a service being down for long (then a queued job)

`DELETE /admin/users/{id}` (admin only, never the reader role) refuses the
caller's own account and the demo user, then calls rag's and ingest's
`DELETE /api/<service>/admin/users/{id}` in that order with the admin's
own bearer forwarded, and deletes its rows only after both answered 2xx:
the user row (ledger and login log cascade), the user's `usage` rows and
the `visit_log` reference. Vouchers the user created or redeemed stay as
history with the reference emptied (migration 0007); `login_attempts`
keep the e-mail. A failing step stops the chain, nothing of account's is
touched, the answer is 502 naming the step. Every service's purge is a
no-op when nothing is left, so the admin repeats the call.

**Reason:** a user's data lives in three services and three stores
(PostgreSQL tables of each, object storage of two). Someone has to drive
the order — storage objects first, because rows can be found again but
orphaned objects cannot — and account is the one service that knows the
user and owns the admin API. Forwarding the admin's bearer means no
service credential exists for this; rag and ingest apply the same
admin-only check they apply to any admin call. Deleting account's rows
last makes the failure mode honest: the user is either fully gone or
still listed, and listed means "try again".

**Rejected alternatives:** a soft-delete flag on the user row with the
data left in place — rejected because the requirement is that the data
is gone, and a flag that hides a user while their objects keep
costing storage is the opposite of that; per-service cleanup jobs that
sweep for users no longer in `users` — rejected because the deletion
would complete at an unknown later time, could not be reported to the
admin, and would need every service to read account's table; deleting
account's rows first — rejected because a later failure in rag or
ingest would leave objects nobody can attribute any more. Keeping the
login log by copying the e-mail into it was considered and dropped: it
is the user's own history, `login_attempts` already keeps the security
record with the e-mail.

**Consequence:** the aggregated usage cost in `/admin/stats` drops by
the deleted user's share; the ledger total drops by their credits. Both
are consequences of the hard delete.
