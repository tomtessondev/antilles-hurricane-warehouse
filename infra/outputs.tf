output "service_account_email" {
  description = "GitHub repository variable GCP_SERVICE_ACCOUNT"
  value       = google_service_account.runner.email
}

output "workload_identity_provider" {
  description = "GitHub repository variable GCP_WORKLOAD_IDENTITY_PROVIDER"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "datasets" {
  value = [for d in google_bigquery_dataset.layer : d.dataset_id]
}
