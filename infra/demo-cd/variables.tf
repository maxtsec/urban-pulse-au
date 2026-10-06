variable "project_id" { type = string }
variable "state_bucket" {
  type        = string
  description = "Dedicated private bucket for serving state and deployment records."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,61}[a-z0-9]$", var.state_bucket))
    error_message = "Use a valid dedicated bucket name."
  }
}
variable "service_name" {
  type    = string
  default = "urbanpulse-demo"
}
variable "runtime_service_account" {
  type        = string
  description = "Existing serving runtime identity; never a migration/import identity."
  validation {
    condition     = var.runtime_service_account == "${var.service_name}-runtime@${var.project_id}.iam.gserviceaccount.com"
    error_message = "Only the existing named serving runtime identity is allowed."
  }
}
