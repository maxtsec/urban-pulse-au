data "google_project" "current" {
  project_id = var.project_id
}

locals {
  # Service agents are not ordinary project-owned service accounts. Bootstrap
  # must establish the IAP identity; derive its documented principal without IAM get.
  iap_service_agent = "service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
  region            = "australia-southeast2"
  revision          = "${var.name_prefix}-${var.release_id}"
  labels            = { application = "urbanpulse", environment = "demo", source-sha = var.source_sha }
}

resource "google_cloud_run_v2_service" "demo" {
  project              = var.project_id
  name                 = var.name_prefix
  location             = local.region
  deletion_protection  = true
  launch_stage         = "GA"
  ingress              = "INGRESS_TRAFFIC_ALL"
  iap_enabled          = true
  invoker_iam_disabled = false
  labels               = local.labels

  scaling {
    min_instance_count = 0
    max_instance_count = 2
  }
  template {
    revision                         = local.revision
    labels                           = local.labels
    service_account                  = var.foundation.identities.runtime
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 4
    timeout                          = "60s"
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.foundation.database_connection_name]
      }
    }
    containers {
      name       = "web"
      image      = var.web_image
      depends_on = ["api"]
      # Cloud Run v2 reports the managed SQL mount on web in this two-container service.
      # Match that read-back; API readiness verifies socket access, not this field's location.
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      ports {
        name           = "http1"
        container_port = 8080
      }
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = false
      }
      env {
        name  = "API_UPSTREAM"
        value = "127.0.0.1:8000"
      }
      startup_probe {
        period_seconds    = 5
        timeout_seconds   = 4
        failure_threshold = 24
        http_get {
          path = "/health/ready"
          port = 8080
        }
      }
      liveness_probe {
        period_seconds    = 30
        timeout_seconds   = 4
        failure_threshold = 3
        http_get {
          path = "/health/live"
          port = 8080
        }
      }
    }
    containers {
      name    = "api"
      image   = var.api_image
      command = ["/app/.venv/bin/python"]
      # Platform probes need the instance interface; only web declares an ingress port.
      args = [
        "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000",
        "--workers", "1", "--no-server-header",
      ]
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = false
      }
      env {
        name  = "URBANPULSE_MODE"
        value = "fixture"
      }
      env {
        name  = "CACHE_ENABLED"
        value = "false"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.foundation.database_secret_ids.runtime
            version = var.runtime_secret_version
          }
        }
      }
      startup_probe {
        period_seconds    = 5
        timeout_seconds   = 4
        failure_threshold = 24
        http_get {
          path = "/health/ready"
          port = 8000
        }
      }
      liveness_probe {
        period_seconds    = 30
        timeout_seconds   = 4
        failure_threshold = 3
        http_get {
          path = "/health/live"
          port = 8000
        }
      }
    }
  }

  # Always name the traffic target. Updating the template never implies promotion.
  # First creation must explicitly select this first revision (no old target exists).
  traffic {
    type     = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"
    revision = var.serving_revision
    percent  = 100
  }
  dynamic "traffic" {
    for_each = var.serving_revision == local.revision ? [] : [local.revision]
    content {
      type     = "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION"
      revision = traffic.value
      percent  = 0
      tag      = "candidate"
    }
  }
}

# Authoritative for these roles at this service only; inherited grants need preflight review.
resource "google_cloud_run_v2_service_iam_binding" "iap_invoker" {
  project  = var.project_id
  location = local.region
  name     = google_cloud_run_v2_service.demo.name
  role     = "roles/run.invoker"
  members  = ["serviceAccount:${local.iap_service_agent}"]
}

# First create the protected service with no reviewer grant. OAuth is configured
# separately; enabling the explicit allowlist requires its reviewed client ID.
resource "google_iap_web_cloud_run_service_iam_binding" "reviewers" {
  count                  = length(var.iap_members) == 0 ? 0 : 1
  project                = var.project_id
  location               = local.region
  cloud_run_service_name = google_cloud_run_v2_service.demo.name
  role                   = "roles/iap.httpsResourceAccessor"
  members                = var.iap_members
  depends_on             = [google_cloud_run_v2_service_iam_binding.iap_invoker]
}
