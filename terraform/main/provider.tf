terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      version = "3.98.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.6.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "2.47.0"
    }
    cloudflare = {
      source = "cloudflare/cloudflare"
      version = "4.29.0"
    }
  }
}
provider "azurerm" {
  features {}
  use_oidc = true
}
provider "cloudflare" {
  # Configuration options
}
