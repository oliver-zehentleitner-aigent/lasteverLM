# Credit

## Admins are exempt from the credit check

**Id:** c2f224e9-769b-490e-9642-f1914d22c112
**Type:** decision
**Status:** superseded
**Superseded by:** 0eed252c-cde9-420d-bdbc-6d0596b72810
**Evidence:** confirmed
**Source:** the maintainer's product rule, 2026-10-13 ("admins have unlimited credit"; admin-only endpoints in ingest and rag)
**Revisit when:** admins stop being only the maintainer's own accounts, or a non-admin needs unlimited credit

`has_credit(conn, user_id)` is the check every service runs before a model
call: true when `users.is_admin`, otherwise when `balance_cents > 0`. It
is one query (`HAS_CREDIT_SQL`). Admins are still billed: their calls
write `usage` rows like everyone's. Admin-only endpoints use
`is_admin`, read from `users` on every request; the JWT carries no
admin claim, so a change of the flag takes effect at once.

This is the first place core reads account's `users` table. Token
resolution (`current_user`) touches no database, and core's migrations
run before account's, so there is no foreign key and a user without a
row counts as no admin.

**Reason:** the admins are the maintainer's own accounts, used to run and
demonstrate the deployment; a credit wall in front of them only gets in
the way. One rule in the check covers that without a new column or a
ledger entry to keep topped up. Billing them anyway keeps the admin
panel's cost view complete.

**Rejected alternative:** a per-user "unlimited" flag. Rejected because
the set of unlimited users is exactly the set of admins; one more column
would have to be kept in step with `is_admin` by hand.

**Rejected alternative:** a very large credit booked to each admin.
Rejected for the same reason, and because it runs out silently and
distorts the balance the admin panel shows.

**Rejected alternative:** an admin claim in the session JWT. Rejected
because a token lives seven days, so revoking admin rights would wait
for the token to expire.

## One credit rule for every user, admins included

**Id:** 0eed252c-cde9-420d-bdbc-6d0596b72810
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's reversal of the admin exemption, 2026-10-13
**Revisit when:** an account needs to run without a balance (a load test, an internal batch job)

`has_credit` and `ahas_credit` are `balance_cents > 0` for every user;
`HAS_CREDIT_SQL` no longer reads `users`. Admins top up with vouchers
like anyone else. `is_admin`, `ais_admin` and `admin_only` stay as
built: the admin flag, read from `users` per request, gates the admin
endpoints (the panel, the stats endpoints) and nothing else.

**Reason:** the maintainer wants to exercise the voucher path himself,
so his own testing goes through the same credit check and redemption
every user meets; an exemption would hide a broken top-up from exactly
the person most likely to notice it. One rule for every user also keeps
the flag's meaning narrow: admin is about the panel, not about money.

**Rejected alternative:** admins exempt from the credit check (the
previous entry, briefly built and merged). Rejected by the maintainer
for the reason above.
