terraform {
  required_version = ">= 1.16, < 2.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project               = var.project_id
  region                = "australia-southeast2"
  billing_project       = var.project_id
  user_project_override = true
}
