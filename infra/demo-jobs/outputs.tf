output "jobs" {
  description = "Non-secret definition references for inspection and separately approved manual execution."
  value = { for role, job in google_cloud_run_v2_job.demo : role => {
    name            = job.name
    project         = job.project
    region          = job.location
    service_account = job.template[0].template[0].service_account
    secret_id       = var.foundation.database_secret_ids[role]
    secret_version  = var.secret_versions[role]
  } }
}

output "release_inputs" {
  value = {
    api_image       = var.api_image
    source_sha      = var.source_sha
    schema_revision = var.schema_revision
    import_id       = var.import_id
    worker_run_id   = var.worker_run_id
  }
}
