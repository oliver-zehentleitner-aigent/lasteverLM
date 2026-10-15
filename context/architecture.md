# Architecture

## Microservices on Kubernetes, one repository per service, Python everywhere

**Id:** d28cc444-b721-43b0-bdd8-f848ef827ec9
**Type:** decision
**Status:** superseded
**Superseded by:** 0c7901e9-3fba-44af-8c63-8acaa7dc92e9
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

The system is cut into separately deployable services (ingest, rag, web,
plus an infra repository holding the cluster manifests), each in its own
Git repository under the `lasteverLM-` prefix, all backend code in
Python, deployed to a managed Kubernetes cluster on Vultr. This parent
repository holds the architecture, the family-wide `context/` and the
coordination files; it ships no code.

**Reason:** the project is a portfolio piece whose point is to show
architecture and operations judgement, not only a working chat. Separate
repositories also give each coding-agent session (see `workflow.md`) a
clean workspace with no merge contention, and Kubernetes is the
maintainer's home ground, so the ops cost is known rather than
speculative.

**Rejected alternative:** a single FastAPI monolith in one repository
with Docker Compose. Faster to an MVP and cheaper to run, rejected
because it would demonstrate none of the things the project exists to
demonstrate, and because four agents in one repository would spend their
time on merge conflicts. Known cost of the chosen path: cluster setup and
cross-repository coordination eat time that is not spent on features.

## Supabase as database, vector store, file storage and auth provider

**Id:** 95c444f7-45b9-4ef0-a5be-cc2b47e73d9d
**Type:** decision
**Status:** superseded
**Superseded by:** 1551d8e8-e2b1-41ef-839d-2ef681d6d595
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Notebooks, sources, chunks with their embeddings (pgvector), chat
messages and uploaded files all live in one Supabase project. Services
talk to it with the Supabase client and the service-role key; the
frontend never holds that key.

**Reason:** one managed component covers Postgres, vector search, object
storage and (if enabled, see below) authentication, which keeps the
cluster to the services this project actually writes. Supabase is also a
stack the project's audience knows, so it needs no explanation in a demo.

**Rejected alternative:** a self-run Postgres with pgvector plus MinIO
inside the cluster. Rejected because it adds two stateful workloads to
operate for no gain in the demo. A dedicated vector database (Qdrant,
Weaviate) was not seriously in contention: pgvector is enough at this
data volume and avoids a second store to keep consistent.

## Hosted Supabase or self-hosted on the cluster

**Id:** b376e44e-18b5-4857-af4b-5f3fcb7ecb4d
**Type:** decision
**Status:** superseded
**Superseded by:** 1551d8e8-e2b1-41ef-839d-2ef681d6d595
**Evidence:** unknown
**Source:** planning conversation, 2026-10-12

Whether the Supabase project runs on supabase.com (free tier) or is
self-hosted on the Vultr cluster is not decided yet. The proposal on the
table is the hosted free tier, so that the whole hosting budget goes into
the cluster and no ops time goes into running Supabase. Until decided,
services must not assume anything beyond the public Supabase API.

## Model providers for the LLM and the embeddings

**Id:** b059feca-be73-4d1f-8af6-e5d3fd46b228
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** answer or citation quality of the open-weight models is not good enough for the demo

Both the language model and the embeddings come from Vultr Serverless
Inference, used through the OpenAI SDK with a configurable base URL.
The embedding dimension is a configuration value with a default of
1536, identical in ingest and rag.

**Reason:** it keeps the whole stack on the one cloud account whose
credit pays for the project, needs no second API key, and the
OpenAI-compatible interface means any other compatible provider is a
config change. Citations are built by the rag service itself, so no
provider-specific citation feature is needed (see the entry below).

**Rejected alternatives:** Claude through the Anthropic API with its
citations feature, which maps well onto cited answers but ties the
citation path to one provider and needs a separate key and budget;
OpenAI or OpenRouter for either side, rejected for the same reason.
Embeddings from a model running inside the cluster were briefly
considered and rejected: CPU cost on the cluster for something the
inference API already offers. Claude stays the fallback if the
open-weight models cite poorly, through the same interface.

## Authentication: magic link restricted to allowed e-mail domains, plus a demo token

**Id:** 38a1cd64-0e61-4e5f-9ce6-058d3ad01659
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Users log in with a magic link: enter an e-mail address, receive a
link, click, done. Only addresses on an allowlist get a link, by domain
or as a single address (single addresses and the viewer domains were
added later; addresses in `ADMIN_EMAILS` are admins); the allowlist
lives in the database, is edited in the admin
panel, and is seeded once from an environment variable, so it never
appears in a repository. A demo token from config resolves to a seeded
demo user for development and recorded walkthroughs and is unset in
production.

**Reason:** the deployment is meant for a known group of people who
should be able to create an account without anyone handing out
credentials, and without a password to manage. The allowlist does that.
Keeping the list out of the repositories is a privacy requirement of
the maintainer.

**Rejected alternatives:** Supabase Auth, gone with Supabase (see the
platform entry); e-mail plus password, rejected because it adds reset
flows and password storage for no gain with this user group; a demo
token only, rejected because the project should show real multi-user
separation and the sponsored credit model needs accounts.

## Everything on Vultr: Kubernetes, Managed PostgreSQL with pgvector, Object Storage, Serverless Inference

**Id:** 1551d8e8-e2b1-41ef-839d-2ef681d6d595
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the hosting credit runs out or a Vultr service is missing something the MVP needs

The cluster, the database with its vector index, the upload storage and
the model inference all come from Vultr. Supabase is out. Mail is the
one external piece, over SMTP whose configuration comes from the
environment (corrected 2026-10-16: it was first planned in the admin
panel; see `account/context/admin-settings.md`).

**Reason:** the maintainer holds a hosting credit on this account that
cannot be paid out, so everything that runs there is effectively free,
and one account with one API key is a cleaner story than a cluster on
one provider and data on another. Managed PostgreSQL means no stateful
workload to back up inside the cluster. The pgvector extension is
available there under the name `vector`.

**Rejected alternatives:** Supabase hosted (free tier limits, a second
provider, and nothing it offered that the project needs beyond
Postgres, storage and auth, each of which has a Vultr or an own
replacement); Postgres inside the cluster through an operator
(CloudNativePG), rejected because it adds a stateful workload with a
backup story to operate during a three-day build for a showcase gain
nobody asked for.

## Citations are built by the rag service, not taken from a provider feature

**Id:** 8457792a-46f9-4029-8d9c-cd8089d7e266
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Retrieved chunks go numbered into the prompt, the model answers with
`[n]` markers, and rag maps each marker back to the chunk, its source
and page, dropping markers that point at nothing. The citation model
is defined once, in core, and the frontend knows only that model.

**Reason:** this works with every OpenAI-compatible provider and keeps
the provider choice a configuration matter. A provider-side citation
feature would tie the core requirement of the product to one vendor.

**Rejected alternative:** the Anthropic citations API. Better citation
quality out of the box, rejected because it would make the one feature
the product is about provider-specific.

## Shared core library instead of duplicated contracts

**Id:** 97441817-e59f-45c1-aba4-5d585ecd6940
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** a service needs a model or helper the others must not see

The Pydantic models, settings loading, bearer-token resolution, the
rate-limit middleware, usage accounting (`record_usage`,
`balance_cents`, model prices) and the provider interfaces live in one
Python package, `core/`, which account, ingest and rag depend on. It is
copied into their images at build time and never published (see the
containers-only entry).

**Reason:** three services sharing one database need one definition of
the rows and one way to price a model call; duplicating a hundred lines
three times is where the first drift between services starts. A library
is also where the "one interface, one implementation" rule is enforced
rather than only described.

**Rejected alternative:** copy the shared code into each service.
Faster tonight, rejected because every later change to a contract
would have to land in three repositories in lockstep. Known cost of the
chosen path: a version pin to keep current in three places.

## Usage rows are the debit; no second ledger write

**Id:** 454bd7eb-b5a2-4c63-9544-6425f342a5a6
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Every model call writes one `usage` row with its token counts and a
`cost_cents` priced at write time by the service that made the call,
through a core helper and a price table from config, and the charge to
the user fixed at the same moment (the cost plus the margin and fixed
fee of the pricing rules, see the finance entries in `core/` and
`account/`). The balance is the sum of ledger credits minus the sum of
usage charges. The account
service only reads usage.

**Reason:** one write per call, done by the service that has the
numbers, cannot drift from a separate debit written later by another
service; and pricing at write time means a price change never rewrites
history. Services share the database, so no service call is needed for
accounting.

**Rejected alternative:** services write raw token counts and the
account service turns them into ledger debits afterwards. Rejected
because it needs a second writer and a reconciliation that can lag or
fail, for the same result.

## One repository with isolated contexts instead of one repository per service

**Id:** 0c7901e9-3fba-44af-8c63-8acaa7dc92e9
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** a service needs its own release cadence or its own access control

The whole family lives in the one repository `lasteverLM`: the root is
the umbrella (architecture, family-wide `context/`, task board,
workflows), each service is a directory with its own Keep the Why
instance (`parent: ..`, own `context/`), nested further if a service
ever grows children. The service cut, Python everywhere and Kubernetes
stay as in the superseded entry; only the repository boundary moved.

**Reason:** six repositories were about to be created only so that six
agents have separate workspaces, and that separation is just as real
with six directories and six branches, while one repository gives one
pull request flow, one CI, one tag that releases everything, one place
to clone, and no cross-repository version pins for the core library.
It also removed the blocker that the agent account cannot create
repositories under the maintainer's name.

**Rejected alternative:** one repository per service (the superseded
entry). Keeps per-service history and access control cleanest, rejected
because this project releases as one unit and nothing here needs
separate access.

## Containers only: Python source in images, nothing published as a package

**Id:** f54d7995-ab3a-4561-89f3-1369ee7ad82b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

Every service ships as one image in GitHub's container registry with
its Python source inside; `core/` is copied into the images of the
services that use it. Nothing is compiled, nothing goes to PyPI or
conda.

**Reason:** the unit of delivery is the running system, not a library
anyone installs; publishing packages would add release steps, version
pins and a second artifact to keep consistent, for no consumer.

**Rejected alternative:** core as a PyPI package pinned by the services
(the earlier plan). Rejected with the move to one repository, where a
path copy at build time is simpler and always consistent.

## Helm chart and automatic deployment on a tag, images in GitHub's registry

**Id:** 2e06adc5-8bce-4d32-95a9-cacbafe32a4b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** more than one environment (staging, production) exists

One Helm chart for the whole application, chart version equal to the
repository tag. A tag `v*` builds and pushes the images to ghcr.io and
runs the Helm upgrade on the cluster; a merge to `main` only builds.
Rollback is a Helm rollback.

**Reason:** a release has to be one action with one version, and Helm
gives that together with templated manifests, upgrade history and
rollback. ghcr.io sits next to the repository and needs no second
account.

**Rejected alternatives:** raw manifests with kustomize and a manual
deploy workflow (the first plan), rejected because it leaves
versioning and rollback to hand work; Vultr Container Registry,
considered to keep everything on one account, rejected because the
images belong next to the source and the registry is not where the
credit is spent.

## PostgreSQL is the job queue; workers claim with SKIP LOCKED

**Id:** 5a0e357d-cc6b-4e6c-8760-92a926a1f0fe
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** job volume or latency makes row claiming a bottleneck

Source processing and output generation run in worker Deployments that
claim rows from `sources` and `outputs` with `FOR UPDATE SKIP LOCKED`,
re-claim abandoned rows after ten minutes, and give up after three
attempts. API pods only insert rows and read status.

**Reason:** the maintainer wants every process to be startable any
number of times. Background work inside an API process breaks that:
a job dies with its pod and two replicas would both pick it up. The
tables already carry the job state, so PostgreSQL's row locks make any
number of workers safe without a broker to run, secure and back up.

**Rejected alternatives:** in-process background tasks (the v1 plan),
rejected for the reasons above; a message broker (Redis, RabbitMQ),
rejected because it is one more stateful component for a queue that
fits in the tables that exist.

## Rate limiting at the ingress plus blocks and bans in a core middleware

**Id:** 9b5e0211-3625-4353-ba19-64a33f39a626
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the deployment is exposed to real traffic and the limits prove wrong

Coarse per-IP rate limiting on the ingress, and a middleware in core
that every API service loads: a window per IP in PostgreSQL, 429 and a
15-minute block when exceeded, a ban on the third block within 24
hours, lifted only by an admin. Every request is written to an access
log with the raw IP, kept 30 days for the security purpose; the
visitor log keeps hashes. All of it visible in the admin panel.

**Reason:** the maintainer's requirement is that someone hammering the
service is blocked automatically and repeat offenders are banned at IP
level, and that access is logged and reviewable. Doing the fine layer
in the application keeps the state in the one database that already
scales with the pods, and makes the admin panel the one place to see
and lift.

**Rejected alternatives:** a fail2ban-style controller reading ingress
logs and rewriting a deny list, rejected as a moving part with
privileged cluster access for a simple rule; keeping the counters in
Redis, rejected because it adds a stateful component the project does
not otherwise need.

## Supabase self-hosted inside the cluster: not used

**Id:** 93a2b954-818b-4202-b961-3c2ea10fd236
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12

The maintainer raised running Supabase as containers in the cluster and
settled it the same evening: no. The database is Vultr Managed
PostgreSQL in Frankfurt, created by the maintainer by hand and handed
to infra as an input, not provisioned by the infrastructure code.

**Reason:** everything Supabase would have added already has a place
here (auth in the account service, files in object storage, vectors in
pgvector), and self-hosting it means about ten containers plus a
stateful database with a backup story on a community chart, for a
three-day build.

**Rejected alternatives:** Supabase self-hosted (above); CloudNativePG
with a pgvector image as the lighter in-cluster path, not needed once
the managed instance existed.

## Audio files are served through presigned URLs; the storage client lives in core

**Id:** 0694e89f-e85a-4d0d-89f7-5cce8a3dc589
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** rag's text-to-speech probe on the inference platform, 2026-10-13; coordinator decision the same morning

An audio output is an MP3 in object storage at
`<notebook_id>/<output_id>/audio.mp3`. The output row stores the object
key; every read of the output (single, list, shared link) replaces it
with a presigned GET URL that expires after one hour. The S3 client
moves from ingest into core (`lasteverlm_core.storage`, with a presign
call) so rag does not grow a second one. Text-to-speech is billed through a third `usage.kind`, `tts`, with
the unit in `tokens_in`: per input character at first; since
2026-10-14 per second of generated speech as the platform reports it,
because a measured call showed the platform charges seconds and the
character count overcharged about fifteenfold (core's entry
b57ab97c-0eee-43b3-a7ee-06226e2d9714 has the measurement; the
presigned-URL decision here is untouched).

**Reason:** the browser's `<audio>` element fetches its source on its own
and cannot send the bearer token, so an authenticated download through
the API would need a token in the URL or a cookie, both new auth paths.
A presigned URL keeps the API contract (`{"url"}`) and the share page
unchanged, and object storage serves the bytes instead of a rag pod. One
storage client in core follows the rule that shared behaviour lives in
core; ingest switches to it when its owner has time, which is not on the
audio path.

**Rejected alternatives:** streaming the file through the rag API with
a short-lived download token — rejected as a second auth scheme for one
output kind; storing the MP3 in PostgreSQL as bytea — rejected because
uploads already live in object storage and the row would carry
megabytes; a rag-local copy of the S3 class now and consolidation later
— rejected because the core module is a move, not new code, and the
owner of core is free this morning. A fourth usage kind instead of
reusing `tokens_in` for the unit was not considered worth a schema
column: the unit is named by the kind.

## Fail loud: a wrong or missing value stops the process, nothing falls back silently

**Id:** 3e37d3d9-bf02-413e-ac38-9e4e51a7ab3f
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's standing rule for all of his projects, restated for this family 2026-10-13

A service that finds its configuration wrong or incomplete refuses to
start and names the value. A loader that extracts no text fails the
source instead of marking it ready. A runbook target that is handed an
inconsistent environment stops before it writes anything. A provider
answer that cannot be used (an empty description, a vector that is not
finite) is an error that is recorded and surfaced, not a value that is
quietly replaced. The only sanctioned fallback is a documented default
for a value that is genuinely optional, and that default is in the
code, not in a catch block.

**Reason:** a silent fallback moves the failure to the place where it
is hardest to see, the user's result: a source that is "ready" without
usable embeddings answers every question with "no information", and
the operator sees a healthy system. Loud failure costs one restart or
one failed upload and is found in the log in minutes.

**Rejected alternative:** degrade gracefully, serve what is available
and log a warning. Rejected because warnings in a pod log are read by
nobody until a user complains, and because every service in this
family has at least two replicas behind a load balancer, where a
partially working pod is indistinguishable from a working one.


## The cheaper path is the default; every extra cost is the user's own action

**Id:** 5009c08b-6a92-4f49-8a40-63d1377f9435
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer, 2026-10-14, on reading sources only when used and on cached versus refetched web pages

Whenever the system can do something more cheaply or more expensively,
the default is the cheaper one, and the more expensive one happens only
because the user chose it: adding a source stores it, reading it waits
until it is used; a web page is taken from the cache unless the user
asks for it to be fetched again, page by page; the judge is off unless
chosen; a price is shown before any paid step, and a plan of the chat
runs only after confirmation.

**Reason:** the user pays for every model call. A system that spends
on their behalf by default, even with good intent, makes the bill
something that happens to them; one that spends only on their action
keeps every charge explainable by a click they made, which is also
what the Credits page lists.

**Rejected alternative:** process everything eagerly so results are
instant (the behaviour before 2026-10-14). Rejected by the maintainer:
it charges for sources that may never be used and hides the moment the
cost arises.
