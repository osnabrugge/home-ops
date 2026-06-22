#!/usr/bin/env -S just --justfile

set default-script
set lazy
set quiet
set shell := ['bash', '-euo', 'pipefail', '-c']

# Azure Key Vault Recipes
[group: 'Azure Key Vault']
mod akv "akv"

# Infrastructure Recipes
[group: 'Infrastructure']
mod infra "infrastructure"

# Bootstrap Recipes
[group: 'Bootstrap']
mod bootstrap "bootstrap"

# Kube Recipes
[group: 'Kubernetes']
mod kube "kubernetes"

# Talos Recipes
[group: 'Talos']
mod talos "talos"

[private]
default:
    just -l

[private]
log lvl msg *args:
    gum log -t rfc3339 -s -l "{{ lvl }}" "{{ msg }}" {{ args }}

[private]
template file *args:
    minijinja-cli "{{ file }}" {{ args }} | just akv inject
