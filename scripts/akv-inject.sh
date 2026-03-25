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
# Requirements:
#   - Azure CLI (`az`) installed + authenticated
#   - `jq` installed (required when using #<jsonKey> selectors)

if ! command -v az >/dev/null 2>&1; then
  echo "akv-inject: 'az' (Azure CLI) not found in PATH" >&2
  exit 127
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "akv-inject: 'jq' not found in PATH" >&2
  exit 127
fi

input="$(cat)"

# Extract unique placeholders (supports optional #jsonKey)
mapfile -t refs < <(
  printf '%s' "$input" |
    grep -oE 'azkv://[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?(#[A-Za-z0-9_.-]+)?' |
    sort -u || true
)

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

  # Fetch the secret value
  value="$(
    az keyvault secret show \
      --vault-name "$vault" \
      --name "$name" \
      --query value \
      -o tsv
  )"

  # If a JSON key selector was used, extract it
  if [[ -n "$json_key" ]]; then
    # Debug/validation: tell us exactly which secret is not valid JSON
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

  # Escape for safe sed replacement
  esc_value="$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')"

  # Replace all occurrences of the full placeholder (including #jsonKey if present)
  input="$(printf '%s' "$input" | sed -e "s|$ref|$esc_value|g")"
done

printf '%s' "$input"
