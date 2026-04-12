#!/usr/bin/env bash
set -euo pipefail

# Sanitize OPNsense config XML for safe sharing
# Usage: scripts/sanitize-opnsense-config.sh <config.xml> [output.xml]

in="${1:?Usage: sanitize-opnsense-config.sh <config.xml> [output.xml]}"
out="${2:-sanitized-$(basename "$in")}"

if [[ ! -f "$in" ]]; then
  echo "error: file not found: $in" >&2
  exit 1
fi

cp "$in" "$out"

# --- XML element redaction (content between tags) ---
# Passwords, keys, secrets, tokens, communities
elements=(
  password
  key
  privatekey
  private-key
  shared_key
  pre_shared_key
  psk
  token
  secret
  secretkey
  apikey
  auth_pass
  auth_user
  rocommunity
  rwcommunity
  ddnsdomainkey
  ddnsdomainkeyname
  enable_password
  crypto_password
  SNMP_COMMUNITY
)

for el in "${elements[@]}"; do
  # Match <element>content</element> and redact content, preserve empty tags
  sed -i -E "s|(<${el}[^>]*>)[^<]+(</\s*${el}>)|\1__REDACTED__\2|gi" "$out"
done

# --- Credential-in-URL patterns (https://user:pass@host) ---
sed -i -E 's#(https?://)[^/@:]+:[^/@]+@#\1__REDACTED_CREDS__@#g' "$out"

# --- Specific high-value fields that don't match generic patterns ---
# WireGuard private keys
sed -i -E 's|(<PrivateKey>)[^<]+(</PrivateKey>)|\1__REDACTED__\2|gi' "$out"
sed -i -E 's|(<PublicKey>)[^<]+(</PublicKey>)|\1__REDACTED__\2|gi' "$out"
sed -i -E 's|(<PresharedKey>)[^<]+(</PresharedKey>)|\1__REDACTED__\2|gi' "$out"

# OpenVPN TLS keys and certificates (multi-line base64 blocks)
sed -i -E '/<tls>/,/<\/tls>/{ /^[A-Za-z0-9+\/=]{20,}/s/.+/__REDACTED_CERT_LINE__/ }' "$out"
sed -i -E '/<ca>/,/<\/ca>/{ /^[A-Za-z0-9+\/=]{20,}/s/.+/__REDACTED_CERT_LINE__/ }' "$out"
sed -i -E '/<prv>/,/<\/prv>/{ /^[A-Za-z0-9+\/=]{20,}/s/.+/__REDACTED_CERT_LINE__/ }' "$out"
sed -i -E '/<crt>/,/<\/crt>/{ /^[A-Za-z0-9+\/=]{20,}/s/.+/__REDACTED_CERT_LINE__/ }' "$out"

# SNMP community strings (may appear as attribute or plain text)
sed -i -E 's|(<rocommunity>)[^<]+(</rocommunity>)|\1__REDACTED__\2|gi' "$out"
sed -i -E 's|(<rwcommunity>)[^<]+(</rwcommunity>)|\1__REDACTED__\2|gi' "$out"

# User password hashes (bcrypt etc)
sed -i -E 's|(<bcrypt-hash>)[^<]+(</bcrypt-hash>)|\1__REDACTED__\2|gi' "$out"
sed -i -E 's|(\$2[aby]\$[0-9]+\$[A-Za-z0-9./]+)|__BCRYPT_REDACTED__|g' "$out"

# TOTP seeds
sed -i -E 's|(<otp_seed>)[^<]+(</otp_seed>)|\1__REDACTED__\2|gi' "$out"

# API keys in env-style values
sed -i -E 's|(api[_-]?key["\s:=]+)["\x27]?[A-Za-z0-9_-]{16,}["\x27]?|\1"__REDACTED__"|gi' "$out"

# MAC addresses (optional - uncomment to redact)
# sed -i -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/__MAC_REDACTED__/g' "$out"

# --- Verification ---
echo "Sanitized: $out"
echo ""
echo "=== Leak check ==="
leaks=$(grep -nEi '<(password|secret|token|apikey|privatekey|psk|rocommunity|rwcommunity|ddnsdomainkey)>[^_<]' "$out" 2>/dev/null | grep -v "__REDACTED__" | head -10 || true)
url_leaks=$(grep -nE 'https?://[^/@:]+:[^/@]+@' "$out" 2>/dev/null | head -5 || true)
bcrypt_leaks=$(grep -nE '\$2[aby]\$[0-9]+\$[A-Za-z0-9./]{20,}' "$out" 2>/dev/null | head -5 || true)

if [[ -z "$leaks" && -z "$url_leaks" && -z "$bcrypt_leaks" ]]; then
  echo "  PASS: No obvious secrets detected"
else
  echo "  WARNING: Potential secrets still present:"
  [[ -n "$leaks" ]] && echo "$leaks"
  [[ -n "$url_leaks" ]] && echo "$url_leaks"
  [[ -n "$bcrypt_leaks" ]] && echo "$bcrypt_leaks"
fi

echo ""
echo "Manual review recommended before sharing."
echo "Fields that may need manual check: usernames, hostnames, WAN IPs, email addresses."
