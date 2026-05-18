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
  {{ root }}/scripts/akv-inject.sh


[doc('View secret value in Azure Key Vault (just akv show-secret <vault> <name> [<key>])')]
show-secret vault name key="":
    #!/usr/bin/env bash
    if key=""; then
      echo "Displaying json {{ key }} from Azure Key Vault:{{ vault }}/{{ name }}"
      az keyvault secret show --vault-name {{ vault }} --name {{ name }} --query value -o tsv 2>/dev/null | jq -r '.{{ key }}'
    else
      echo "Displaying secret value from Azure Key Vault:{{ vault }}/{{ name }}"
      az keyvault secret show --vault-name {{ vault }} --name {{ name }} --query value -o tsv
    fi
