#!/usr/bin/env bash
set -euo pipefail

# PiKVM + TESmart KVM Switch Helper
#
# Usage:
#   scripts/infra-pikvm.sh <command> [args...]
#
# Commands:
#   switch <node>         Switch TESmart to the specified node's HDMI port
#   wol <node>            Send Wake-on-LAN to a node via PiKVM GPIO
#   snapshot [file]       Take a screenshot of the currently selected KVM port
#   ocr                   Take a screenshot and OCR the text on screen
#   info                  Show PiKVM system info
#   gpio                  Show GPIO state (TESmart port status)
#   active                Show which TESmart port is currently active
#
# Environment:
#   PIKVM_HOST            PiKVM hostname (default: kvm01.in.homeops.ca)
#   PIKVM_USER            PiKVM username (default: admin)
#   PIKVM_PASS            PiKVM password (required, or set in .private/pikvm.env)
#
# TESmart Port Mapping (from PiKVM override.yaml):
#   Pin 0  = nas01    Pin 1  = k8s01    Pin 2  = k8s02
#   Pin 3  = k8s03    Pin 4  = k8s04    Pin 5  = k8s05
#   Pin 6  = k8s06    Pin 7  = pi01     Pin 8  = pi02
#   Pin 9  = pi03     Pin 10 = pi04     Pin 11 = pve01
#   Pin 12 = fw01

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Load credentials from .private/pikvm.env if it exists
if [[ -f "$ROOT_DIR/.private/pikvm.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.private/pikvm.env"
fi

PIKVM_HOST="${PIKVM_HOST:-kvm01.in.homeops.ca}"
PIKVM_USER="${PIKVM_USER:-admin}"
PIKVM_PASS="${PIKVM_PASS:-}"

if [[ -z "$PIKVM_PASS" ]]; then
  echo "error: PIKVM_PASS not set. Set it in environment or .private/pikvm.env" >&2
  exit 1
fi

# curl wrapper with PiKVM auth
_pikvm() {
  local method="$1" path="$2"
  shift 2
  curl -sk -X "$method" \
    -H "X-KVMD-User:${PIKVM_USER}" \
    -H "X-KVMD-Passwd:${PIKVM_PASS}" \
    "https://${PIKVM_HOST}/api${path}" \
    "$@"
}

# Node-to-TESmart-pin mapping
declare -A NODE_PIN=(
  [nas01]=0
  [k8s01]=1  [k8s02]=2  [k8s03]=3
  [k8s04]=4  [k8s05]=5  [k8s06]=6
  [pi01]=7   [pi02]=8   [pi03]=9   [pi04]=10
  [pve01]=11 [fw01]=12
)

# Node-to-WoL-GPIO-channel mapping (matches PiKVM override scheme names)
declare -A NODE_WOL_CHANNEL=(
  [k8s01]=server1_wol  [k8s02]=server2_wol  [k8s03]=server3_wol
  [k8s04]=server4_wol  [k8s05]=server5_wol  [k8s06]=server6_wol
  [pi01]=server7_wol   [pi02]=server8_wol   [pi03]=server9_wol   [pi04]=server10_wol
  [pve01]=server11_wol [fw01]=server12_wol
)

# Node-to-TESmart-switch-channel mapping
declare -A NODE_SWITCH_CHANNEL=(
  [nas01]=server0_switch
  [k8s01]=server1_switch  [k8s02]=server2_switch  [k8s03]=server3_switch
  [k8s04]=server4_switch  [k8s05]=server5_switch  [k8s06]=server6_switch
  [pi01]=server7_switch   [pi02]=server8_switch   [pi03]=server9_switch   [pi04]=server10_switch
  [pve01]=server11_switch [fw01]=server12_switch
)

cmd_switch() {
  local node="${1:?Usage: switch <node>}"
  local channel="${NODE_SWITCH_CHANNEL[$node]:-}"
  if [[ -z "$channel" ]]; then
    echo "error: unknown node '$node'. Valid: ${!NODE_SWITCH_CHANNEL[*]}" >&2
    exit 1
  fi
  echo "Switching KVM to $node (channel=$channel)..."
  # TESmart channels are pulse-mode (switch: false in PiKVM config), not toggle
  _pikvm POST "/gpio/pulse?channel=${channel}&delay=0&wait=1"
  echo ""
  echo "  KVM switched to $node"
}

cmd_wol() {
  local node="${1:?Usage: wol <node>}"
  local channel="${NODE_WOL_CHANNEL[$node]:-}"
  if [[ -z "$channel" ]]; then
    echo "error: unknown node '$node' or no WoL configured. Valid: ${!NODE_WOL_CHANNEL[*]}" >&2
    exit 1
  fi
  echo "Sending Wake-on-LAN to $node (channel=$channel)..."
  _pikvm POST "/gpio/pulse?channel=${channel}&delay=0&wait=1"
  echo ""
  echo "  WoL sent to $node"
}

cmd_snapshot() {
  local outfile="${1:-/dev/stdout}"
  if [[ "$outfile" == "/dev/stdout" ]]; then
    echo "Taking snapshot (outputting to stdout)..." >&2
    _pikvm GET "/streamer/snapshot?save=1"
  else
    echo "Taking snapshot → $outfile"
    _pikvm GET "/streamer/snapshot?save=1" -o "$outfile"
    echo "  Saved to $outfile"
  fi
}

cmd_ocr() {
  echo "Taking screenshot and running OCR..."
  local text
  text=$(_pikvm GET "/streamer/snapshot?ocr=true&ocr_langs=eng")
  echo "$text"
}

cmd_info() {
  _pikvm GET "/info?fields=system,hw" | jq .
}

cmd_gpio() {
  _pikvm GET "/gpio" | jq .
}

cmd_active() {
  local gpio_state
  gpio_state=$(_pikvm GET "/gpio")
  # Find which server LED is active (the TESmart reports active port via LED inputs)
  echo "TESmart port status:"
  for node in nas01 k8s01 k8s02 k8s03 k8s04 k8s05 k8s06 pi01 pi02 pi03 pi04 pve01 fw01; do
    local pin="${NODE_PIN[$node]}"
    local led_channel="server${pin}_led"
    local state
    state=$(echo "$gpio_state" | jq -r --arg ch "$led_channel" '.result.state.inputs[$ch].state // "unknown"')
    if [[ "$state" == "true" || "$state" == "1" ]]; then
      echo "  $node (pin $pin): ACTIVE ◀"
    else
      echo "  $node (pin $pin): -"
    fi
  done
}

# Dispatch
case "${1:-help}" in
  switch)   shift; cmd_switch "$@" ;;
  wol)      shift; cmd_wol "$@" ;;
  snapshot) shift; cmd_snapshot "$@" ;;
  ocr)      shift; cmd_ocr "$@" ;;
  info)     shift; cmd_info ;;
  gpio)     shift; cmd_gpio ;;
  active)   shift; cmd_active ;;
  help|--help|-h)
    head -20 "$0" | grep '^#' | sed 's/^# \?//'
    ;;
  *)
    echo "error: unknown command '$1'. Run with --help for usage." >&2
    exit 1
    ;;
esac
