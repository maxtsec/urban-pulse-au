output "archive_bucket" { value = google_storage_bucket.archive.name }
output "archive_service_account" { value = google_service_account.archive.email }
output "scheduler_service_account" { value = google_service_account.scheduler.email }
output "job_name" { value = google_cloud_run_v2_job.archive.name }
output "last_success_query" { value = local.success_query }
