set lazy
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

root := justfile_directory()

[private]
[script]
default:
  just -l akv

[doc('Inject Azure Key Vault secrets into stdin (azkv://vault/name[#key] or azkv://name[#key])')]
inject:
  bash "{{ root }}/scripts/akv-inject.sh"
