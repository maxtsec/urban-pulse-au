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
  description = "Stable service name, independent of the foundation state."
  default     = "urbanpulse-demo"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{3,14}[a-z0-9]$", var.name_prefix))
    error_message = "Use 5-16 lowercase letters, digits or hyphens, starting with a letter and ending with a letter or digit."
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
  description = "Verified published api image by immutable digest, containing the verified API entrypoint."
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

variable "web_image" {
  type = string
  validation {
    condition     = can(regex("^australia-southeast2-docker\\.pkg\\.dev/${var.project_id}/[a-z0-9-]+/web@sha256:[0-9a-f]{64}$", var.web_image))
    error_message = "Use this project's compiled web serving image by immutable digest."
  }
}

variable "runtime_secret_version" {
  type = string
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.runtime_secret_version))
    error_message = "Pin the runtime database URL to an existing numbered secret version."
  }
}

variable "release_id" {
  description = "Unique suffix for an immutable candidate revision, e.g. sha-0123456789ab-r1. Never reuse with changed image/config."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,43}[a-z0-9]$", var.release_id))
    error_message = "Use a 2-45 character lowercase revision suffix ending in a letter or digit."
  }
}

variable "serving_revision" {
  description = "Explicit verified revision receiving 100% of default URL traffic. Keep unchanged for a candidate deployment; set to an existing compatible revision for rollback."
  type        = string
  validation {
    condition     = length(var.serving_revision) <= 63 && can(regex("^${var.name_prefix}-[a-z][a-z0-9-]*[a-z0-9]$", var.serving_revision))
    error_message = "Use an explicit revision of this service, not LATEST. First creation must select its own candidate revision."
  }
}

variable "custom_oauth_client_id" {
  description = "Non-secret client ID verified in this service's IAP settings before granting access. OAuth credentials are configured outside Terraform; this value is an operator assertion, not a live verification."
  type        = string
  default     = null
  validation {
    condition     = var.custom_oauth_client_id == null ? true : can(regex("^[0-9]+-[A-Za-z0-9_-]+\\.apps\\.googleusercontent\\.com$", var.custom_oauth_client_id))
    error_message = "Use the reviewed custom Web OAuth client ID, or null for the closed bootstrap stage. Never supply the client secret."
  }
}

variable "iap_members" {
  description = "Named Google users, including consumer Gmail. Empty by default for closed bootstrap; initially grant only the acceptance operator. Review each later audience change separately."
  type        = set(string)
  default     = []
  nullable    = false
  # Deliberately visible in the private plan so every access grant can be reviewed.
  validation {
    condition = alltrue([for member in var.iap_members :
      member == null ? false : can(regex("^user:[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)+$", member)) &&
      !endswith(lower(member), ".gserviceaccount.com")
    ])
    error_message = "Allow only named Google user emails; no public, group, domain-wide or service-account access."
  }
  validation {
    condition     = length(var.iap_members) == 0 || var.custom_oauth_client_id != null
    error_message = "Verify custom OAuth on this service and record its client ID before enabling the allowlist."
  }
}
