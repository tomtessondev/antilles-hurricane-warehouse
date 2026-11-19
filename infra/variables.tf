variable "project_id" {
  description = "GCP project of the warehouse"
  type        = string
  default     = "antilles-hurricanes"
}

variable "billing_account" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX), for the budget"
  type        = string
}

variable "github_repository" {
  description = "The only repository whose workflows may act as the runner"
  type        = string
  default     = "tomtessondev/antilles-hurricane-warehouse"
}

variable "budget_amount" {
  description = "Monthly budget; alerts at 50, 90 and 100 %"
  type        = number
  default     = 5
}

variable "budget_currency" {
  description = "Currency of the billing account (a budget must use it)"
  type        = string
  default     = "USD" # the billing account's currency (checked with gcloud)
}
