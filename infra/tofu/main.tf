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

# Managed PostgreSQL ---------------------------------------------------------

resource "vultr_database" "pg" {
  database_engine         = "pg"
  database_engine_version = var.pg_version
  region                  = var.region
  plan                    = var.pg_plan
  label                   = "${var.label}-pg"
  cluster_time_zone       = "UTC"
  maintenance_dow         = "sunday"
  maintenance_time        = "03:00"
}

resource "vultr_database_db" "app" {
  database_id = vultr_database.pg.id
  name        = var.db_name
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "vultr_database_user" "app" {
  database_id = vultr_database.pg.id
  username    = var.db_user
  password    = random_password.db.result
}

# Object storage -------------------------------------------------------------

data "vultr_object_storage_cluster" "s3" {
  filter {
    name   = "region"
    values = [var.object_storage_region]
  }
}

# The bucket itself is created by `make bucket` (one signed S3 PUT with curl):
# provider 2.33 has no bucket block yet, see context/object-storage.md.
resource "vultr_object_storage" "sources" {
  cluster_id = data.vultr_object_storage_cluster.s3.id
  tier_id    = var.object_storage_tier_id
  label      = "${var.label}-objects"
}
