terraform {
  required_version = ">= 1.6.0"

  required_providers {
    vultr = {
      source  = "vultr/vultr"
      version = "~> 2.33"
    }
  }
}

# VULTR_API_KEY is read from the environment; nothing is configured here.
provider "vultr" {
  rate_limit  = 700
  retry_limit = 3
}
