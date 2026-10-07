# Synthetic limits below are test inputs, never approved production thresholds.
mock_provider "google" {
  override_during = plan
}
override_resource {
  target          = google_service_account.collector
  override_during = plan
  values = {
    member = "serviceAccount:urbanpulse-collector@fixture-project.iam.gserviceaccount.com"
    email  = "urbanpulse-collector@fixture-project.iam.gserviceaccount.com"
  }
}
override_resource {
  target          = google_project_iam_custom_role.known_object
  override_during = plan
  values          = { name = "projects/fixture-project/roles/urbanpulseCaptureObjectGet" }
}
override_resource {
  target          = google_project_iam_custom_role.telemetry
  override_during = plan
  values          = { name = "projects/fixture-project/roles/urbanpulseCaptureTelemetryWrite" }
}
variables {
  project_id     = "fixture-project"
  landing_bucket = "fixture-project-capture-landing"
  collector_id   = "fixture-primary"
  alert_limits = {
    absence_seconds     = 600
    sustained_seconds   = 120
    capture_age_seconds = { vehicle-positions = 600, trip-updates = 900, service-alerts = 600 }
    upload_age_seconds  = 1800
    free_bytes          = 1073741824
    free_inodes         = 20000
  }
}

run "private_non_destructive_landing" {
  command = plan
  assert {
    condition = (
      google_storage_bucket.landing.location == "AUSTRALIA-SOUTHEAST2" &&
      google_storage_bucket.landing.storage_class == "STANDARD" &&
      google_storage_bucket.landing.uniform_bucket_level_access &&
      google_storage_bucket.landing.public_access_prevention == "enforced" &&
      !google_storage_bucket.landing.force_destroy &&
      google_storage_bucket.landing.deletion_policy == "PREVENT" &&
      !google_storage_bucket.landing.versioning[0].enabled &&
      google_storage_bucket.landing.soft_delete_policy[0].retention_duration_seconds == 604800 &&
      length(google_storage_bucket.landing.lifecycle_rule) == 0
    )
    error_message = "Landing must be private, regional and protected, with no blanket expiry."
  }
}

run "minimal_storage_and_metrics_permissions" {
  command = plan
  assert {
    condition = (
      toset(google_project_iam_custom_role.known_object.permissions) == toset(["storage.objects.get"]) &&
      google_storage_bucket_iam_member.create.role == "roles/storage.objectCreator" &&
      google_storage_bucket_iam_member.create.bucket == google_storage_bucket.landing.name &&
      google_storage_bucket_iam_member.known_object.bucket == google_storage_bucket.landing.name &&
      google_storage_bucket_iam_member.known_object.role == google_project_iam_custom_role.known_object.name &&
      google_storage_bucket_iam_member.create.member == google_service_account.collector.member &&
      google_storage_bucket_iam_member.known_object.member == google_service_account.collector.member &&
      toset(google_project_iam_custom_role.telemetry.permissions) == toset(["monitoring.timeSeries.create"]) &&
      google_project_iam_member.telemetry.member == google_service_account.collector.member &&
      google_project_iam_member.telemetry.role == google_project_iam_custom_role.telemetry.name
    )
    error_message = "Exactly the accepted create/get and timeSeries.create grants may reach the collector."
  }
}

run "disabled_until_enrolled" {
  command = plan
  assert {
    condition = !google_monitoring_alert_policy.heartbeat.enabled && alltrue([
      for policy in google_monitoring_alert_policy.health : !policy.enabled
    ])
    error_message = "Creating resources must not claim a working or enabled alert pipeline."
  }
  assert {
    condition = (
      length(google_monitoring_metric_descriptor.collector) == 8 &&
      alltrue([for metric in google_monitoring_metric_descriptor.collector :
        metric.metric_kind == "GAUGE" && metric.value_type == "INT64"
      ]) &&
      toset(keys(google_monitoring_alert_policy.health)) == toset([
        "capture-vehicle-positions", "capture-trip-updates", "capture-service-alerts", "upload", "bytes", "inodes"
      ])
    )
    error_message = "Every feed, upload backlog, capacity and liveness signal must be represented."
  }
}

run "enrolled_alert_filters_and_unknown_states" {
  command = plan
  variables {
    alert_groups          = { for group in ["heartbeat", "capture", "capacity", "upload"] : group => { enabled = true, enrolled = true } }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  assert {
    condition = (
      google_monitoring_alert_policy.heartbeat.enabled &&
      google_monitoring_alert_policy.heartbeat.conditions[0].condition_absent[0].duration == "600s" &&
      alltrue([for policy in google_monitoring_alert_policy.health :
        policy.enabled && policy.combiner == "OR" &&
        policy.notification_channels == var.notification_channels &&
        alltrue([for condition in policy.conditions :
          strcontains(condition.condition_threshold[0].filter, "resource.type = \"generic_task\"") &&
          strcontains(condition.condition_threshold[0].filter, "resource.labels.task_id = \"fixture-primary\"") &&
          condition.condition_threshold[0].evaluation_missing_data == "EVALUATION_MISSING_DATA_INACTIVE"
        ])
      ]) &&
      length(google_monitoring_alert_policy.health["upload"].conditions) == 3 &&
      anytrue([for condition in google_monitoring_alert_policy.health["upload"].conditions :
        strcontains(condition.condition_threshold[0].filter, "upload_pending_age_seconds") &&
        condition.condition_threshold[0].comparison == "COMPARISON_GT" &&
        condition.condition_threshold[0].threshold_value == var.alert_limits.upload_age_seconds
      ]) &&
      length(google_monitoring_alert_policy.health["capture-trip-updates"].conditions) == 2 &&
      anytrue([for condition in google_monitoring_alert_policy.health["capture-trip-updates"].conditions :
        strcontains(condition.condition_threshold[0].filter, "capture_success_known") &&
        condition.condition_threshold[0].comparison == "COMPARISON_LT"
      ]) &&
      alltrue([for condition in google_monitoring_alert_policy.health["capture-trip-updates"].conditions :
        strcontains(condition.condition_threshold[0].filter, "metric.labels.feed = \"trip-updates\"")
      ])
    )
    error_message = "Alerts must target the stable collector/feed, handle unknown success and detect stalled pending uploads."
  }
}

run "reject_enable_without_enrollment" {
  command = plan
  variables {
    alert_groups          = { for group in ["heartbeat", "capture", "capacity", "upload"] : group => { enabled = true } }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  expect_failures = [google_monitoring_alert_policy.heartbeat, google_monitoring_alert_policy.health]
}
run "reject_enable_without_channel" {
  command = plan
  variables {
    alert_groups = { for group in ["heartbeat", "capture", "capacity", "upload"] : group => { enabled = true, enrolled = true } }
  }
  expect_failures = [google_monitoring_alert_policy.heartbeat, google_monitoring_alert_policy.health]
}
run "reject_foreign_channel" {
  command = plan
  variables { notification_channels = ["projects/another-project/notificationChannels/12345"] }
  expect_failures = [var.notification_channels]
}
run "reject_filter_injection" {
  command = plan
  variables { collector_id = "bad-alias OR true" }
  expect_failures = [var.collector_id]
}
run "reject_reserve_warning_below_stop" {
  command = plan
  variables {
    alert_limits = {
      absence_seconds     = 600, sustained_seconds = 120,
      capture_age_seconds = { vehicle-positions = 600, trip-updates = 900, service-alerts = 600 },
      upload_age_seconds  = 1800, free_bytes = 100, free_inodes = 20000
    }
  }
  expect_failures = [var.alert_limits]
}
run "reject_missing_feed_and_fractional_absence" {
  command = plan
  variables {
    alert_limits = {
      absence_seconds     = 61.5, sustained_seconds = 120,
      capture_age_seconds = { vehicle-positions = 600 },
      upload_age_seconds  = 1800, free_bytes = 1073741824, free_inodes = 20000
    }
  }
  expect_failures = [var.alert_limits]
}


run "raw_only_without_upload_enrollment" {
  command = plan
  variables {
    alert_groups = {
      heartbeat = { enabled = true, enrolled = true }
      capture   = { enabled = true, enrolled = true }
      capacity  = { enabled = true, enrolled = true }
    }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  assert {
    condition = (
      google_monitoring_alert_policy.heartbeat.enabled &&
      alltrue([for key, policy in google_monitoring_alert_policy.health : key == "upload" ? !policy.enabled : policy.enabled]) &&
      !var.alert_groups.upload.enrolled
    )
    error_message = "Raw capture must have heartbeat/feed/capacity alerts without an uploader or upload enrollment."
  }
}

run "heartbeat_only_enrollment" {
  command = plan
  variables {
    alert_groups          = { heartbeat = { enabled = true, enrolled = true } }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  assert {
    condition = google_monitoring_alert_policy.heartbeat.enabled && alltrue([
      for policy in google_monitoring_alert_policy.health : !policy.enabled
    ])
    error_message = "Heartbeat enrollment must not enable health groups."
  }
}

run "reject_upload_using_raw_enrollment" {
  command = plan
  variables {
    alert_groups = {
      heartbeat = { enabled = true, enrolled = true }
      capture   = { enabled = true, enrolled = true }
      capacity  = { enabled = true, enrolled = true }
      upload    = { enabled = true }
    }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  expect_failures = [google_monitoring_alert_policy.health["upload"]]
}

run "reject_capture_using_other_enrollment" {
  command = plan
  variables {
    alert_groups = {
      heartbeat = { enabled = true, enrolled = true }
      capture   = { enabled = true }
      capacity  = { enrolled = true }
      upload    = { enrolled = true }
    }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  expect_failures = [google_monitoring_alert_policy.health]
}

run "reject_capacity_using_other_enrollment" {
  command = plan
  variables {
    alert_groups = {
      heartbeat = { enabled = true, enrolled = true }
      capture   = { enrolled = true }
      capacity  = { enabled = true }
      upload    = { enrolled = true }
    }
    notification_channels = ["projects/fixture-project/notificationChannels/12345"]
  }
  expect_failures = [google_monitoring_alert_policy.health]
}
