# Model prices

## An unpriced model is a configuration error, not a free call

**Id:** 42268e89-b005-4607-bc32-76e6f4a1ff01
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** core design and family coordination, 2026-10-12; parent docs/architecture.md, "Model prices"
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
tokens at exactly one million tokens must be one cent, not 1.0000000001
rounded up to two.
