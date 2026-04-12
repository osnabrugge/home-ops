#!/usr/bin/env bash
set -euo pipefail

# CyberPower PDU41001 Power Control via SNMP
#
# Usage:
#   scripts/infra-pdu.sh <command> <node>
#
# Commands:
#   on <node>             Power on an outlet
#   off <node>            Power off an outlet (DANGEROUS)
#   reboot <node>         Power cycle an outlet (off then on)
#   status [node]         Show outlet status (all outlets if no node specified)
#
# Environment:
#   PDU_COMMUNITY         SNMP community string (default: private)
#
# PDU Outlet Mapping (from NetBox):
#   pdu01 (192.168.99.15):  1=k8s01, 2=k8s02, 3=k8s03, 4=nas01, 5=core01-u1, 6=fw01
#   pdu02 (192.168.99.16):  1=k8s04, 2=k8s05, 3=k8s06, 4=nas01, 5=core01-u2
#
# SNMP OID: .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.{outlet}
#   Values: 1=on, 2=off, 3=reboot, 4=cancel
#
# Requirements:
#   - snmpset and snmpget (net-snmp-utils)
#   - Network access to management VLAN (192.168.99.0/24)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Load credentials from .private/cyberpower.env if available
if [[ -f "$ROOT_DIR/.private/cyberpower.env" ]]; then
  _comm="$(grep -oP 'Community String: \K.*' "$ROOT_DIR/.private/cyberpower.env" 2>/dev/null || true)"
  [[ -n "$_comm" ]] && PDU_COMMUNITY="$_comm"
fi
PDU_COMMUNITY="${PDU_COMMUNITY:-private}"
SNMP_OID_BASE=".1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4"

if ! command -v snmpset >/dev/null 2>&1; then
  echo "error: snmpset not found. Install net-snmp or snmp package." >&2
  exit 127
fi

# Node → PDU IP + outlet mapping
declare -A NODE_PDU_IP=(
  [k8s01]=192.168.99.15  [k8s02]=192.168.99.15  [k8s03]=192.168.99.15
  [nas01]=192.168.99.15   [core01-u1]=192.168.99.15  [fw01]=192.168.99.15
  [k8s04]=192.168.99.16  [k8s05]=192.168.99.16  [k8s06]=192.168.99.16
  [nas01-psu2]=192.168.99.16  [core01-u2]=192.168.99.16
)

declare -A NODE_PDU_OUTLET=(
  [k8s01]=1  [k8s02]=2  [k8s03]=3
  [nas01]=4  [core01-u1]=5  [fw01]=6
  [k8s04]=1  [k8s05]=2  [k8s06]=3
  [nas01-psu2]=4  [core01-u2]=5
)

declare -A NODE_PDU_NAME=(
  [k8s01]=pdu01  [k8s02]=pdu01  [k8s03]=pdu01
  [nas01]=pdu01  [core01-u1]=pdu01  [fw01]=pdu01
  [k8s04]=pdu02  [k8s05]=pdu02  [k8s06]=pdu02
  [nas01-psu2]=pdu02  [core01-u2]=pdu02
)

_snmp_set() {
  local ip="$1" outlet="$2" value="$3"
  snmpset -v 2c -c "$PDU_COMMUNITY" -r 2 -t 3 \
    "$ip" "${SNMP_OID_BASE}.${outlet}" integer "$value" >/dev/null 2>&1
}

_snmp_get() {
  local ip="$1" outlet="$2"
  snmpget -v 2c -c "$PDU_COMMUNITY" -r 2 -t 3 \
    "$ip" "${SNMP_OID_BASE}.${outlet}" -Ov 2>/dev/null | grep -oP 'INTEGER: \K\d+' || echo "?"
}

_resolve_node() {
  local node="$1"
  local ip="${NODE_PDU_IP[$node]:-}"
  local outlet="${NODE_PDU_OUTLET[$node]:-}"
  local pdu="${NODE_PDU_NAME[$node]:-}"
  if [[ -z "$ip" || -z "$outlet" ]]; then
    echo "error: unknown node '$node'. Valid: ${!NODE_PDU_IP[*]}" >&2
    exit 1
  fi
  echo "$ip $outlet $pdu"
}

_state_name() {
  case "$1" in
    1) echo "ON" ;;
    2) echo "OFF" ;;
    3) echo "REBOOT" ;;
    4) echo "CANCEL" ;;
    ?) echo "UNKNOWN" ;;
    *) echo "STATE-$1" ;;
  esac
}

cmd_on() {
  local node="${1:?Usage: on <node>}"
  read -r ip outlet pdu <<< "$(_resolve_node "$node")"
  echo "Powering ON $node ($pdu outlet $outlet @ $ip)..."
  _snmp_set "$ip" "$outlet" 1
  echo "  OK: power on command sent"
}

cmd_off() {
  local node="${1:?Usage: off <node>}"
  read -r ip outlet pdu <<< "$(_resolve_node "$node")"
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  WARNING: This will power OFF $node                     ║"
  echo "║  PDU: $pdu outlet $outlet ($ip)                         ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  if command -v gum >/dev/null 2>&1; then
    gum confirm "Power off $node?" --default="No" || exit 0
  else
    read -rp "Power off $node? (y/N) " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
  fi
  _snmp_set "$ip" "$outlet" 2
  echo "  OK: power off command sent"
}

cmd_reboot() {
  local node="${1:?Usage: reboot <node>}"
  read -r ip outlet pdu <<< "$(_resolve_node "$node")"
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  Power cycling $node (off→on)                           ║"
  echo "║  PDU: $pdu outlet $outlet ($ip)                         ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  if command -v gum >/dev/null 2>&1; then
    gum confirm "Power cycle $node?" --default="No" || exit 0
  else
    read -rp "Power cycle $node? (y/N) " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
  fi
  _snmp_set "$ip" "$outlet" 3
  echo "  OK: reboot command sent"
}

cmd_status() {
  local node="${1:-}"
  if [[ -n "$node" ]]; then
    read -r ip outlet pdu <<< "$(_resolve_node "$node")"
    local state
    state=$(_snmp_get "$ip" "$outlet")
    echo "$node ($pdu outlet $outlet): $(_state_name "$state")"
    return
  fi
  # Show all outlets
  echo "=== pdu01 (192.168.99.15) ==="
  for n in k8s01 k8s02 k8s03 nas01 core01-u1 fw01; do
    read -r ip outlet pdu <<< "$(_resolve_node "$n")"
    local state
    state=$(_snmp_get "$ip" "$outlet")
    printf "  outlet %-2s %-12s %s\n" "$outlet" "$n" "$(_state_name "$state")"
  done
  echo "=== pdu02 (192.168.99.16) ==="
  for n in k8s04 k8s05 k8s06 nas01-psu2 core01-u2; do
    read -r ip outlet pdu <<< "$(_resolve_node "$n")"
    local state
    state=$(_snmp_get "$ip" "$outlet")
    printf "  outlet %-2s %-12s %s\n" "$outlet" "$n" "$(_state_name "$state")"
  done
}

# Dispatch
case "${1:-help}" in
  on)     shift; cmd_on "$@" ;;
  off)    shift; cmd_off "$@" ;;
  reboot) shift; cmd_reboot "$@" ;;
  status) shift; cmd_status "$@" ;;
  help|--help|-h)
    head -15 "$0" | grep '^#' | sed 's/^# \?//'
    ;;
  *)
    echo "error: unknown command '$1'. Run with --help for usage." >&2
    exit 1
    ;;
esac
