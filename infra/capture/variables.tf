variable "project_id" {
  type        = string
  description = "Existing project; this root does not create billing or a project."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a project ID."
  }
}
variable "landing_bucket" {
  type        = string
  description = "Globally unique dedicated landing bucket, distinct from Terraform state."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.landing_bucket))
    error_message = "Use a 3-63 character lowercase bucket name without dots."
  }
}
variable "collector_id" {
  type        = string
  description = "Stable private logical alias, never a hostname, IP, session UUID or store UUID."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,31}$", var.collector_id))
    error_message = "Use a stable lowercase logical alias."
  }
}
variable "alerts_enabled" {
  type    = bool
  default = false
}
variable "monitoring_enrolled" {
  type        = bool
  default     = false
  description = "Operator attestation that expected streams and notification channels were verified."
}
variable "notification_channels" {
  type        = list(string)
  default     = []
  description = "Existing verified same-project channel names; identities/destinations remain private."
  validation {
    condition = alltrue([for channel in var.notification_channels :
      can(regex("^projects/${var.project_id}/notificationChannels/[0-9]+$", channel))
    ]) && length(distinct(var.notification_channels)) == length(var.notification_channels)
    error_message = "Use distinct full notification-channel names from this project."
  }
}
variable "alert_limits" {
  description = "Required private operator choices, with no production defaults. Test values are synthetic."
  nullable    = false
  type = object({
    absence_seconds     = number
    sustained_seconds   = number
    capture_age_seconds = map(number)
    upload_age_seconds  = number
    free_bytes          = number
    free_inodes         = number
  })
  validation {
    condition = (
      var.alert_limits.absence_seconds >= 120 && var.alert_limits.absence_seconds <= 84600 &&
      var.alert_limits.absence_seconds % 60 == 0 &&
      var.alert_limits.sustained_seconds >= 60 && var.alert_limits.sustained_seconds <= 84600 &&
      var.alert_limits.sustained_seconds % 60 == 0 &&
      toset(keys(var.alert_limits.capture_age_seconds)) == toset(["vehicle-positions", "trip-updates", "service-alerts"]) &&
      alltrue([for age in values(var.alert_limits.capture_age_seconds) : age >= 120 && age == floor(age)]) &&
      var.alert_limits.upload_age_seconds >= 120 && var.alert_limits.upload_age_seconds == floor(var.alert_limits.upload_age_seconds) &&
      var.alert_limits.free_bytes > (256 + 8) * 1024 * 1024 + 65536 && var.alert_limits.free_bytes == floor(var.alert_limits.free_bytes) &&
      var.alert_limits.free_inodes > 4128 && var.alert_limits.free_inodes == floor(var.alert_limits.free_inodes)
    )
    error_message = "Supply every feed and positive integer limits; durations must be whole minutes within Monitoring limits and capacity warnings above the default hard stop."
  }
}
