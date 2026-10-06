locals {
  region = "australia-southeast2"
  labels = { application = "urbanpulse", environment = "demo", source-sha = var.source_sha }
  initialization_args = [
    "--database", var.foundation.database_name,
    "--expected-revision", var.schema_revision,
    "--timeout-seconds", "540",
  ]
  commands = {
    migrate = concat(["-m", "workers.initialization.job", "migrate"], local.initialization_args)
    import = concat(
      ["-m", "workers.initialization.job", "import"], local.initialization_args,
      ["--expected-import-id", var.import_id],
    )
    worker = [
      "-m", "workers.city.job", var.worker_run_id,
      "--scope", var.import_id, "--scenario", "city", "--seconds", "360",
      "--timeout-seconds", "540",
    ]
  }
}

# This root owns Job definitions only. Foundation owns all API, SQL, IAM and
# secret containers. Creating or updating these definitions does not execute them.
resource "google_cloud_run_v2_job" "demo" {
  for_each            = local.commands
  project             = var.project_id
  name                = "${var.name_prefix}-${each.key}"
  location            = local.region
  launch_stage        = "GA"
  deletion_protection = true
  labels              = local.labels

  template {
    task_count  = 1
    parallelism = 1
    labels      = local.labels
    template {
      service_account       = var.foundation.identities[each.key]
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
      # The 60-second difference also needs startup/cleanup evidence; see the runbook.
      timeout     = "600s"
      max_retries = 0
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [var.foundation.database_connection_name]
        }
      }
      containers {
        image   = var.api_image
        command = ["/app/.venv/bin/python"]
        args    = each.value
        resources {
          limits = { cpu = "1", memory = "512Mi" }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
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
              secret  = var.foundation.database_secret_ids[each.key]
              version = var.secret_versions[each.key]
            }
          }
        }
      }
    }
  }
}
