mock_provider "google" { override_during = plan }
variables {
  project_id              = "example-project"
  state_bucket            = "example-project-demo-delivery"
  runtime_service_account = "urbanpulse-demo-runtime@example-project.iam.gserviceaccount.com"
}
run "private_versioned_state_and_separate_deployer" {
  command = plan
  assert {
    condition     = google_storage_bucket.delivery.versioning[0].enabled && google_storage_bucket.delivery.uniform_bucket_level_access && google_storage_bucket.delivery.public_access_prevention == "enforced" && !google_storage_bucket.delivery.force_destroy
    error_message = "Deployment state must be private, versioned and protected from forced deletion."
  }
  assert {
    condition     = !contains(google_project_iam_custom_role.service.permissions, "run.services.setIamPolicy") && !contains(google_project_iam_custom_role.service.permissions, "run.services.delete") && google_service_account_iam_member.runtime.role == "roles/iam.serviceAccountUser"
    error_message = "Only existing service updates and one runtime identity are allowed."
  }
  assert {
    condition     = strcontains(google_iam_workload_identity_pool_provider.delivery.attribute_condition, "assertion.job_workflow_ref") && strcontains(google_iam_workload_identity_pool_provider.delivery.attribute_condition, "demo-promotion") && strcontains(google_iam_workload_identity_pool_provider.delivery.attribute_condition, "demo-candidate")
    error_message = "Federation must bind the reusable workflow and environment."
  }
}
run "reject_job_identity" {
  command = plan
  variables {
    runtime_service_account = "urbanpulse-demo-migrate@example-project.iam.gserviceaccount.com"
  }
  expect_failures = [var.runtime_service_account]
}
