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

variable "object_storage_cluster_id" {
  description = "Object storage cluster (see `vultr-cli object-storage cluster list`). A region can have several, so the filter data source is ambiguous; 6 is ams1.vultrobjects.com."
  type        = number
  default     = 6
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

variable "bucket_name" {
  description = "Object storage bucket for uploaded sources."
  type        = string
  default     = "lasteverlm-sources"
}
