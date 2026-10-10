# Existing roots own Run, IAM, Storage, Logging and Monitoring API activation.
# No shared API is disabled or re-owned here.
resource "google_project_service" "scheduler" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}
resource "google_storage_bucket" "archive" {
  name                        = var.archive_bucket
  location                    = "AUSTRALIA-SOUTHEAST2"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  deletion_policy             = "PREVENT"
  versioning { enabled = false }
  soft_delete_policy { retention_duration_seconds = 604800 }
  labels = { application = "urbanpulse", purpose = "static-archive" }
  # Timetables are lineage inputs; no automatic age deletion.
  lifecycle { prevent_destroy = true }
}
resource "google_service_account" "archive" {
  account_id   = "urbanpulse-gtfs-archive"
  display_name = "UrbanPulse static tram archive"
  lifecycle { prevent_destroy = true }
}
resource "google_service_account" "scheduler" {
  account_id   = "urbanpulse-gtfs-scheduler"
  display_name = "UrbanPulse static archive scheduler"
}
resource "google_project_iam_custom_role" "archive" {
  role_id     = "urbanpulseStaticArchive"
  title       = "UrbanPulse static archive create and known-object read"
  permissions = ["storage.objects.create", "storage.objects.get"]
}
resource "google_storage_bucket_iam_member" "archive" {
  bucket = google_storage_bucket.archive.name
  role   = google_project_iam_custom_role.archive.name
  member = google_service_account.archive.member
  condition {
    title      = "static-tram-only"
    expression = "resource.name.startsWith('projects/_/buckets/${google_storage_bucket.archive.name}/objects/static/gtfs-tram/')"
  }
}
resource "google_cloud_run_v2_job" "archive" {
  name                = "urbanpulse-gtfs-archive"
  location            = "australia-southeast2"
  deletion_protection = true
  labels              = { application = "urbanpulse", "source-sha" = var.source_sha }
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account       = google_service_account.archive.email
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
      timeout               = "900s"
      max_retries           = 0
      containers {
        image   = var.api_image
        command = ["/app/.venv/bin/python"]
        args = ["-m", "workers.schedule_archive.main", "check", "--bucket", google_storage_bucket.archive.name,
          "--expected-service-account", google_service_account.archive.email, "--code-version", var.source_sha,
        "--timeout-seconds", "540"]
        resources { limits = { cpu = "1", memory = "2Gi" } }
      }
    }
  }
  depends_on = [google_storage_bucket_iam_member.archive]
}
resource "google_cloud_run_v2_job_iam_member" "invoke" {
  project  = var.project_id
  location = google_cloud_run_v2_job.archive.location
  name     = google_cloud_run_v2_job.archive.name
  role     = "roles/run.invoker"
  member   = google_service_account.scheduler.member
}
resource "google_cloud_scheduler_job" "archive" {
  name   = "urbanpulse-gtfs-archive-daily"
  region = "australia-southeast2"
  # UTC avoids the 25-hour gap on the Melbourne daylight-saving fallback day.
  schedule         = "0 18 * * *"
  time_zone        = "Etc/UTC"
  paused           = !var.schedule_enabled
  attempt_deadline = "60s"
  retry_config { retry_count = 0 }
  http_target {
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/australia-southeast2/jobs/${google_cloud_run_v2_job.archive.name}:run"
    http_method = "POST"
    body        = base64encode("{}")
    headers     = { "Content-Type" = "application/json" }
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  depends_on = [google_project_service.scheduler, google_cloud_run_v2_job_iam_member.invoke]
  lifecycle {
    precondition {
      condition     = !var.schedule_enabled || (var.acceptance_complete && var.alerts_enabled && var.alerts_enrolled)
      error_message = "Accept finite cloud runs and enroll alerts before enabling daily capture."
    }
  }
}
