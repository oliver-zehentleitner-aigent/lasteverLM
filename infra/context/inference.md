# Inference

## Model choice on Vultr Serverless Inference: qwen3.8-27b for answers, qwen3-embedding-4b at 1024 dimensions

**Id:** b3a0ecd7-f23e-4cb2-9789-39e9be3371d8
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** `GET https://api.vultrinference.com/v1/models` on 2026-10-12 (catalog, prices, context lengths), embedding probes the same day; the choice itself was delegated to infra by the family coordinator because the maintainer was offline
**Revisit when:** a Llama-class or a stronger multilingual model appears in the catalog, the demo's answer quality is judged, or the prices change

`LLM_MODEL=qwen3.8-27b`, `EMBEDDING_MODEL=qwen3-embedding-4b`,
`EMBEDDING_DIMENSION=1024`, `TTS_MODEL=qwen3-tts-12hz-1.7b`, and
`MODEL_PRICES` from the catalog's per-token price (one price per model,
so `in` equals `out`): 100, 5 and 28000 cents per million tokens. The
maintainer can flip any of these with one value in the environment and
`make deploy`.

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
is in conflict: on 2026-10-14 the catalog lists qwen3-tts-12hz-1.7b at
0.00028 USD per second of output audio (its unit read as "token" on
2026-10-12), while core prices `tts` usage per million characters of
input text, so the 28000 is applied to characters; which unit the
platform bills is open.

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
