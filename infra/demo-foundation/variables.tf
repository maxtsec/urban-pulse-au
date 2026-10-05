variable "project_id" {
  description = "Existing project containing the reviewed image/bootstrap resources."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a Google Cloud project ID, not a display name."
  }
}

variable "name_prefix" {
  description = "Stable demo resource names; changing this can require replacement."
  type        = string
  default     = "urbanpulse-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,15}$", var.name_prefix))
    error_message = "Use 5-16 lowercase letters, digits or hyphens, starting with a letter."
  }
}
