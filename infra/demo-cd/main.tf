resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "delivery" {
  depends_on                  = [google_project_service.storage]
  name                        = var.state_bucket
  location                    = "AUSTRALIA-SOUTHEAST2"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning { enabled = true }
  lifecycle { prevent_destroy = true }
}

# Independent trust configuration: leave the existing image-builder policy untouched.
resource "google_iam_workload_identity_pool" "delivery" {
  workload_identity_pool_id = "github-deploy"
  display_name              = "UrbanPulse deployment"
}
resource "google_iam_workload_identity_pool_provider" "delivery" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.delivery.workload_identity_pool_id
  workload_identity_pool_provider_id = "managed-demo"
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.repository_id" = "assertion.repository_id"
  }
  attribute_condition = <<-CEL
    assertion.repository_id == '1404249334' &&
    assertion.repository_owner_id == '98444048' &&
    assertion.ref == 'refs/heads/main' &&
    assertion.workflow_ref == 'maxtsec/urban-pulse-au/.github/workflows/cd.yml@refs/heads/main' &&
    assertion.job_workflow_ref == 'maxtsec/urban-pulse-au/.github/workflows/deploy.yml@refs/heads/main' &&
    ((assertion.event_name == 'workflow_run' && assertion.environment == 'demo-candidate') ||
     (assertion.event_name == 'workflow_dispatch' && assertion.environment == 'demo-promotion'))
  CEL
}
resource "google_service_account" "deployer" {
  account_id   = "ci-demo-deployer"
  display_name = "Managed demo deployer"
}
resource "google_service_account_iam_member" "federation" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.delivery.name}/attribute.repository_id/1404249334"
}
resource "google_storage_bucket_iam_member" "state" {
  bucket = google_storage_bucket.delivery.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.deployer.member
}
resource "google_artifact_registry_repository_iam_member" "images" {
  location   = "australia-southeast2"
  repository = "urbanpulse"
  role       = "roles/artifactregistry.reader"
  member     = google_service_account.deployer.member
}
resource "google_service_account_iam_member" "runtime" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.runtime_service_account}"
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
resource "google_project_iam_custom_role" "service" {
  role_id = "urbanpulseDemoServiceDeployer"
  title   = "UrbanPulse existing service deployer"
  permissions = [
    "run.services.get", "run.services.update", "run.services.getIamPolicy",
    "run.revisions.get", "run.revisions.list",
  ]
}
resource "google_cloud_run_v2_service_iam_member" "service" {
  project  = var.project_id
  location = "australia-southeast2"
  name     = var.service_name
  role     = google_project_iam_custom_role.service.name
  member   = google_service_account.deployer.member
}
resource "google_project_iam_custom_role" "metadata" {
  role_id = "urbanpulseDemoDeploymentMetadata"
  title   = "UrbanPulse deployment metadata reader"
  permissions = [
    "resourcemanager.projects.get", "run.operations.get",
    "iap.webServices.getIamPolicy", "serviceusage.services.use",
  ]
}
resource "google_project_iam_member" "metadata" {
  project = var.project_id
  role    = google_project_iam_custom_role.metadata.name
  member  = google_service_account.deployer.member
}
