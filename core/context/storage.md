# Storage

## One synchronous S3 client in core, presigning with SigV4

**Id:** fd494102-fa8c-4509-a928-97395e854911
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the audio output contract in the family's docs/architecture.md (core provides the storage client, an audio output is read through a one-hour presigned GET); a local presign with boto3's default client, 2026-10-13
**Revisit when:** the bucket moves to a provider without SigV4, or a service needs storage calls on its event loop at a volume a thread cannot carry

`lasteverlm_core.storage.S3Storage` is the family's only S3 code: ingest
stores uploads with it, rag stores the audio file and hands the browser a
presigned GET. It is ingest's boto3 class moved, taking an `S3Settings`
loaded with `from_env` like core's other settings, plus
`presigned_get(key, expires_s=3600)`. The boto3 client is created with
`signature_version="s3v4"`.

**Reason:** two services need the same bucket, the same key layout and
the same error type, and a second copy in rag would drift from ingest's.
The presign setting is there because boto3, left at its defaults, signed
the URL in the legacy SigV2 query form (`AWSAccessKeyId`, `Signature`,
`Expires`), while uploads already go out with SigV4; one scheme for both
keeps the object store's support for the old one out of the picture.

**Rejected alternative:** an async client (aioboto3 or aiobotocore) for the
async services. Rejected for now: one more dependency with its own
version coupling to botocore, for a handful of calls per upload or output
that `anyio.to_thread.run_sync` serves.

**Rejected alternative:** keeping ingest's keyword-argument constructor
unchanged. A settings object read from the environment is how core's
auth and inference settings work, and it lets a service fail at startup
on a missing `S3_*` variable instead of at the first upload.
