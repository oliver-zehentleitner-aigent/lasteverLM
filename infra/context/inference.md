# Inference

## Model choice on Vultr Serverless Inference: qwen3.8-27b for answers, qwen3-embedding-4b at 1024 dimensions

**Id:** b3a0ecd7-f23e-4cb2-9789-39e9be3371d8
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** `GET https://api.vultrinference.com/v1/models` on 2026-10-12 (catalog, prices, context lengths), embedding probes the same day; the choice itself was delegated to infra by the family coordinator because the maintainer was offline; the same catalog read again on 2026-10-14 (qwen3.8-27b's prices, the TTS unit)
**See:** https://github.com/oliver-zehentleitner/lasteverLM — b57ab97c-0eee-43b3-a7ee-06226e2d9714 — as of 2026-10-14
**See:** https://github.com/oliver-zehentleitner/lasteverLM — b8b85840-a958-42e9-90b4-a9205d5b6f40 — as of 2026-10-14
**Revisit when:** a Llama-class or a stronger multilingual model appears in the catalog, the demo's answer quality is judged, or the prices change

`LLM_MODEL=qwen3.8-27b`, `EMBEDDING_MODEL=qwen3-embedding-4b`,
`EMBEDDING_DIMENSION=1024`, `TTS_MODEL=qwen3-tts-12hz-1.7b`, and
`MODEL_PRICES` from the catalog's prices: qwen3.8-27b
`{"in":15,"out":100}` cents per million input and output tokens,
qwen3-embedding-4b 5, and qwen3-tts-12hz-1.7b 28000 cents per million
seconds of output audio. The maintainer can flip any of these with one
value in the environment and `make deploy`.

The two catalog reads disagree on qwen3.8-27b: the read of 2026-10-12
was recorded as one price per model, 100 cents for `in` and `out`; the
read of 2026-10-14 lists a `prompt` price of 0.00000015 and a
`completion` price of 0.000001 USD per token, 15 and 100 cents per
million. Whether the catalog changed in between or the first read was
wrong is not known. Resolved in favour of the live catalog: the prices
are 15 and 100 since 2026-10-14.

**Reason:** the catalog has no Llama-class model at all. Among the text
models, qwen3.8-27b is multilingual (German sources are the demo case),
has 262k context, is in the same family as the only embedding model,
and costs a third of the strongest option. qwen3-embedding-4b is the
only embedding model; its native 2560 dimensions exceed pgvector's
2000-dimension limit for HNSW and IVFFlat indexes, and the API honours
the OpenAI `dimensions` parameter (verified with 1024 and 1536), so
1024 keeps the index possible and the vectors small. The prices are
read from the API, not from a web page, which is why the evidence is
inferred rather than confirmed: the API's `pricing` field is not
documented as the billing truth.

**Rejected alternatives:** glm-5.3 — the strongest text model in the
catalog, three times the price, kept as the obvious upgrade if answer
quality disappoints; deepseek-v4.1-flash and mimo-v2.6-pro — cheaper,
less known on German text; keeping 2560 dimensions — would have forced
`halfvec` indexes or no index at all.

**Known risks:** qwen3.8-27b is a reasoning model; a probe with
`max_tokens=20` returned only reasoning tokens and an empty answer, so
the services must disable thinking or budget for it. The TTS price unit
conflict is resolved: on 2026-10-14 the catalog lists
qwen3-tts-12hz-1.7b at 0.00028 USD per second of output audio (its unit
read as "token" on 2026-10-12), core first priced `tts` usage per
million characters of input text, and core and rag now record the
seconds the platform reports (`x-usage-seconds`), so the 28000 applies
to seconds (the two See lines).

## Speech to text: whisper-large-v3-turbo, priced per second of audio

**Id:** 1c80fe00-dfdf-4aa4-8ce7-305a977f0d77
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** the maintainer's go for audio sources on 2026-10-14 with this model; price, limits and region from `GET https://api.vultrinference.com/v1/models` the same day; multipart upload measured against `/v1/audio/transcriptions` by core's live probe the same day
**Revisit when:** the catalog lists another transcription model, a region outside the US, or a new price

`STT_MODEL=whisper-large-v3-turbo` (core's default, set explicitly in
`chart/values-prod.yaml` and `compose.yaml`), and `MODEL_PRICES`
`{"in":1111,"out":1111}` for it: the catalog prices the audio at
0.00001111 USD per second, core records `stt` usage as whole seconds
in `in`, so 1111 cents per million seconds. The public pricing page
could not be read (it answers scripted requests with a bot check), so
the number has the same standing as the other prices: read from the
API's `pricing` field.

**Reason:** the model is the maintainer's choice (confirmed); that it is
the only model in the catalog with a transcription output, the
multimodal models that accept audio answering as chat completions, is
read from the catalog (inferred as the reason, like the price).

**Rejected alternatives:** unknown.

**Known risks:** the catalog serves the model only from `sjc` (US), so
users' own uploads leave the EU for transcription. The catalog lists
`audio/wav` and `audio/mpeg` as the only formats, 14400 seconds and
26214400 bytes as the limits (the ingress and the compose gateway
accept 64 MiB, so the platform's cap is the binding one), and
`base64` as the only source; the multipart upload core uses works
nonetheless (measured), so the catalog's `sources` field is not the
whole truth.

## Decision outputs: clef, priced per input token as the API reports it

**Id:** 4cc18e29-0bd3-481b-ba47-4f133035cb86
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** the maintainer's go for a Decision output kind with the platform's decision model on 2026-10-14; price, unit and region from `GET https://api.vultrinference.com/v1/models` the same day; the usage the API reports measured by core's live calls the same day (short and long inputs, one and three questions, clef and clef-flash)
**Revisit when:** the API reports output tokens for clef, the catalog changes its price or unit, or a region outside the US appears

`DECISION_MODEL=clef` (core's default, set explicitly in
`chart/values-prod.yaml` and `compose.yaml`), with `MODEL_PRICES`
`{"in":10,"out":0}` for clef and `{"in":5,"out":0}` for clef-flash:
0.0000001 and 0.00000005 USD per token in the catalog, 10 and 5 cents
per million. The model choice is the maintainer's (confirmed); the
numbers are read from the API's `pricing` field, as for the other
models (inferred).

**Reason:** the catalog and the API disagree on which tokens are billed.
The catalog attaches the price to the `decisions` output as
`completion` tokens; the response body reports `usage.input_tokens`
and 0 output tokens, with no usage or cost headers. Core bills what the
platform reports, so the price sits on `in` and `out` is 0.

**Rejected alternatives:** pricing `out` as the catalog's
`completion` suggests — with the API reporting 0 output tokens, every
decision would be free.

**Known risks:** which count the platform actually invoices is not
verified against an invoice. clef and clef-flash run only in `atl`
(US), like the TTS model.

## Judge candidates: glm-5.3-flash, deepseek-v4.1-flash and glm-5.3, priced per input and output token

**Id:** 83ae95fe-51ab-4309-8fcb-3843b6035210
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** the family coordinator's request on 2026-10-14 for rag's opt-in judge (levels low, medium and high) with models of another family than the author model; prices and regions from `GET https://api.vultrinference.com/v1/models` the same day
**Revisit when:** rag's measurement settles which candidate serves which level (`JUDGE_MODELS`), a candidate is dropped, or the catalog changes a price or region

`MODEL_PRICES` carries all three candidates before the mapping is
final, so whichever rag picks is billed from its first call:
glm-5.3-flash `{"in":10,"out":35}`, deepseek-v4.1-flash
`{"in":15,"out":60}`, glm-5.3 `{"in":75,"out":300}`, read from the
catalog's `prompt` and `completion` prices per token (0.0000001 /
0.00000035, 0.00000015 / 0.0000006, 0.00000075 / 0.000003 USD). The
numbers have the same standing as the other prices: the API's
`pricing` field, not an invoice.

**Reason:** a judge from the author's own family (qwen) would share its
blind spots; the three are the catalog's text models outside it, from
cheap to strong. Which model serves which level is rag's decision after
its measurement, not infra's.

**Rejected alternatives:** unknown (the candidate list is rag's).

**Known risks:** all three run only in `sea` (Seattle, US), like the
author model qwen3.8-27b, so a judged answer and its sources go to the
US twice.
