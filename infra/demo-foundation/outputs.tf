output "database_connection_name" {
  description = "Cloud SQL attachment; application socket path is /cloudsql/<connection_name>."
  value       = google_sql_database_instance.demo.connection_name
}

output "database_name" {
  value = google_sql_database.demo.name
}

output "identities" {
  description = "Separate application and private job service identities."
  value       = { for role, identity in google_service_account.demo : role => identity.email }
}

output "database_secret_ids" {
  description = "Empty containers only; privately create numbered versions before deployment."
  value       = { for role, secret in google_secret_manager_secret.database : role => secret.secret_id }
}

output "deployment_contract" {
  description = "Future runtime controls to implement and verify before deployment, not deployed limits."
  value = {
    connections        = local.connections
    database_role_caps = local.role_limits
    total_client_slots = local.client_slots
    unallocated_slots  = local.connections.database_limit - local.client_slots - local.connections.reserved_and_admin_slots
    api_concurrency    = 4
    api_min_instances  = 0
    worker = {
      trigger     = "manual"
      task_count  = 1
      parallelism = 1
      max_retries = 0
      timeout     = "600s"
      executions  = 1
    }
    access = "explicit-organization-users-or-groups-only"
  }
}
