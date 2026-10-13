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

## Only a missing key means "not there"; every other storage error raises

**Id:** c7bab6fe-8259-44ce-8451-ad5a3e434065
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** rag's request for cached voice samples at deterministic keys, 2026-10-13
**Revisit when:** a caller needs a cache check that may degrade instead of fail, or the object store reports a missing key with a code other than 404, NoSuchKey or NotFound

`exists(key)` is a HEAD request. It returns `False` only for the codes
an S3 implementation uses for a missing key (`404`, `NoSuchKey`,
`NotFound`). Anything else raises `StorageError`: denied access, a
missing bucket, a 5xx, an unreachable endpoint.

**Reason:** the caller is a cache in front of a paid synthesis. If
"broken" read as "not cached yet", an outage or a revoked key would
re-synthesise and pay on every request, and the fault would show up on
the bill instead of in the logs.

**Rejected alternative:** `False` on any error, the forgiving check.
That is what makes a broken bucket look like an empty cache.

**Rejected alternative:** `get` and catching the miss. That downloads the
whole object just to learn that it exists.

## object_key rejects an unsafe name instead of cleaning it

**Id:** 889932cd-6ceb-4ab1-b95d-23c3c3bcd755
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security audit of core, 2026-10-14
**Revisit when:** a caller legitimately needs a nested name below its owner's prefix

`object_key` takes two UUIDs and one plain name segment and raises
`ValueError` for anything else: an empty name, `/` or `\`, `.` or
`..`, control characters, more than 255 characters.

**Reason:** the key decides whose data an object is (`<user_id>/…` for an
upload, `<notebook_id>/…` for an output). A name with a slash or `..`
could reach into another prefix wherever an S3 implementation or a proxy
normalises paths. Cleaning the name is the caller's job, where the
original filename is known and shown to the user (ingest's `safe_name`).
Core only guarantees the shape, and a caller that skips its own cleaning
fails at once instead of writing somewhere unexpected.

**Rejected alternative:** sanitise the name inside `object_key`. Two
places would then decide what a name becomes, and the stored key would
silently differ from the name the caller recorded.
