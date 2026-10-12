variable "label" {
  description = "Label prefix for every resource this configuration creates."
  type        = string
  default     = "lasteverlm"
}

variable "region" {
  description = "Vultr region for the cluster and the database (see `vultr-cli regions list`)."
  type        = string
  default     = "fra"
}

variable "object_storage_region" {
  description = "Vultr region for object storage. Not every compute region has an object storage cluster; `fra` has none as of 2026-10, `ams` is the nearest."
  type        = string
  default     = "ams"
}

variable "object_storage_tier_id" {
  description = "Object storage tier (see `vultr-cli object-storage tier list`). No default: tiers are account-visible only and change over time."
  type        = number
}

variable "kubernetes_version" {
  description = "VKE version string, e.g. `v1.37.1+2` (see `make vke-versions`)."
  type        = string
  default     = "v1.37.1+2"
}

variable "node_plan" {
  description = "Plan of the worker nodes (see `vultr-cli plans list`)."
  type        = string
  default     = "vc2-2c-4gb"
}

variable "node_count" {
  description = "Number of worker nodes in the default pool."
  type        = number
  default     = 2
}

variable "pg_version" {
  description = "Managed PostgreSQL engine version."
  type        = string
  default     = "17"
}

variable "pg_plan" {
  description = "Managed database plan (see `vultr-cli database plans`)."
  type        = string
  default     = "vultr-dbaas-startup-cc-1-55-2"
}

variable "db_name" {
  description = "Logical database the services connect to."
  type        = string
  default     = "lasteverlm"
}

variable "db_user" {
  description = "Database role the services connect as."
  type        = string
  default     = "lasteverlm"
}

variable "bucket_name" {
  description = "Object storage bucket for uploaded sources."
  type        = string
  default     = "lasteverlm-sources"
}
