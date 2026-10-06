output "workload_identity_provider" { value = google_iam_workload_identity_pool_provider.delivery.name }
output "deployer_service_account" { value = google_service_account.deployer.email }
output "state_bucket" { value = google_storage_bucket.delivery.name }
