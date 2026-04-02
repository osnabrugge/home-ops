set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

root := justfile_directory()

[private]
default:
  just -l akv

[doc('Inject Azure Key Vault secrets into stdin (azkv://vault/name[#key] or azkv://name[#key])')]
inject:
  bash "{{ root }}/scripts/akv-inject.sh"
