# Infrastructure (GCP)

Terraform for the warehouse's Google Cloud side, in project `antilles-hurricanes`:

- BigQuery datasets `raw`, `staging`, `intermediate`, `marts` (location `US`, where the public
  datasets live);
- service account `dbt-runner`: may run BigQuery jobs and write those four datasets, nothing
  else;
- Workload Identity Federation for GitHub Actions: only the workflows of
  `tomtessondev/antilles-hurricane-warehouse` can act as `dbt-runner`, with short-lived
  credentials; no service account key exists;
- a monthly budget of 5 USD (the billing account's currency) with alerts at 50, 90 and 100 %.

## Once, by hand

```bash
gcloud services enable bigquery.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com billingbudgets.googleapis.com cloudresourcemanager.googleapis.com \
  storage.googleapis.com cloudbilling.googleapis.com --project antilles-hurricanes
gcloud auth application-default login
gcloud auth application-default set-quota-project antilles-hurricanes   # needed by the budget API
gcloud storage buckets create gs://antilles-hurricanes-tfstate --location=US \
  --uniform-bucket-level-access && gcloud storage buckets update gs://antilles-hurricanes-tfstate --versioning
```

## Apply

```bash
cp terraform.tfvars.example terraform.tfvars   # the billing account id; not committed
terraform init
terraform plan -out=tfplan                     # the owner reads it
terraform apply tfplan                         # only after the owner approves
terraform output                               # service account and provider for GitHub variables
```

The outputs go into the GitHub repository variables `GCP_SERVICE_ACCOUNT` and
`GCP_WORKLOAD_IDENTITY_PROVIDER` (variables, not secrets: neither grants access on its own).
