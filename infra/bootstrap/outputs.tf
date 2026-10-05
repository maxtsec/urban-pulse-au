# None of these values are secrets; GitHub workflows reference them as plain configuration.

output "workload_identity_provider" {
  description = "Value for google-github-actions/auth workload_identity_provider."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "builder_service_account" {
  description = "Service account the main-branch image workflow impersonates."
  value       = google_service_account.ci_builder.email
}

output "image_repository" {
  description = "Docker image path prefix."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "project_number" {
  description = "Numeric project ID used in federation principal identifiers."
  value       = data.google_project.current.number
}
