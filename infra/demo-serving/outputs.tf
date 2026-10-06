output "service" {
  value = {
    name               = google_cloud_run_v2_service.demo.name
    region             = local.region
    uri                = google_cloud_run_v2_service.demo.uri
    candidate_revision = local.revision
    serving_revision   = var.serving_revision
    traffic            = google_cloud_run_v2_service.demo.traffic_statuses
  }
}

output "candidate_release" {
  description = "Candidate metadata only. For promotion/rollback verify the actual serving revision against its retained deployment record."
  value = {
    source_sha             = var.source_sha
    api_image              = var.api_image
    web_image              = var.web_image
    revision               = local.revision
    schema_revision        = var.schema_revision
    import_id              = var.import_id
    runtime_secret_version = var.runtime_secret_version
  }
}

output "access_review" {
  description = "Declared access only; does not prove OAuth configuration, browser login or inherited IAM."
  value = {
    custom_oauth_client_id = var.custom_oauth_client_id
    iap_members            = var.iap_members
    stage                  = length(var.iap_members) == 0 ? "closed-bootstrap" : "named-operator-access"
  }
}
