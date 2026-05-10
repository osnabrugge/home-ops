set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

scripts_dir := justfile_dir() + '/scripts'

[private]
default:
    just -l infra

# ──────────────────────────────────────────────────────────────────────────────
# KVM — PiKVM + TESmart HDMI Switch
# ──────────────────────────────────────────────────────────────────────────────

[doc('Switch KVM to a node (nas01, k8s01-06, pi01-04, pve01, fw01)')]
kvm-switch node:
    bash "{{ scripts_dir }}/infra-pikvm.sh" switch "{{ node }}"

[doc('Send Wake-on-LAN to a node via PiKVM')]
wol node:
    bash "{{ scripts_dir }}/infra-pikvm.sh" wol "{{ node }}"

[doc('Show which KVM port is active')]
kvm-active:
    bash "{{ scripts_dir }}/infra-pikvm.sh" active

[doc('Take a KVM screenshot (optionally with OCR)')]
kvm-screenshot *args:
    bash "{{ scripts_dir }}/infra-pikvm.sh" snapshot {{ args }}

[doc('OCR the current KVM screen')]
kvm-ocr:
    bash "{{ scripts_dir }}/infra-pikvm.sh" ocr

[doc('Show PiKVM system info')]
kvm-info:
    bash "{{ scripts_dir }}/infra-pikvm.sh" info

[doc('Show PiKVM GPIO state (TESmart ports)')]
kvm-gpio:
    bash "{{ scripts_dir }}/infra-pikvm.sh" gpio

# ──────────────────────────────────────────────────────────────────────────────
# PDU — CyberPower PDU41001 Power Control (SNMP)
# ──────────────────────────────────────────────────────────────────────────────

[doc('Power on a node via PDU')]
pdu-on node:
    bash "{{ scripts_dir }}/infra-pdu.sh" on "{{ node }}"

[doc('Power off a node via PDU (DANGEROUS — requires confirmation)')]
pdu-off node:
    bash "{{ scripts_dir }}/infra-pdu.sh" off "{{ node }}"

[doc('Power cycle a node via PDU (requires confirmation)')]
pdu-reboot node:
    bash "{{ scripts_dir }}/infra-pdu.sh" reboot "{{ node }}"

[doc('Show PDU outlet status (all outlets or specific node)')]
pdu-status *node:
    bash "{{ scripts_dir }}/infra-pdu.sh" status {{ node }}

# ──────────────────────────────────────────────────────────────────────────────
# Compound operations
# ──────────────────────────────────────────────────────────────────────────────

[doc('Hard reboot a k8s node: PDU power cycle + wait for maintenance port')]
hard-reboot node:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Hard rebooting {{ node }} via PDU power cycle..."
    bash "{{ scripts_dir }}/infra-pdu.sh" reboot "{{ node }}"
    echo ""
    echo "Waiting for {{ node }} to come back on maintenance port 50000..."
    # Derive IP from node name
    declare -A node_ips=(
      [k8s01]=192.168.42.51 [k8s02]=192.168.42.52 [k8s03]=192.168.42.53
      [k8s04]=192.168.42.54 [k8s05]=192.168.42.55 [k8s06]=192.168.42.56
    )
    ip="${node_ips[{{ node }}]:-}"
    if [[ -z "$ip" ]]; then
      echo "  No IP mapping for {{ node }}, skipping wait"
      exit 0
    fi
    retries=0
    max_retries=60
    while [[ $retries -lt $max_retries ]]; do
      if timeout 3 bash -c "echo >/dev/tcp/$ip/50000" 2>/dev/null; then
        echo "  OK: {{ node }} ($ip) is back on port 50000"
        exit 0
      fi
      retries=$((retries + 1))
      if (( retries % 10 == 0 )); then
        echo "  Waiting... (${retries}/${max_retries})"
      fi
      sleep 5
    done
    echo "  WARN: {{ node }} did not come back within $((max_retries * 5))s"

[doc('View KVM console for a node: switch KVM + take screenshot')]
console node:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Switching KVM to {{ node }}..."
    bash "{{ scripts_dir }}/infra-pikvm.sh" switch "{{ node }}"
    sleep 2
    echo "Taking screenshot..."
    outfile="{{ justfile_dir() }}/.private/screenshots/{{ node }}-$(date +%Y%m%d-%H%M%S).jpg"
    mkdir -p "$(dirname "$outfile")"
    bash "{{ scripts_dir }}/infra-pikvm.sh" snapshot "$outfile"
    echo "  Screenshot saved: $outfile"
