variable "project_id" {
  description = "Existing project containing the reviewed foundation and image repository."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use the existing Google Cloud project ID."
  }
}

variable "name_prefix" {
  type        = string
  description = "Stable Job names, independent of the foundation state."
  default     = "urbanpulse-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,15}$", var.name_prefix))
    error_message = "Use 5-16 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "foundation" {
  description = "Reviewed non-secret output values from demo-foundation; no remote state or secret data is read."
  type = object({
    database_connection_name = string
    database_name            = string
    identities               = map(string)
    database_secret_ids      = map(string)
  })
  validation {
    condition = (
      var.foundation.database_name == "urbanpulse" &&
      can(regex("^${var.project_id}:australia-southeast2:[a-z][a-z0-9-]+$", var.foundation.database_connection_name))
    )
    error_message = "Use the reviewed urbanpulse database in this project's Melbourne instance."
  }
  validation {
    condition = (
      toset(keys(var.foundation.identities)) == toset(["runtime", "migrate", "import", "worker"]) &&
      toset(keys(var.foundation.database_secret_ids)) == toset(["runtime", "migrate", "import", "worker"]) &&
      length(distinct(values(var.foundation.identities))) == 4 &&
      length(distinct(values(var.foundation.database_secret_ids))) == 4 &&
      alltrue([for identity in values(var.foundation.identities) :
        can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]@${var.project_id}\\.iam\\.gserviceaccount\\.com$", identity))
      ]) &&
      alltrue([for secret in values(var.foundation.database_secret_ids) : can(regex("^[A-Za-z0-9_-]{1,255}$", secret))])
    )
    error_message = "Supply all four distinct foundation identities and secret IDs, in the same project."
  }
}

variable "api_image" {
  description = "Verified published api image by immutable digest, containing all three finite runners."
  type        = string
  validation {
    condition     = can(regex("^australia-southeast2-docker\\.pkg\\.dev/${var.project_id}/[a-z0-9-]+/api@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "Use this project's Melbourne Artifact Registry api image with a sha256 digest, not a tag."
  }
}

variable "source_sha" {
  description = "Full source commit verified against the publication record and image label before planning."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.source_sha))
    error_message = "Record the full tested source commit."
  }
}

variable "schema_revision" {
  description = "Reviewed migration/access matrix shipped in the pinned image."
  type        = string
  default     = "0007_city_checkpoints"
  validation {
    condition     = var.schema_revision == "0007_city_checkpoints"
    error_message = "A new migration requires review of the runner, privileges and deployment revision together."
  }
}

variable "import_id" {
  description = "Expected capture/normalizer identity verified offline from the pinned image. Shared by import and worker."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.import_id))
    error_message = "Use the complete 64-character import identity from the pinned image."
  }
}

variable "secret_versions" {
  description = "Numbered existing database URL secret versions. Values and credentials stay outside Terraform."
  type        = map(string)
  validation {
    condition = (
      toset(keys(var.secret_versions)) == toset(["migrate", "import", "worker"]) &&
      alltrue([for version in values(var.secret_versions) : can(regex("^[1-9][0-9]*$", version))])
    )
    error_message = "Pin migrate, import and worker to numbered secret versions; latest and aliases are forbidden."
  }
}

variable "worker_run_id" {
  description = "Stable manually selected city run, bound to this import; retain it for retries."
  type        = string
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$", var.worker_run_id))
    error_message = "Use a stable 1-100 character run ID with letters, digits, dot, underscore or hyphen."
  }
}
