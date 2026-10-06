# All runs use mocked providers: no cloud credentials, applies or IAM writes.
mock_provider "google" {
  override_during = plan
  mock_data "google_project" {
    defaults = { number = "123456789012" }
  }
  mock_data "google_project_ancestry" {
    defaults = { ancestors = [{ type = "project", id = "example-project" }, { type = "organization", id = "987654321012" }] }
  }
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
  api_image              = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  source_sha             = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  import_id              = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  web_image              = "australia-southeast2-docker.pkg.dev/example-project/urbanpulse/web@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  runtime_secret_version = "1"
  release_id             = "sha-bbbbbbbbbbbb-r1"
  serving_revision       = "urbanpulse-demo-sha-bbbbbbbbbbbb-r1"
  organization_domain    = "example.com"
  iap_members            = ["user:operator@example.com"]
}

run "protected_first_revision" {
  command = plan
  assert {
    condition = (
      google_cloud_run_v2_service.demo.iap_enabled &&
      !google_cloud_run_v2_service.demo.invoker_iam_disabled &&
      google_cloud_run_v2_service.demo.deletion_protection &&
      google_cloud_run_v2_service.demo.location == "australia-southeast2" &&
      google_cloud_run_v2_service_iam_binding.iap_invoker.role == "roles/run.invoker" &&
      google_cloud_run_v2_service_iam_binding.iap_invoker.members == toset(["serviceAccount:service-123456789012@gcp-sa-iap.iam.gserviceaccount.com"]) &&
      google_iap_web_cloud_run_service_iam_binding.reviewers.role == "roles/iap.httpsResourceAccessor" &&
      google_iap_web_cloud_run_service_iam_binding.reviewers.members == var.iap_members &&
      !issensitive(google_iap_web_cloud_run_service_iam_binding.reviewers.members)
    )
    error_message = "Only IAP may invoke; only explicit organization reviewers receive IAP access."
  }
  assert {
    condition = (
      google_cloud_run_v2_service.demo.scaling[0].min_instance_count == 0 &&
      google_cloud_run_v2_service.demo.scaling[0].max_instance_count == 2 &&
      google_cloud_run_v2_service.demo.template[0].scaling[0].min_instance_count == 0 &&
      google_cloud_run_v2_service.demo.template[0].scaling[0].max_instance_count == 2 &&
      google_cloud_run_v2_service.demo.template[0].max_instance_request_concurrency == 4 &&
      google_cloud_run_v2_service.demo.template[0].service_account == var.foundation.identities.runtime &&
      google_cloud_run_v2_service.demo.template[0].execution_environment == "EXECUTION_ENVIRONMENT_GEN2" &&
      google_cloud_run_v2_service.demo.template[0].timeout == "60s"
    )
    error_message = "Keep the reviewed runtime identity and connection/scaling envelope."
  }
  assert {
    condition = (
      length(google_cloud_run_v2_service.demo.template[0].containers) == 2 &&
      one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "api"]).command == tolist(["/app/.venv/bin/python"]) &&
      one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "api"]).args == tolist([
        "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-server-header"
      ]) &&
      one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "api"]).image == var.api_image &&
      length(one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "api"]).ports) == 0 &&
      one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "web"]).image == var.web_image &&
      one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "web"]).ports[0].container_port == 8080 &&
      one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "web"]).depends_on == tolist(["api"]) &&
      one(one([for c in google_cloud_run_v2_service.demo.template[0].containers : c if c.name == "web"]).env).value == "127.0.0.1:8000"
    )
    error_message = "Expose compiled Caddy only, after the single-process API sidecar starts."
  }
  assert {
    condition = alltrue([for c in google_cloud_run_v2_service.demo.template[0].containers :
      c.startup_probe[0].http_get[0].path == "/health/ready" &&
      c.liveness_probe[0].http_get[0].path == "/health/live" &&
      c.startup_probe[0].http_get[0].port == (c.name == "api" ? 8000 : 8080) &&
      c.liveness_probe[0].http_get[0].port == (c.name == "api" ? 8000 : 8080) &&
      c.resources[0].cpu_idle && !c.resources[0].startup_cpu_boost &&
      c.resources[0].limits == tomap({ cpu = "1", memory = "512Mi" })
    ])
    error_message = "Saturated database readiness must never be used as a liveness signal."
  }
  assert {
    condition = (
      toset(google_cloud_run_v2_service.demo.template[0].volumes[0].cloud_sql_instance[0].instances) == toset([var.foundation.database_connection_name]) &&
      alltrue([for c in google_cloud_run_v2_service.demo.template[0].containers : c.name == "api" ? (
        c.volume_mounts[0].mount_path == "/cloudsql" &&
        one([for e in c.env : e if e.name == "DATABASE_URL"]).value_source[0].secret_key_ref[0].secret == var.foundation.database_secret_ids.runtime &&
        one([for e in c.env : e if e.name == "DATABASE_URL"]).value_source[0].secret_key_ref[0].version == "1" &&
        one([for e in c.env : e.value if e.name == "CACHE_ENABLED"]) == "false" &&
        one([for e in c.env : e.value if e.name == "URBANPULSE_MODE"]) == "fixture"
      ) : length(c.volume_mounts) == 0 && length(c.env) == 1])
    )
    error_message = "Only the API gets the numbered runtime secret/socket; no job credential or Redis dependency."
  }
  assert {
    condition = (
      length(google_cloud_run_v2_service.demo.traffic) == 1 &&
      google_cloud_run_v2_service.demo.traffic[0].type == "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION" &&
      google_cloud_run_v2_service.demo.traffic[0].revision == "urbanpulse-demo-sha-bbbbbbbbbbbb-r1" &&
      google_cloud_run_v2_service.demo.traffic[0].percent == 100
    )
    error_message = "First deployment explicitly selects the sole revision; never rely on implicit LATEST traffic."
  }
}

run "candidate_does_not_promote" {
  command = plan
  variables { release_id = "sha-bbbbbbbbbbbb-r2" }
  assert {
    condition = (
      google_cloud_run_v2_service.demo.template[0].revision == "urbanpulse-demo-sha-bbbbbbbbbbbb-r2" &&
      length(google_cloud_run_v2_service.demo.traffic) == 2 &&
      one([for t in google_cloud_run_v2_service.demo.traffic : t if t.percent == 100]).revision == var.serving_revision &&
      one([for t in google_cloud_run_v2_service.demo.traffic : t if t.tag == "candidate"]).revision == "urbanpulse-demo-sha-bbbbbbbbbbbb-r2" &&
      one([for t in google_cloud_run_v2_service.demo.traffic : t if t.tag == "candidate"]).percent == 0
    )
    error_message = "A candidate gets a test URL with zero default traffic; verified serving traffic stays pinned."
  }
}
run "explicit_promotion" {
  command = plan
  variables {
    release_id       = "sha-bbbbbbbbbbbb-r2"
    serving_revision = "urbanpulse-demo-sha-bbbbbbbbbbbb-r2"
  }
  assert {
    condition     = length(google_cloud_run_v2_service.demo.traffic) == 1 && google_cloud_run_v2_service.demo.traffic[0].revision == var.serving_revision
    error_message = "Promotion must explicitly select the verified candidate."
  }
}
run "rollback_leaves_candidate_and_schema_unchanged" {
  command = plan
  variables {
    release_id       = "sha-bbbbbbbbbbbb-r2"
    serving_revision = "urbanpulse-demo-sha-aaaaaaaaaaaa-r1"
  }
  assert {
    condition = (
      google_cloud_run_v2_service.demo.template[0].revision == "urbanpulse-demo-sha-bbbbbbbbbbbb-r2" &&
      one([for t in google_cloud_run_v2_service.demo.traffic : t if t.percent == 100]).revision == "urbanpulse-demo-sha-aaaaaaaaaaaa-r1" &&
      output.candidate_release.schema_revision == "0007_city_checkpoints" &&
      output.candidate_release.import_id == var.import_id
    )
    error_message = "Rollback only changes the named traffic target; it must not rebuild images or mutate data."
  }
}
run "reject_no_organization" {
  command = plan
  override_data {
    target = data.google_project_ancestry.current
    values = { ancestors = [{ type = "project", id = "example-project" }] }
  }
  expect_failures = [google_cloud_run_v2_service.demo]
}

run "reject_mutable_api" {
  command = plan
  variables { api_image = "api:latest" }
  expect_failures = [var.api_image]
}

run "reject_mutable_web" {
  command = plan
  variables { web_image = "web:latest" }
  expect_failures = [var.web_image]
}

run "reject_secret_alias" {
  command = plan
  variables { runtime_secret_version = "latest" }
  expect_failures = [var.runtime_secret_version]
}

run "reject_latest_traffic" {
  command = plan
  variables { serving_revision = "LATEST" }
  expect_failures = [var.serving_revision]
}

run "reject_foreign_revision" {
  command = plan
  variables { serving_revision = "another-service-sha-aaaaaaaaaaaa-r1" }
  expect_failures = [var.serving_revision]
}

run "reject_public_access" {
  command = plan
  variables { iap_members = ["allUsers"] }
  expect_failures = [var.iap_members]
}

run "reject_domain_access" {
  command = plan
  variables { iap_members = ["domain:example.com"] }
  expect_failures = [var.iap_members]
}

run "reject_external_access" {
  command = plan
  variables { iap_members = ["user:reviewer@gmail.com"] }
  expect_failures = [var.iap_members]
}

run "reject_service_account_access" {
  command = plan
  variables { iap_members = ["serviceAccount:sa@example.com"] }
  expect_failures = [var.iap_members]
}

run "reject_empty_access" {
  command = plan
  variables { iap_members = [] }
  expect_failures = [var.iap_members]
}

run "reject_invalid_suffix" {
  command = plan
  variables { release_id = "LATEST_1" }
  expect_failures = [var.release_id]
}

run "reject_wrong_schema" {
  command = plan
  variables { schema_revision = "head" }
  expect_failures = [var.schema_revision]
}

run "organization_through_nested_folders" {
  command = plan
  override_data {
    target = data.google_project.current
    values = { number = "123456789012", org_id = "", folder_id = "111111111111" }
  }
  override_data {
    target = data.google_project_ancestry.current
    values = { ancestors = [
      { type = "project", id = "example-project" },
      { type = "folder", id = "111111111111" },
      { type = "folder", id = "222222222222" },
      { type = "organization", id = "987654321012" },
    ] }
  }
  assert {
    condition     = google_cloud_run_v2_service.demo.iap_enabled
    error_message = "Folder nesting must not reject a project with an organization ancestor."
  }
}
run "reject_folder_without_organization" {
  command = plan
  override_data {
    target = data.google_project_ancestry.current
    values = { ancestors = [{ type = "project", id = "example-project" }, { type = "folder", id = "111111111111" }] }
  }
  expect_failures = [google_cloud_run_v2_service.demo]
}
