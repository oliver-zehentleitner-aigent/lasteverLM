# Credits

## Voucher codes are stored encrypted with a key outside the database, beside the hash

**Id:** 221a3630-0523-4fad-a43d-24c995db5b71
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14
**Revisit when:** the key must be rotated (then re-encryption under the new key), or vouchers move to a payment provider

A voucher keeps its SHA-256 `code_hash`, which the redeem uses, and since
migration 0008 also `code_enc`: the plain code under AES-GCM with a random
nonce, keyed by `VOUCHER_KEY` (32 bytes, environment only, the service
refuses to start without it). Admins can show the code again
(`GET /admin/vouchers/{id}/code`) and mail it (`POST /admin/vouchers/{id}/send`);
the list shows it masked. Codes created before 0008 have no `code_enc` and
stay unrecoverable.

**Reason:** the maintainer wants to see, copy and mail vouchers after
creating them. A voucher code is money: whoever reads it can redeem it. Keeping
the key out of the database means a leaked dump or backup alone still yields no
spendable code; it takes the database and the cluster secret together. The hash
stays the lookup path, so the redeem needs neither the key nor a decryption.

**Rejected alternatives:** a plaintext code column — rejected because it turns
any database leak into spendable credit; keeping hash-only storage — rejected by
the maintainer, it makes "show again" and "send later" impossible; deriving the
key from `AUTH_JWT_SECRET` — rejected because a leak of one secret would expose
both sessions and vouchers.

**Consequence:** the key must stay stable. A new key makes every stored code
unrecoverable (404 `not_recoverable`), while the vouchers stay redeemable through
their hash; infra keeps it like `AUTH_JWT_SECRET`, generated once. No rotation
in this round.
