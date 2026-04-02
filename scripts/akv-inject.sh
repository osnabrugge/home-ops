#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   cat file.yaml | scripts/akv-inject.sh
#
# Placeholders supported:
#   azkv://<vault>/<secretName>
#   azkv://<vault>/<secretName>#<jsonKey>
#   azkv://<secretName>                 (requires AZURE_KEYVAULT_NAME)
#   azkv://<secretName>#<jsonKey>       (requires AZURE_KEYVAULT_NAME)
#
# Modes:
#   AKV mode (default):  Fetches secrets via Azure CLI (`az keyvault secret show`)
#   Local mode:          Set AKV_LOCAL_DIR to a directory containing local secret JSON files.
#                        Lookup: $AKV_LOCAL_DIR/<vault>/<name>.json
#                        Same JSON format as AKV (the secret "value" is the file content).
#
# Requirements:
#   - AKV mode: Azure CLI (`az`) installed + authenticated
#   - Both modes: `jq` installed (required when using #<jsonKey> selectors)

local_mode=false
if [[ -n "${AKV_LOCAL_DIR:-}" ]]; then
  local_mode=true
  if [[ ! -d "$AKV_LOCAL_DIR" ]]; then
    echo "akv-inject: AKV_LOCAL_DIR='$AKV_LOCAL_DIR' is not a directory" >&2
    exit 1
  fi
fi

if [[ "$local_mode" == false ]]; then
  if ! command -v az >/dev/null 2>&1; then
    echo "akv-inject: 'az' (Azure CLI) not found in PATH" >&2
    exit 127
  fi
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "akv-inject: 'jq' not found in PATH" >&2
  exit 127
fi

input="$(cat)"

# Extract unique placeholders (supports optional #jsonKey)
# Sort longest-first to prevent shorter prefixes from corrupting longer matches
# e.g. CLUSTER_SECRET must not match before CLUSTER_SECRETBOXENCRYPTIONSECRET
mapfile -t refs < <(
  printf '%s' "$input" |
    grep -oE 'azkv://[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?(#[A-Za-z0-9_.-]+)?' |
    sort -u | awk '{ print length, $0 }' | sort -rn | awk '{ print $2 }' || true
)

# Cache fetched secret values by vault/name to avoid redundant lookups
declare -A _secret_cache

for ref in "${refs[@]}"; do
  rest="${ref#azkv://}"

  if [[ "$rest" == */* ]]; then
    vault="${rest%%/*}"
    name_with_selector="${rest#*/}"
  else
    : "${AZURE_KEYVAULT_NAME:?akv-inject: AZURE_KEYVAULT_NAME must be set when using azkv://<name> references}"
    vault="$AZURE_KEYVAULT_NAME"
    name_with_selector="$rest"
  fi

  # Split optional JSON selector suffix: <name>#<jsonKey>
  name="$name_with_selector"
  json_key=""
  if [[ "$name_with_selector" == *"#"* ]]; then
    json_key="${name_with_selector#*#}"
    name="${name_with_selector%%#*}"
  fi

  # Fetch the secret value (with caching)
  cache_key="${vault}/${name}"
  if [[ -n "${_secret_cache[$cache_key]+x}" ]]; then
    value="${_secret_cache[$cache_key]}"
  elif [[ "$local_mode" == true ]]; then
    local_file="${AKV_LOCAL_DIR}/${vault}/${name}.json"
    if [[ ! -f "$local_file" ]]; then
      echo "akv-inject: local secret file not found: $local_file" >&2
      exit 1
    fi
    value="$(cat "$local_file")"
    _secret_cache[$cache_key]="$value"
  else
    value="$(
      az keyvault secret show \
        --vault-name "$vault" \
        --name "$name" \
        --query value \
        -o tsv
    )"
    _secret_cache[$cache_key]="$value"
  fi

  # If a JSON key selector was used, extract it
  if [[ -n "$json_key" ]]; then
    if ! printf '%s' "$value" | jq -e . >/dev/null 2>&1; then
      echo "akv-inject: secret '$vault/$name' is not valid JSON but '#$json_key' was requested" >&2
      echo -n "akv-inject: first 200 chars: " >&2
      printf '%s' "$value" | head -c 200 >&2
      echo >&2
      exit 1
    fi

    extracted="$(printf '%s' "$value" | jq -r --arg k "$json_key" '.[$k]')"
    if [[ "$extracted" == "null" ]]; then
      echo "akv-inject: key '$json_key' not found in JSON secret '$vault/$name'" >&2
      exit 1
    fi
    value="$extracted"
  fi

  # Literal string replacement — safe with any characters (/, &, newlines, $, etc.)
  # No sed escaping needed. Bash ${//} treats the pattern literally for fixed strings.
  input="${input//"$ref"/"$value"}"
done

printf '%s' "$input"
