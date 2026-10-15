# Provisioning

## OpenTofu for the Vultr resources

**Id:** f8e07256-2054-4771-832c-101079071460
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12; the tooling choice was delegated to infra
**Revisit when:** the Vultr provider stops working with OpenTofu, or the project moves off Vultr

The cluster and the object storage subscription are declared in
`tofu/` and applied with OpenTofu through the
`vultr/vultr` provider (`~> 2.33`). The provider is the same binary the
Terraform registry serves; only the CLI differs.

**Reason:** one declarative description with state gives an idempotent
`make up` and a `make down` that removes everything, which a demo that
is torn down between sessions needs. OpenTofu is MPL-licensed, which
suits an MIT portfolio project better than a BUSL tool, and it reads
the HCL any reviewer who knows Terraform already reads. The managed
database is not among them: it was created by hand before the first run
and is an input (`database.md`, entry 210e2af5-c0c6-4459-8aff-9e33a06c52b2).

**Rejected alternatives:** plain `vultr-cli` scripts — no state, so
re-runs and teardown would have to be written by hand and would drift;
Terraform itself — same HCL, same provider, rejected only for the
license, so switching back is a one-word change in the runbook.

## Kubeconfig comes from vultr-cli; the OpenTofu state holds the admin credentials too

**Id:** a2760414-e8d9-4b37-ae4f-a62ffd57f658
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** provider source read on 2026-10-12 (`resource_vultr_kubernetes.go`); the state's attribute names read on 2026-10-14 (provider 2.33.1, names only, not values); the maintainer's decision of 2026-10-14 to keep both as they are for this deployment
**Verification:** corroborated — the state of the `vultr_kubernetes` resource holds `kube_config`, `client_certificate`, `client_key` and `cluster_ca_certificate`; it holds no database password, the database not being in the configuration
**Revisit when:** the deployment is kept beyond the demo, or issue #288 is picked up

`make kubeconfig` fetches the cluster credentials with
`vultr-cli kubernetes config <id>` and writes them to `build/kubeconfig`.
The OpenTofu state holds the same admin credentials anyway: provider
2.33.1 stores the cluster's kubeconfig and client key in the state of
the `vultr_kubernetes` resource, which the 2026-10-12 reading of the
provider source missed. The state also holds the object storage keys,
not the database password. It is kept local, ignored by Git and mode
600 (`make up`), and is a cluster-admin secret.

**Reason:** the deployment lives only as long as the demo and is
deleted afterwards, so neither path is worth changing for it; issue
#288 (https://github.com/oliver-zehentleitner/lasteverLM/issues/288)
keeps the question for a longer-lived deployment.

**Rejected alternatives:** reading the kubeconfig from a tofu output
instead of vultr-cli — one tool less, but the credentials sit in the
state either way, so it changes nothing about where they are.
