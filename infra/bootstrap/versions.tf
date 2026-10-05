terraform {
  # Import blocks with variable-based IDs require Terraform 1.6 or later.
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # Bill API quota to this project when running with personal application-default credentials.
  billing_project       = var.project_id
  user_project_override = true
}
