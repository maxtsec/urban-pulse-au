variable "project_id" {
  description = "Google Cloud project ID (not the display name)."
  type        = string
}

variable "region" {
  description = "Region for the Artifact Registry repository."
  type        = string
  default     = "australia-southeast2"
}

variable "artifact_repository_id" {
  description = "Existing Docker repository adopted into Terraform state."
  type        = string
  default     = "urbanpulse"
}

# Numeric IDs do not change when a repository or owner is renamed, so a later
# repository with the same name cannot inherit this trust.
variable "github_repository_id" {
  description = "Numeric GitHub ID of maxtsec/urban-pulse-au."
  type        = string
  default     = "1404249334"
}

variable "github_owner_id" {
  description = "Numeric GitHub ID of the repository owner."
  type        = string
  default     = "98444048"
}

variable "builder_ref" {
  description = "Only workflows running on this Git ref may publish images."
  type        = string
  default     = "refs/heads/main"
}
