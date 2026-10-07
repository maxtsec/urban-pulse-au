# Storage/IAM APIs belong to the existing bootstrap/delivery roots.
# Monitoring is enabled here; never disable a shared API on teardown.
resource "google_project_service" "monitoring" {
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "landing" {
  name                        = var.landing_bucket
  location                    = "AUSTRALIA-SOUTHEAST2"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  deletion_policy             = "PREVENT"
  versioning { enabled = false }
  soft_delete_policy { retention_duration_seconds = 604800 }
  labels = { application = "urbanpulse", purpose = "normalized-capture" }

  # No blanket age deletion: retained lineage/static references need an expiry design.
  lifecycle { prevent_destroy = true }
}

resource "google_service_account" "collector" {
  account_id   = "urbanpulse-collector"
  display_name = "UrbanPulse collector upload and telemetry"
  lifecycle { prevent_destroy = true }
}

resource "google_project_iam_custom_role" "known_object" {
  role_id     = "urbanpulseCaptureObjectGet"
  title       = "UrbanPulse known landing object read"
  description = "Known-name metadata/content read; no list, overwrite or delete."
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket_iam_member" "create" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectCreator"
  member = google_service_account.collector.member
}

resource "google_storage_bucket_iam_member" "known_object" {
  bucket = google_storage_bucket.landing.name
  role   = google_project_iam_custom_role.known_object.name
  member = google_service_account.collector.member
}

# Architect-approved amendment: this additional permission is project-scoped.
# IAM cannot constrain it to just the descriptors or resource labels below.
resource "google_project_iam_custom_role" "telemetry" {
  role_id     = "urbanpulseCaptureTelemetryWrite"
  title       = "UrbanPulse collector time-series write"
  permissions = ["monitoring.timeSeries.create"]
}

resource "google_project_iam_member" "telemetry" {
  project    = var.project_id
  role       = google_project_iam_custom_role.telemetry.name
  member     = google_service_account.collector.member
  depends_on = [google_project_service.monitoring]
}
