terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      version = "3.99.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.6.1"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "2.48.0"
    }
    cloudflare = {
      source = "cloudflare/cloudflare"
      version = "4.30.0"
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
