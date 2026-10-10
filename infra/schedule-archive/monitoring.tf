locals {
  job_filter = "resource.type = \"cloud_run_job\" AND resource.labels.project_id = \"${var.project_id}\" AND resource.labels.location = \"australia-southeast2\" AND resource.labels.job_name = \"${google_cloud_run_v2_job.archive.name}\""
  # Positive samples only: zero-filled log-counter samples must not hide a missed day.
  # Candidate query; sparse-series behavior must be measured before enrollment.
  success_query = "((max(max_over_time({__name__=\"logging.googleapis.com/user/${google_logging_metric.success.name}\",monitored_resource=\"cloud_run_job\",project_id=\"${var.project_id}\",location=\"australia-southeast2\",job_name=\"${google_cloud_run_v2_job.archive.name}\"}[24h30m])) or vector(0)) < 1) and on() (vector(time()) >= ${var.alert_not_before})"
}
resource "google_logging_metric" "success" {
  name        = "urbanpulse_gtfs_archive_complete"
  filter      = "${local.job_filter} AND jsonPayload.status = \"complete\" AND jsonPayload.kind = \"gtfs_archive_success\""
  description = "Count of complete acknowledged daily static archives, excluding historical seeds and inspections."
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}
resource "google_monitoring_alert_policy" "failed" {
  display_name          = "GTFS archive execution failed"
  enabled               = var.alerts_enabled
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "Failed bounded execution"
    condition_threshold {
      filter          = "${local.job_filter} AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
      trigger { count = 1 }
    }
  }
  documentation {
    mime_type = "text/markdown"
    content   = "Inspect this Job execution and its incomplete manifest. Do not overwrite archives or count a seed as a daily success. Follow docs/runbooks/gtfs-archive-deployment.md."
  }
  lifecycle {
    precondition {
      condition     = !var.alerts_enabled || (var.alerts_enrolled && var.alert_not_before > 0 && length(var.notification_channels) > 0)
      error_message = "Review grace, verify real queries and channels before alert enrollment."
    }
  }
}
resource "google_monitoring_alert_policy" "last_success" {
  display_name          = "GTFS archive daily success missing"
  enabled               = var.alerts_enabled
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "No positive complete check within daily window"
    condition_prometheus_query_language {
      query               = local.success_query
      duration            = "0s"
      evaluation_interval = "300s"
    }
  }
  documentation {
    mime_type = "text/markdown"
    content   = "Check Scheduler, failed or stalled Job, incomplete manifests and log ingestion. Historical seeds do not clear this condition. A paused schedule requires a reviewed snooze; this policy deliberately still detects missed checks."
  }
  depends_on = [google_logging_metric.success, google_monitoring_alert_policy.failed]
}
