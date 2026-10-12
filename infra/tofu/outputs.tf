output "vke_id" {
  description = "VKE cluster id; `vultr-cli kubernetes config <id>` returns the kubeconfig."
  value       = vultr_kubernetes.cluster.id
}

output "vke_endpoint" {
  value = vultr_kubernetes.cluster.endpoint
}

output "database_url" {
  description = "Connection string for the services, TLS required by Vultr."
  value       = "postgresql://${vultr_database_user.app.username}:${vultr_database_user.app.password}@${vultr_database.pg.host}:${vultr_database.pg.port}/${vultr_database_db.app.name}?sslmode=require"
  sensitive   = true
}

output "database_admin_url" {
  description = "Admin connection string; only `make migrate` needs it (CREATE EXTENSION)."
  value       = "postgresql://${vultr_database.pg.user}:${vultr_database.pg.password}@${vultr_database.pg.host}:${vultr_database.pg.port}/${vultr_database_db.app.name}?sslmode=require"
  sensitive   = true
}

output "s3_endpoint" {
  value = "https://${vultr_object_storage.sources.s3_hostname}"
}

output "s3_bucket" {
  value = var.bucket_name
}

output "s3_access_key" {
  value     = vultr_object_storage.sources.s3_access_key
  sensitive = true
}

output "s3_secret_key" {
  value     = vultr_object_storage.sources.s3_secret_key
  sensitive = true
}

output "s3_region" {
  description = "Region token for SigV4 signing against the object storage endpoint."
  value       = var.object_storage_region
}
