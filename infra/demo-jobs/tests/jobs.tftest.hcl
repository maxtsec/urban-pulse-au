# Mocked plans only: no credentials, Cloud API calls, applies or executions.
mock_provider "google" {
  override_during = plan
}

variables {
  project_id = "example-project"
  foundation = {
    database_connection_name = "example-project:australia-southeast2:urbanpulse-demo-pg17"
    database_name            = "urbanpulse"
    identities = {
      runtime = "urbanpulse-demo-runtime@example-project.iam.gserviceaccount.com"
      migrate = "urbanpulse-demo-migrate@example-project.iam.gserviceaccount.com"
      import  = "urbanpulse-demo-import@example-project.iam.gserviceaccount.com"
      worker  = "urbanpulse-demo-worker@example-project.iam.gserviceaccount.com"
    }
    database_secret_ids = {
      runtime = "urbanpulse-demo-runtime-database-url"
      migrate = "urbanpulse-demo-migrate-database-url"
      import  = "urbanpulse-demo-import-database-url"
      worker  = "urbanpulse-demo-worker-database-url"
    }
  }
  api_image     = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  source_sha    = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  import_id     = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  worker_run_id = "demo-city-bbbbbbbb"
  secret_versions = {
    migrate = "1"
    import  = "1"
    worker  = "1"
  }
}

run "bounded_private_jobs" {
  command = plan
  assert {
    condition = (
      toset(keys(google_cloud_run_v2_job.demo)) == toset(["migrate", "import", "worker"]) &&
      alltrue([for job in google_cloud_run_v2_job.demo :
        job.location == "australia-southeast2" && job.project == var.project_id &&
        job.deletion_protection && job.run_execution_token == null && job.start_execution_token == null &&
        job.template[0].task_count == 1 &&
        job.template[0].parallelism == 1 &&
        job.template[0].template[0].timeout == "600s" &&
        job.template[0].template[0].max_retries == 0 &&
        job.template[0].template[0].execution_environment == "EXECUTION_ENVIRONMENT_GEN2" &&
        job.template[0].template[0].containers[0].command == tolist(["/app/.venv/bin/python"]) &&
        job.template[0].template[0].containers[0].image == var.api_image &&
        job.labels["source-sha"] == var.source_sha &&
        job.template[0].template[0].containers[0].resources[0].limits == tomap({ cpu = "1", memory = "512Mi" })
      ])
    )
    error_message = "Keep all three runners finite, digest-pinned and within the accepted execution envelope."
  }
  assert {
    condition = alltrue([for role, job in google_cloud_run_v2_job.demo :
      job.template[0].template[0].service_account == var.foundation.identities[role] &&
      one([for env in job.template[0].template[0].containers[0].env : env if env.name == "DATABASE_URL"]).value_source[0].secret_key_ref[0].secret == var.foundation.database_secret_ids[role] &&
      one([for env in job.template[0].template[0].containers[0].env : env if env.name == "DATABASE_URL"]).value_source[0].secret_key_ref[0].version == var.secret_versions[role] &&
      one([for env in job.template[0].template[0].containers[0].env : env.value if env.name == "CACHE_ENABLED"]) == "false" &&
      one([for env in job.template[0].template[0].containers[0].env : env.value if env.name == "URBANPULSE_MODE"]) == "fixture" &&
      job.template[0].template[0].volumes[0].cloud_sql_instance[0].instances == tolist([var.foundation.database_connection_name]) &&
      job.template[0].template[0].containers[0].volume_mounts[0].mount_path == "/cloudsql"
    ])
    error_message = "Pair each Job with its own identity/numbered secret and the foundation socket; no default login or Redis."
  }
  assert {
    condition = (
      google_cloud_run_v2_job.demo["migrate"].template[0].template[0].containers[0].args == tolist([
        "-m", "workers.initialization.job", "migrate", "--database", "urbanpulse",
        "--expected-revision", "0007_city_checkpoints", "--timeout-seconds", "540",
      ]) &&
      google_cloud_run_v2_job.demo["import"].template[0].template[0].containers[0].args == tolist([
        "-m", "workers.initialization.job", "import", "--database", "urbanpulse",
        "--expected-revision", "0007_city_checkpoints", "--timeout-seconds", "540",
        "--expected-import-id", var.import_id,
      ]) &&
      google_cloud_run_v2_job.demo["worker"].template[0].template[0].containers[0].args == tolist([
        "-m", "workers.city.job", var.worker_run_id, "--scope", var.import_id,
        "--scenario", "city", "--seconds", "360", "--timeout-seconds", "540",
      ])
    )
    error_message = "Commands must use finite runners and the same pinned import, with shutdown headroom."
  }
}

run "reject_mutable_image" {
  command = plan
  variables {
    api_image = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/api:latest"
  }
  expect_failures = [var.api_image]
}

run "reject_foreign_image" {
  command = plan
  variables {
    api_image = "australia-southeast2-docker.pkg.dev/other-project/urbanpulse/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.api_image]
}

run "reject_web_image" {
  command = plan
  variables {
    api_image = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/web@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.api_image]
}

run "reject_secret_alias" {
  command = plan
  variables {
    secret_versions = { migrate = "1", import = "latest", worker = "1" }
  }
  expect_failures = [var.secret_versions]
}

run "reject_missing_secret_version" {
  command = plan
  variables {
    secret_versions = { migrate = "1", import = "1" }
  }
  expect_failures = [var.secret_versions]
}

run "reject_unreviewed_revision" {
  command = plan
  variables {
    schema_revision = "head"
  }
  expect_failures = [var.schema_revision]
}

run "reject_invalid_import" {
  command = plan
  variables {
    import_id = "not-an-import"
  }
  expect_failures = [var.import_id]
}

run "reject_short_source" {
  command = plan
  variables {
    source_sha = "123abcd"
  }
  expect_failures = [var.source_sha]
}

run "reject_empty_run" {
  command = plan
  variables {
    worker_run_id = ""
  }
  expect_failures = [var.worker_run_id]
}

run "reject_cross_project_database" {
  command = plan
  variables {
    foundation = {
      database_connection_name = "other-project:australia-southeast2:urbanpulse-demo-pg17"
      database_name            = "urbanpulse"
      identities = {
        runtime = "urbanpulse-demo-runtime@example-project.iam.gserviceaccount.com"
        migrate = "urbanpulse-demo-migrate@example-project.iam.gserviceaccount.com"
        import  = "urbanpulse-demo-import@example-project.iam.gserviceaccount.com"
        worker  = "urbanpulse-demo-worker@example-project.iam.gserviceaccount.com"
      }
      database_secret_ids = {
        runtime = "urbanpulse-demo-runtime-database-url"
        migrate = "urbanpulse-demo-migrate-database-url"
        import  = "urbanpulse-demo-import-database-url"
        worker  = "urbanpulse-demo-worker-database-url"
      }
    }
  }
  expect_failures = [var.foundation]
}

run "reject_reused_identity" {
  command = plan
  variables {
    foundation = {
      database_connection_name = "example-project:australia-southeast2:urbanpulse-demo-pg17"
      database_name            = "urbanpulse"
      identities = {
        runtime = "urbanpulse-demo-runtime@example-project.iam.gserviceaccount.com"
        migrate = "urbanpulse-demo-migrate@example-project.iam.gserviceaccount.com"
        import  = "urbanpulse-demo-migrate@example-project.iam.gserviceaccount.com"
        worker  = "urbanpulse-demo-worker@example-project.iam.gserviceaccount.com"
      }
      database_secret_ids = {
        runtime = "urbanpulse-demo-runtime-database-url"
        migrate = "urbanpulse-demo-migrate-database-url"
        import  = "urbanpulse-demo-import-database-url"
        worker  = "urbanpulse-demo-worker-database-url"
      }
    }
  }
  expect_failures = [var.foundation]
}

run "reject_reused_secret" {
  command = plan
  variables {
    foundation = {
      database_connection_name = "example-project:australia-southeast2:urbanpulse-demo-pg17"
      database_name            = "urbanpulse"
      identities = {
        runtime = "urbanpulse-demo-runtime@example-project.iam.gserviceaccount.com"
        migrate = "urbanpulse-demo-migrate@example-project.iam.gserviceaccount.com"
        import  = "urbanpulse-demo-import@example-project.iam.gserviceaccount.com"
        worker  = "urbanpulse-demo-worker@example-project.iam.gserviceaccount.com"
      }
      database_secret_ids = {
        runtime = "urbanpulse-demo-runtime-database-url"
        migrate = "urbanpulse-demo-migrate-database-url"
        import  = "urbanpulse-demo-migrate-database-url"
        worker  = "urbanpulse-demo-worker-database-url"
      }
    }
  }
  expect_failures = [var.foundation]
}
