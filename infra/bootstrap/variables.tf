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

# GitHub repository/owner IDs and the image-builder claims live in
# github-oidc-policy.json so Terraform and its unit test share one definition.
