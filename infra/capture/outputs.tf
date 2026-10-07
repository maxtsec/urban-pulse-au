output "landing_bucket" {
  value = google_storage_bucket.landing.name
}
output "collector_service_account" {
  value = google_service_account.collector.email
}
output "metric_types" {
  value = { for key, metric in google_monitoring_metric_descriptor.collector : key => metric.type }
}
output "monitored_resource" {
  value = {
    type = "generic_task"
    labels = {
      project_id = var.project_id
      location   = "australia-southeast2"
      namespace  = "urbanpulse"
      job        = "capture"
      task_id    = var.collector_id
    }
  }
}
output "alert_groups" {
  value = var.alert_groups
}
