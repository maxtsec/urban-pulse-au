locals {
  region = "australia-southeast2"
  # Existing bootstrap retains ownership of registry, IAM and federation APIs.
  services = toset([
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "run.googleapis.com",
    "iap.googleapis.com",
  ])
  identities = {
    runtime = "Read-only fixture application"
    migrate = "Explicit schema migration job"
    import  = "Explicit fixture import job"
    worker  = "Manually invoked bounded fixture worker job"
  }
  labels = { application = "urbanpulse", environment = "demo" }

  # Deployment prerequisites, NOT a claim that current application pools obey
  # these limits. Read the resource plan before creating any serving/job resource.
  connections = {
    database_limit           = 50
    service_max_instances    = 2
    serving_revision_slots   = 2
    replacement_slots        = 2
    processes_per_instance   = 1
    pool_size                = 2
    max_overflow             = 0
    migration_limit          = 2
    import_limit             = 3
    worker_limit             = 4
    reserved_and_admin_slots = 10
  }
  api_slots = (
    local.connections.service_max_instances * local.connections.serving_revision_slots
    + local.connections.replacement_slots
    ) * local.connections.processes_per_instance * (
    local.connections.pool_size + local.connections.max_overflow
  )
  role_limits = {
    runtime = local.api_slots
    migrate = local.connections.migration_limit
    import  = local.connections.import_limit
    worker  = local.connections.worker_limit
  }
  client_slots = sum(values(local.role_limits))
}

resource "google_project_service" "demo" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

resource "google_sql_database_instance" "demo" {
  name                = "${var.name_prefix}-pg17"
  project             = var.project_id
  region              = local.region
  database_version    = "POSTGRES_17"
  deletion_protection = true

  settings {
    edition                     = "ENTERPRISE"
    tier                        = "db-g1-small"
    availability_type           = "ZONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = 10
    disk_autoresize             = false
    activation_policy           = "ALWAYS"
    connector_enforcement       = "REQUIRED"
    deletion_protection_enabled = true
    retain_backups_on_delete    = true
    user_labels                 = local.labels

    ip_configuration {
      ipv4_enabled   = true
      ssl_mode       = "ENCRYPTED_ONLY"
      server_ca_mode = "GOOGLE_MANAGED_INTERNAL_CA"
      # No authorized_networks or unrestricted direct-client access.
    }
    database_flags {
      name  = "max_connections"
      value = tostring(local.connections.database_limit)
    }
    backup_configuration {
      enabled                        = true
      start_time                     = "16:00"
      location                       = local.region
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }
    maintenance_window {
      day          = 7
      hour         = 17
      update_track = "stable"
    }
  }
  lifecycle {
    precondition {
      condition = (
        local.client_slots + local.connections.reserved_and_admin_slots
        < local.connections.database_limit
      )
      error_message = "Client role budgets plus operational reserve must leave database headroom."
    }
  }
  depends_on = [google_project_service.demo]
}

resource "google_sql_database" "demo" {
  name            = "urbanpulse"
  project         = var.project_id
  instance        = google_sql_database_instance.demo.name
  deletion_policy = "ABANDON"
}

resource "google_service_account" "demo" {
  for_each     = local.identities
  project      = var.project_id
  account_id   = "${var.name_prefix}-${each.key}"
  display_name = each.value
  description  = "DEMO-01 ${each.key}; no deployment, IAM administration or image write authority"
  depends_on   = [google_project_service.demo]
}

resource "google_project_iam_member" "sql_client" {
  for_each = local.identities
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.demo[each.key].email}"
}

# Only empty containers and one-to-one access grants. User/password creation and
# secret versions are a separately reviewed private operation, not Terraform data.
resource "google_secret_manager_secret" "database" {
  for_each            = local.identities
  project             = var.project_id
  secret_id           = "${var.name_prefix}-${each.key}-database-url"
  deletion_protection = true
  labels              = local.labels
  replication {
    user_managed {
      replicas {
        location = local.region
      }
    }
  }
  depends_on = [google_project_service.demo]
}

resource "google_secret_manager_secret_iam_member" "database_reader" {
  for_each  = local.identities
  project   = var.project_id
  secret_id = google_secret_manager_secret.database[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.demo[each.key].email}"
}
