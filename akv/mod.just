set no-exit-message
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

root := justfile_directory()

[private]
default:
  just -l akv

[script]
[doc('Inject Azure Key Vault secrets into stdin (azkv://vault/name[#key] or azkv://name[#key])')]
inject:
  "{{ root }}/scripts/akv-inject.sh"
