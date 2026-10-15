# Model prices

## An unpriced model is a configuration error, not a free call

**Id:** 42268e89-b005-4607-bc32-76e6f4a1ff01
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** core design, 2026-10-12; parent docs/architecture.md, "Model prices"
**Revisit when:** a provider reports its own cost per call, making the price table unnecessary

`cost_cents` raises `UnpricedModelError` for a model that has no entry
in the merged price table, and `require_prices` lets a service raise the
same error at startup for every model it is configured to use. A usage
row is never written at a silent zero tariff.

**Reason:** the balance is the only brake on spending, and a model that
costs nothing in the books costs real money at the provider. One of the
pre-core mirrors priced unknown models at zero and kept going; a typo in
`LLM_MODEL` would have given every user unlimited free calls while the
row count looked healthy. Failing at startup moves the mistake to the
deploy, where it is cheap.

**Rejected alternative:** price unknown models at zero and log a
warning. Rejected because nobody reads the warning before the bill does.

**Rejected alternative:** a default price for unknown models. Rejected
because any default is wrong for some model, and a wrong default hides
the same mistake behind plausible numbers.

Arithmetic is `Decimal`, not `float`: a price of 0.1 cents per million
tokens at exactly one million tokens must be exactly 0.1 cents. Since
the finance redesign the cost is booked exact, without rounding up per
call (`billing.md`), so a float error would show in every row instead of
hiding in a rounding.

## Shipped default prices are empty until the platform's models are known

**Id:** 3b47f88d-81a2-4204-b99a-15c86df40205
**Type:** constraint
**Status:** superseded
**Superseded by:** c94fdf50-58e7-40dc-9d7a-8f52a6a68b0f
**Evidence:** confirmed
**Source:** the state of 2026-10-12: no inference key yet, so no model list
**Revisit when:** an inference key exists and the platform's model names and prices have been read

`DEFAULT_MODEL_PRICES` is an empty table. The architecture says core
ships defaults for the platform's models; at the time of writing nobody
had an inference key, so the model names and their prices were not
known, and every deployment sets `MODEL_PRICES` for the models it uses.

**Reason:** a default table written from memory would carry invented
model names and prices, and a wrong default is worse than a missing one
because the start-up check would pass on it. The empty table plus the
startup check fails loud instead.

## Core ships no default prices; the deployment's MODEL_PRICES is the one price table

**Id:** c94fdf50-58e7-40dc-9d7a-8f52a6a68b0f
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** the code and deployment as of 2026-10-15: `DEFAULT_MODEL_PRICES` is empty, and the chart values and `compose.yaml` price every model the services use
**Verification:** contradicted — docs/architecture.md still says the prices have "defaults in core" (the credits section, the model-prices section and the configuration table); the code ships none
**Revisit when:** a service has to start without a deployment configuration, or the platform publishes prices in a form core could read at runtime

`DEFAULT_MODEL_PRICES` stays empty now that the platform's model names
and prices are known. Every model a service uses is priced in
`MODEL_PRICES` of the deployment (the chart values for the cluster,
`compose.yaml` for a local run). The start-up check still refuses a
configured model without a price.

**Reason:** the prices have changed and grown more than once (the
judge models were priced in the deployment alone), and one table can't
drift from another. A default table in core would be a second copy that
looks authoritative. It would be released with core instead of
configured with the deployment, and a stale default would pass the
start-up check.

**Rejected alternative:** ship the platform's prices as core defaults,
as the architecture first described. Rejected for the reason above.
The original reason for the empty table, that the names and prices
weren't known yet, no longer applies; the table is empty now by choice.
