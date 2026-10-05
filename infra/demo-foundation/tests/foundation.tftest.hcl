# Mocked plan only: no credentials, remote backend or Cloud API calls.
mock_provider "google" {
  override_during = plan
}

variables {
  project_id = "fixture-project"
}

run "database_safety" {
  command = plan
  assert {
    condition = (
      google_sql_database_instance.demo.database_version == "POSTGRES_17" &&
      google_sql_database_instance.demo.region == "australia-southeast2" &&
      google_sql_database_instance.demo.settings[0].edition == "ENTERPRISE" &&
      google_sql_database_instance.demo.settings[0].tier == "db-g1-small" &&
      google_sql_database_instance.demo.settings[0].availability_type == "ZONAL"
    )
    error_message = "The selected database must stay on the accepted regional shared-core profile."
  }
  assert {
    condition = (
      google_sql_database_instance.demo.deletion_protection &&
      google_sql_database_instance.demo.settings[0].deletion_protection_enabled &&
      google_sql_database.demo.deletion_policy == "ABANDON"
    )
    error_message = "Both instance deletion paths and database removal need protection."
  }
  assert {
    condition = (
      google_sql_database_instance.demo.settings[0].disk_size == 10 &&
      google_sql_database_instance.demo.settings[0].disk_type == "PD_SSD" &&
      !google_sql_database_instance.demo.settings[0].disk_autoresize
    )
    error_message = "Do not silently expand the agreed initial storage footprint."
  }
  assert {
    condition = (
      google_sql_database_instance.demo.settings[0].connector_enforcement == "REQUIRED" &&
      google_sql_database_instance.demo.settings[0].ip_configuration[0].ipv4_enabled &&
      google_sql_database_instance.demo.settings[0].ip_configuration[0].ssl_mode == "ENCRYPTED_ONLY" &&
      length(google_sql_database_instance.demo.settings[0].ip_configuration[0].authorized_networks) == 0
    )
    error_message = "Public addressing must require authenticated encrypted connectors, with no direct-client allowlist."
  }
  assert {
    condition = (
      google_sql_database_instance.demo.settings[0].backup_configuration[0].enabled &&
      google_sql_database_instance.demo.settings[0].backup_configuration[0].point_in_time_recovery_enabled &&
      google_sql_database_instance.demo.settings[0].backup_configuration[0].transaction_log_retention_days == 7 &&
      google_sql_database_instance.demo.settings[0].backup_configuration[0].backup_retention_settings[0].retained_backups == 7 &&
      google_sql_database_instance.demo.settings[0].retain_backups_on_delete
    )
    error_message = "Daily backups, seven-day PITR and retained backups must remain explicit."
  }
}

run "identity_separation" {
  command = plan
  assert {
    condition = (
      toset(keys(google_service_account.demo)) == toset(["runtime", "migrate", "import", "worker"]) &&
      length(distinct([for identity in google_service_account.demo : identity.email])) == 4 &&
      alltrue([for key, grant in google_project_iam_member.sql_client :
        grant.role == "roles/cloudsql.client" &&
        grant.member == "serviceAccount:${google_service_account.demo[key].email}"
      ])
    )
    error_message = "Each role must have its own identity with only the connector project role."
  }
  assert {
    condition = alltrue([for key, grant in google_secret_manager_secret_iam_member.database_reader :
      grant.role == "roles/secretmanager.secretAccessor" &&
      grant.secret_id == google_secret_manager_secret.database[key].secret_id &&
      grant.member == "serviceAccount:${google_service_account.demo[key].email}"
    ])
    error_message = "Database secret access must pair each identity with only its own container."
  }
  assert {
    condition = alltrue([for secret in google_secret_manager_secret.database :
      secret.deletion_protection &&
      one(secret.replication[0].user_managed[0].replicas).location == "australia-southeast2"
    ])
    error_message = "Secret containers must be protected and regionally replicated."
  }
  assert {
    condition = (
      toset(keys(google_project_service.demo)) == toset([
        "run.googleapis.com", "sqladmin.googleapis.com", "secretmanager.googleapis.com", "iap.googleapis.com"
      ]) && alltrue([for service in google_project_service.demo : !service.disable_on_destroy])
    )
    error_message = "Demo state must not adopt or disable the existing bootstrap APIs."
  }
}

run "connection_headroom_and_execution_contract" {
  command = plan
  assert {
    condition = (
      output.deployment_contract.database_role_caps.runtime == 12 &&
      output.deployment_contract.total_client_slots == 21 &&
      output.deployment_contract.unallocated_slots == 19 &&
      output.deployment_contract.connections.reserved_and_admin_slots == 10 &&
      output.deployment_contract.connections.processes_per_instance == 1 &&
      output.deployment_contract.connections.max_overflow == 0
    )
    error_message = "Account for both revisions, replacement slots, all job roles and operational reserve."
  }
  assert {
    condition = (
      one(google_sql_database_instance.demo.settings[0].database_flags).name == "max_connections" &&
      tonumber(one(google_sql_database_instance.demo.settings[0].database_flags).value) == 50 &&
      output.deployment_contract.total_client_slots + output.deployment_contract.connections.reserved_and_admin_slots < 50
    )
    error_message = "The planned client envelope must fit the selected small-instance limit without raising it."
  }
  assert {
    condition = (
      output.deployment_contract.worker.trigger == "manual" &&
      output.deployment_contract.worker.timeout == "600s" &&
      output.deployment_contract.worker.parallelism == 1 &&
      output.deployment_contract.worker.task_count == 1 &&
      output.deployment_contract.worker.max_retries == 0 &&
      output.deployment_contract.worker.executions == 1 &&
      output.deployment_contract.access == "explicit-organization-users-or-groups-only"
    )
    error_message = "The selected manual worker and organization-only access contracts must remain bounded."
  }
}

run "reject_project_display_name" {
  command = plan
  variables {
    project_id = "UrbanPulse Demo"
  }
  expect_failures = [var.project_id]
}

run "reject_unsafe_resource_prefix" {
  command = plan
  variables {
    name_prefix = "../../production"
  }
  expect_failures = [var.name_prefix]
}

override_resource {
  override_during = plan
  target          = google_service_account.demo["runtime"]
  values = {
    email = "urbanpulse-demo-runtime@fixture-project.iam.gserviceaccount.com"
  }
}

override_resource {
  override_during = plan
  target          = google_service_account.demo["migrate"]
  values = {
    email = "urbanpulse-demo-migrate@fixture-project.iam.gserviceaccount.com"
  }
}

override_resource {
  override_during = plan
  target          = google_service_account.demo["import"]
  values = {
    email = "urbanpulse-demo-import@fixture-project.iam.gserviceaccount.com"
  }
}

override_resource {
  override_during = plan
  target          = google_service_account.demo["worker"]
  values = {
    email = "urbanpulse-demo-worker@fixture-project.iam.gserviceaccount.com"
  }
}
