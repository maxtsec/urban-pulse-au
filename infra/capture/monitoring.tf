locals {
  metric_prefix = "custom.googleapis.com/urbanpulse/collector/v1"
  descriptors = {
    heartbeat                  = { unit = "1", feed = false, description = "1 only when the collection loop emits a current live pulse; not source health." }
    capture_age_seconds        = { unit = "s", feed = true, description = "Elapsed seconds since the latest durably successful live capture of this feed; omit when unknown." }
    capture_success_known      = { unit = "1", feed = true, description = "1 if a durable live success timestamp exists for this feed, otherwise 0; never infer success from process liveness." }
    upload_age_seconds         = { unit = "s", feed = false, description = "Elapsed seconds since the last durable generation/checksum-validated landing confirmation; omit when unknown." }
    upload_pending_age_seconds = { unit = "s", feed = false, description = "Age of the oldest required unconfirmed upload; 0 only when the durable queue is known empty, omitted when queue state is unknown." }
    upload_success_known       = { unit = "1", feed = false, description = "1 if a durable landing upload confirmation exists, otherwise 0." }
    free_bytes                 = { unit = "By", feed = false, description = "Filesystem bytes available to the unprivileged collector on the mounted data volume." }
    free_inodes                = { unit = "1", feed = false, description = "Filesystem inodes available to the unprivileged collector on the mounted data volume." }
  }
  resource_filter = join(" AND ", [
    "resource.type = \"generic_task\"",
    "resource.labels.project_id = \"${var.project_id}\"",
    "resource.labels.location = \"australia-southeast2\"",
    "resource.labels.namespace = \"urbanpulse\"",
    "resource.labels.job = \"capture\"",
    "resource.labels.task_id = \"${var.collector_id}\"",
  ])
  rules = merge({
    for feed, age in var.alert_limits.capture_age_seconds : "capture-${feed}" => {
      group      = "capture", metric = "capture_age_seconds", known = "capture_success_known", threshold = age,
      comparison = "COMPARISON_GT", feed_filter = " AND metric.labels.feed = \"${feed}\""
    }
    }, {
    upload = { group = "upload", metric = "upload_age_seconds", known = "upload_success_known", threshold = var.alert_limits.upload_age_seconds, comparison = "COMPARISON_GT", feed_filter = "" }
    bytes  = { group = "capacity", metric = "free_bytes", known = null, threshold = var.alert_limits.free_bytes, comparison = "COMPARISON_LT", feed_filter = "" }
    inodes = { group = "capacity", metric = "free_inodes", known = null, threshold = var.alert_limits.free_inodes, comparison = "COMPARISON_LT", feed_filter = "" }
  })
}

resource "google_monitoring_metric_descriptor" "collector" {
  for_each     = local.descriptors
  type         = "${local.metric_prefix}/${each.key}"
  display_name = "Collector ${each.key}"
  description  = each.value.description
  metric_kind  = "GAUGE"
  value_type   = "INT64"
  unit         = each.value.unit
  dynamic "labels" {
    for_each = each.value.feed ? [true] : []
    content {
      key         = "feed"
      value_type  = "STRING"
      description = "Exactly vehicle-positions, trip-updates or service-alerts."
    }
  }
  depends_on = [google_project_service.monitoring]
  lifecycle { prevent_destroy = true }
}

resource "google_monitoring_alert_policy" "heartbeat" {
  display_name          = "Collector heartbeat missing"
  enabled               = var.alert_groups.heartbeat.enabled
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "No current collector pulse"
    condition_absent {
      filter   = "${local.resource_filter} AND metric.type = \"${google_monitoring_metric_descriptor.collector["heartbeat"].type}\""
      duration = "${var.alert_limits.absence_seconds}s"
      trigger { count = 1 }
    }
  }
  documentation {
    mime_type = "text/markdown"
    content   = "Inspect host power/network, Docker, manual unlock and reserve refusal. Missing pulses are an outage, not proof of a particular cause. Follow docs/runbooks/capture-infrastructure.md."
  }
  lifecycle {
    precondition {
      condition     = !var.alert_groups.heartbeat.enabled || (var.alert_groups.heartbeat.enrolled && length(var.notification_channels) > 0)
      error_message = "Enroll this group and verify its expected streams/channels before enabling it."
    }
  }
}

resource "google_monitoring_alert_policy" "health" {
  for_each              = local.rules
  display_name          = "Collector ${each.key}"
  enabled               = var.alert_groups[each.value.group].enabled
  combiner              = "OR"
  notification_channels = var.notification_channels
  conditions {
    display_name = "${each.key} threshold"
    condition_threshold {
      filter                  = "${local.resource_filter} AND metric.type = \"${google_monitoring_metric_descriptor.collector[each.value.metric].type}\"${each.value.feed_filter}"
      comparison              = each.value.comparison
      threshold_value         = each.value.threshold
      duration                = "${var.alert_limits.sustained_seconds}s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = each.value.comparison == "COMPARISON_LT" ? "ALIGN_MIN" : "ALIGN_MAX"
      }
      trigger { count = 1 }
    }
  }
  dynamic "conditions" {
    for_each = each.value.known == null ? [] : [each.value.known]
    content {
      display_name = "${each.key} success unknown"
      condition_threshold {
        filter                  = "${local.resource_filter} AND metric.type = \"${google_monitoring_metric_descriptor.collector[conditions.value].type}\"${each.value.feed_filter}"
        comparison              = "COMPARISON_LT"
        threshold_value         = 1
        duration                = "${var.alert_limits.sustained_seconds}s"
        evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
        aggregations {
          alignment_period   = "60s"
          per_series_aligner = "ALIGN_MIN"
        }
        trigger { count = 1 }
      }
    }
  }
  dynamic "conditions" {
    for_each = each.key == "upload" ? [true] : []
    content {
      display_name = "Oldest upload remains unconfirmed"
      condition_threshold {
        filter                  = "${local.resource_filter} AND metric.type = \"${google_monitoring_metric_descriptor.collector["upload_pending_age_seconds"].type}\""
        comparison              = "COMPARISON_GT"
        threshold_value         = var.alert_limits.upload_age_seconds
        duration                = "${var.alert_limits.sustained_seconds}s"
        evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
        aggregations {
          alignment_period   = "60s"
          per_series_aligner = "ALIGN_MAX"
        }
        trigger { count = 1 }
      }
    }
  }
  documentation {
    mime_type = "text/markdown"
    content   = "Investigate source failures, normalization/upload backlog, missing telemetry or local capacity. Do not delete pinned raw or manufacture success to clear an alert. Follow docs/runbooks/capture-infrastructure.md."
  }
  lifecycle {
    precondition {
      condition     = !var.alert_groups[each.value.group].enabled || (var.alert_groups[each.value.group].enrolled && length(var.notification_channels) > 0)
      error_message = "Enroll this group and verify its expected streams/channels before enabling it."
    }
  }
}
