data "google_project" "current" {}

locals {
  # Bootstrap only. Cloud Run, Cloud SQL, IAP and runtime identities follow in
  # the DEMO-01 resource plan.
  services = toset([
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])

  # Exact-match claim policies. tests/unit/test_github_oidc_policy.py evaluates
  # the same file against push, pull_request, pull_request_target and other tokens.
  oidc_policy  = jsondecode(file("${path.module}/github-oidc-policy.json"))
  policy_value = concat(values(local.oidc_policy.provider), values(local.oidc_policy.image_builder))
  policy_claim = concat(keys(local.oidc_policy.provider), keys(local.oidc_policy.image_builder))

  provider_condition = join(" && ", [
    for claim in sort(keys(local.oidc_policy.provider)) :
    "assertion.${claim} == '${local.oidc_policy.provider[claim]}'"
  ])
  # The repository claims are already enforced by the provider condition.
  image_builder_condition = join(" && ", [
    for claim in sort(keys(local.oidc_policy.image_builder)) :
    "assertion.${claim} == '${local.oidc_policy.image_builder[claim]}'"
  ])
}

resource "google_project_service" "bootstrap" {
  for_each = local.services
  service  = each.value
  # Removing this configuration must not disable APIs that other resources use.
  disable_on_destroy = false
}

# Adopt the repository created in the console instead of creating a duplicate.
import {
  to = google_artifact_registry_repository.images
  id = "projects/${var.project_id}/locations/${var.region}/repositories/${var.artifact_repository_id}"
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.artifact_repository_id
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"
  # Matches the console default; no cleanup policies are defined yet, so nothing is deleted.
  cleanup_policy_dry_run = true

  depends_on = [google_project_service.bootstrap]
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC tokens from the UrbanPulse AU repository"

  depends_on = [google_project_service.bootstrap]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "urban-pulse-au"
  display_name                       = "urban-pulse-au"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.repository_id" = "assertion.repository_id"
    "attribute.ref"           = "assertion.ref"
    "attribute.event_name"    = "assertion.event_name"
    "attribute.workflow_ref"  = "assertion.workflow_ref"
    "attribute.image_builder" = "(${local.image_builder_condition}) ? 'allowed' : 'denied'"
  }

  # Reject tokens from any other repository, including forks and renamed lookalikes.
  attribute_condition = local.provider_condition

  lifecycle {
    precondition {
      # Policy values are embedded in CEL string literals.
      condition = alltrue([
        for value in local.policy_value : length(regexall("['\\\\]", value)) == 0
      ]) && alltrue([for claim in local.policy_claim : can(regex("^[a-z_]+$", claim))])
      error_message = "OIDC policy claims must be lowercase names and values must not contain quotes or backslashes."
    }
  }
}

resource "google_service_account" "ci_builder" {
  account_id   = "ci-builder"
  display_name = "CI image builder"
  description  = "Publishes images from the main-branch image workflow on push; no deployment or secret access"

  depends_on = [google_project_service.bootstrap]
}

# Write access to this one repository only, not project-wide Artifact Registry roles.
resource "google_artifact_registry_repository_iam_member" "builder_writer" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.ci_builder.member
}

# Only push events running the image workflow from main map to 'allowed'.
# pull_request, pull_request_target (which also reports refs/heads/main),
# workflow_dispatch and other workflows map to 'denied'.
resource "google_service_account_iam_member" "builder_federation" {
  service_account_id = google_service_account.ci_builder.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.image_builder/allowed"
}
