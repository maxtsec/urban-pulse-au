variable "project_id" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use the existing project ID."
  }
}
variable "archive_bucket" {
  type        = string
  description = "New isolated bucket, never the home collector landing bucket."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,60}[a-z0-9]$", var.archive_bucket))
    error_message = "Use a globally unique lowercase bucket name without dots."
  }
}
variable "api_image" {
  type = string
  validation {
    condition     = can(regex("^australia-southeast2-docker\\.pkg\\.dev/${var.project_id}/[a-z0-9-]+/api@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "Pin the reviewed same-project API image by digest."
  }
}
variable "source_sha" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.source_sha))
    error_message = "Use the image's full reviewed source commit."
  }
}
variable "schedule_enabled" {
  type    = bool
  default = false
}
variable "acceptance_complete" {
  type        = bool
  default     = false
  description = "True only after saved-plan, identity, seed, bounded cloud execution and notification acceptance."
}
variable "alerts_enabled" {
  type    = bool
  default = false
}
variable "alerts_enrolled" {
  type        = bool
  default     = false
  description = "Actual sparse daily query and notification cases verified, not merely mocked plans."
}
variable "alert_not_before" {
  type        = number
  default     = 0
  description = "Reviewed Unix second when missing-success evaluation begins, after first-run grace."
  validation {
    condition     = var.alert_not_before >= 0 && floor(var.alert_not_before) == var.alert_not_before
    error_message = "Use an integer Unix second."
  }
}
variable "notification_channels" {
  type    = list(string)
  default = []
  validation {
    condition     = alltrue([for channel in var.notification_channels : can(regex("^projects/${var.project_id}/notificationChannels/[0-9]+$", channel))])
    error_message = "Use verified same-project notification channel IDs."
  }
}
