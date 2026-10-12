# Provisioning

## OpenTofu for the Vultr resources

**Id:** f8e07256-2054-4771-832c-101079071460
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** infra design session, 2026-10-12; the tooling choice was delegated to infra by the family coordinator
**Revisit when:** the Vultr provider stops working with OpenTofu, or the project moves off Vultr

The cluster, the managed database and the object storage subscription
are declared in `tofu/` and applied with OpenTofu through the
`vultr/vultr` provider (`~> 2.33`). The provider is the same binary the
Terraform registry serves; only the CLI differs.

**Reason:** one declarative description with state gives an idempotent
`make up` and a `make down` that removes everything, which a demo that
is torn down between sessions needs. OpenTofu is MPL-licensed, which
suits an MIT portfolio project better than a BUSL tool, and it reads
the HCL any reviewer who knows Terraform already reads.

**Rejected alternatives:** plain `vultr-cli` scripts — no state, so
re-runs and teardown would have to be written by hand and would drift;
Terraform itself — same HCL, same provider, rejected only for the
license, so switching back is a one-word change in the runbook.

## Kubeconfig comes from vultr-cli, not from the OpenTofu state

**Id:** a2760414-e8d9-4b37-ae4f-a62ffd57f658
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** provider source read on 2026-10-12 (`resource_vultr_kubernetes.go` exports no kubeconfig attribute)
**Revisit when:** the provider exports the kubeconfig again

`make kubeconfig` fetches the cluster credentials with
`vultr-cli kubernetes config <id>` and writes them to `build/kubeconfig`.
The provider version in use exports the cluster id and endpoint but not
the kubeconfig, so it cannot be an OpenTofu output. The side effect is
welcome: the state file holds the database password and the S3 keys but
not the cluster admin credentials.
