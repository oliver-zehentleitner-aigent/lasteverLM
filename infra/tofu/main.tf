# Kubernetes cluster ---------------------------------------------------------

resource "vultr_kubernetes" "cluster" {
  region  = var.region
  label   = "${var.label}-vke"
  version = var.kubernetes_version

  node_pools {
    node_quantity = var.node_count
    plan          = var.node_plan
    label         = "${var.label}-pool"
  }
}

# Managed PostgreSQL: created by the maintainer by hand, not managed here.
# The admin URL is an input to `make env`, which derives the application role's
# URL; `make db-bootstrap` creates role, database and extension. See
# context/database.md.

# Object storage -------------------------------------------------------------

resource "vultr_object_storage" "sources" {
  cluster_id = var.object_storage_cluster_id
  tier_id    = var.object_storage_tier_id
  label      = "${var.label}-objects"
}
