#!/usr/bin/env -S just --justfile

set lazy
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

[group: 'Azure Keyvault']
mod akv "akv"

[group: 'Bootstrap']
mod bootstrap "bootstrap"

[group: 'Infrastructure']
mod infra "infra"

[group: 'Kube']
mod kube "kubernetes"

[group: 'Talos']
mod talos "talos"

[private]
[script]
default:
    just -l

[private]
[script]
log lvl msg *args:
    gum log -t rfc3339 -s -l "{{ lvl }}" "{{ msg }}" {{ args }}

[private]
[script]
template file *args:
    minijinja-cli "{{ file }}" {{ args }} | just akv inject
