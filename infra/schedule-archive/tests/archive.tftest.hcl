mock_provider "google" {
  override_during = plan
  override_resource {
    target = google_service_account.archive
    values = {
      email  = "urbanpulse-gtfs-archive@example-project.iam.gserviceaccount.com"
      member = "serviceAccount:urbanpulse-gtfs-archive@example-project.iam.gserviceaccount.com"
    }
  }
  override_resource {
    target = google_service_account.scheduler
    values = {
      email  = "urbanpulse-gtfs-scheduler@example-project.iam.gserviceaccount.com"
      member = "serviceAccount:urbanpulse-gtfs-scheduler@example-project.iam.gserviceaccount.com"
    }
  }
  override_resource {
    target = google_project_iam_custom_role.archive
    values = { name = "projects/example-project/roles/urbanpulseStaticArchive" }
  }
}
variables {
  project_id     = "example-project"
  archive_bucket = "example-project-static-archive"
  api_image      = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  source_sha     = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
run "isolated_and_dormant" {
  command = plan
  assert {
    condition = (
      google_storage_bucket.archive.public_access_prevention == "enforced" &&
      google_storage_bucket.archive.uniform_bucket_level_access &&
      !google_storage_bucket.archive.force_destroy && google_storage_bucket.archive.deletion_policy == "PREVENT" &&
      google_storage_bucket.archive.location == "AUSTRALIA-SOUTHEAST2" &&
      length(google_storage_bucket.archive.lifecycle_rule) == 0 &&
      google_storage_bucket_iam_member.archive.member == google_service_account.archive.member &&
      google_project_iam_custom_role.archive.permissions == toset(["storage.objects.create", "storage.objects.get"]) &&
      google_storage_bucket_iam_member.archive.condition[0].expression == "resource.name.startsWith('projects/_/buckets/example-project-static-archive/objects/static/gtfs-tram/')"
    )
    error_message = "Keep archives private, preserved and prefix scoped without list, delete or broader roles."
  }
  assert {
    condition = (
      google_cloud_run_v2_job.archive.template[0].template[0].service_account == google_service_account.archive.email &&
      google_cloud_run_v2_job.archive.template[0].task_count == 1 && google_cloud_run_v2_job.archive.template[0].parallelism == 1 &&
      google_cloud_run_v2_job.archive.template[0].template[0].max_retries == 0 &&
      google_cloud_run_v2_job.archive.template[0].template[0].timeout == "900s" &&
      google_cloud_run_v2_job.archive.template[0].template[0].containers[0].resources[0].limits == tomap({ cpu = "1", memory = "2Gi" }) &&
      length(google_cloud_run_v2_job.archive.template[0].template[0].volumes) == 0 &&
      length(google_cloud_run_v2_job.archive.template[0].template[0].containers[0].env) == 0 &&
      google_cloud_run_v2_job.archive.run_execution_token == null && google_cloud_run_v2_job.archive.start_execution_token == null &&
      google_cloud_run_v2_job.archive.template[0].template[0].containers[0].args == tolist([
        "-m", "workers.schedule_archive.main", "check", "--bucket", var.archive_bucket,
        "--expected-service-account", google_service_account.archive.email, "--code-version", var.source_sha,
        "--timeout-seconds", "540"
      ])
    )
    error_message = "Use the bounded metadata-only check without SQL, secrets, seed arguments or apply-time execution."
  }
  assert {
    condition = (
      google_cloud_scheduler_job.archive.paused && !google_monitoring_alert_policy.failed.enabled && !google_monitoring_alert_policy.last_success.enabled &&
      google_cloud_scheduler_job.archive.schedule == "0 18 * * *" && google_cloud_scheduler_job.archive.time_zone == "Etc/UTC" &&
      google_cloud_scheduler_job.archive.retry_config[0].retry_count == 0 &&
      google_cloud_run_v2_job_iam_member.invoke.role == "roles/run.invoker" &&
      google_cloud_run_v2_job_iam_member.invoke.member == google_service_account.scheduler.member &&
      google_cloud_run_v2_job_iam_member.invoke.name == google_cloud_run_v2_job.archive.name &&
      google_cloud_scheduler_job.archive.http_target[0].oauth_token[0].service_account_email == google_service_account.scheduler.email &&
      base64decode(google_cloud_scheduler_job.archive.http_target[0].body) == "{}"
    )
    error_message = "Apply creates no captures or notifications; Scheduler must have only the specific Job invocation grant."
  }
  assert {
    condition = (
      strcontains(google_logging_metric.success.filter, "gtfs_archive_success") &&
      strcontains(local.success_query, "[24h30m]") && strcontains(local.success_query, "or vector(0)") &&
      strcontains(local.success_query, "< 1") &&
      google_monitoring_alert_policy.last_success.conditions[0].condition_prometheus_query_language[0].evaluation_interval == "300s" &&
      google_monitoring_alert_policy.last_success.conditions[0].condition_prometheus_query_language[0].duration == "0s"
    )
    error_message = "Keep daily success distinct from seeds, zero fills and missing series; use a bounded candidate query."
  }
}
run "reject_unaccepted_schedule" {
  command = plan
  variables { schedule_enabled = true }
  expect_failures = [google_cloud_scheduler_job.archive]
}
run "reject_unenrolled_alerts" {
  command = plan
  variables { alerts_enabled = true }
  expect_failures = [google_monitoring_alert_policy.failed]
}
run "reject_missing_grace" {
  command = plan
  variables {
    alerts_enabled        = true
    alerts_enrolled       = true
    notification_channels = ["projects/example-project/notificationChannels/123"]
  }
  expect_failures = [google_monitoring_alert_policy.failed]
}
run "accepted_enrollment" {
  command = plan
  variables {
    acceptance_complete   = true
    schedule_enabled      = true
    alerts_enabled        = true
    alerts_enrolled       = true
    notification_channels = ["projects/example-project/notificationChannels/123"]
    alert_not_before      = 1791583200
  }
  assert {
    condition     = !google_cloud_scheduler_job.archive.paused && google_monitoring_alert_policy.last_success.enabled
    error_message = "Reviewed acceptance can activate this source independently."
  }
}
run "reject_tag" {
  command = plan
  variables { api_image = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/api:main" }
  expect_failures = [var.api_image]
}
run "reject_foreign_image" {
  command = plan
  variables { api_image = "australia-southeast2-docker.pkg.dev/another-project/urbanpulse/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [var.api_image]
}
run "reject_short_sha" {
  command = plan
  variables { source_sha = "abcd" }
  expect_failures = [var.source_sha]
}
run "reject_foreign_notification" {
  command = plan
  variables { notification_channels = ["projects/another-project/notificationChannels/123"] }
  expect_failures = [var.notification_channels]
}
