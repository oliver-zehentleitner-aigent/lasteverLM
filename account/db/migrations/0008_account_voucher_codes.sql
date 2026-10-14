-- lasteverLM-account: voucher codes recoverable by admins, sent by mail.
-- Plain PostgreSQL, safe to re-run.

-- code_enc: the plain code encrypted with AES-GCM under VOUCHER_KEY (context/credits.md);
-- null for vouchers created before this, whose codes stay unrecoverable. code_hash keeps
-- serving the redeem. sent_to/sent_at: the last mail an admin sent this voucher with.
alter table vouchers add column if not exists code_enc text;
alter table vouchers add column if not exists sent_to text;
alter table vouchers add column if not exists sent_at timestamptz;
