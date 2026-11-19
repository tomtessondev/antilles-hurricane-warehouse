# The GCP side of the warehouse: the BigQuery datasets, the service account the jobs run
# as, keyless authentication for GitHub Actions (Workload Identity Federation) and a budget.

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
  # Versioned bucket created once with gcloud (see README.md).
  backend "gcs" {
    bucket = "antilles-hurricanes-tfstate"
    prefix = "warehouse"
  }
}

provider "google" {
  project = var.project_id
  # The budget API is called with the owner's user credentials: bill the quota to this project.
  user_project_override = true
  billing_project       = var.project_id
}

locals {
  datasets = ["raw", "staging", "intermediate", "marts"]
}

# Public datasets live in the US multi-region and a query cannot mix locations.
resource "google_bigquery_dataset" "layer" {
  for_each   = toset(local.datasets)
  dataset_id = each.key
  location   = "US"
}

resource "google_service_account" "runner" {
  account_id   = "dbt-runner"
  display_name = "Loaders and dbt (GitHub Actions)"
}

resource "google_project_iam_member" "runner_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runner.email}"
}

resource "google_bigquery_dataset_iam_member" "runner_data" {
  for_each   = google_bigquery_dataset.layer
  dataset_id = each.value.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runner.email}"
}

# GitHub Actions exchanges its OIDC token for short-lived credentials: no key anywhere.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  # Only this repository's workflows (main and pull requests from its own branches).
  attribute_condition = "assertion.repository == '${var.github_repository}'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_runner" {
  service_account_id = google_service_account.runner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_billing_budget" "warehouse" {
  billing_account = var.billing_account
  display_name    = "antilles-hurricanes"
  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }
  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }
  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }
}

data "google_project" "this" {
  project_id = var.project_id
}
