set no-exit-message
set quiet
set script-interpreter := ['bash', '-euo', 'pipefail']
set shell := ['bash', '-euo', 'pipefail', '-c']

scripts_dir := justfile_dir() + '/scripts'

[private]
default:
    just -l infra

# ──────────────────────────────────────────────────────────────────────────────
# KVM — PiKVM + TESmart HDMI Switch
# ──────────────────────────────────────────────────────────────────────────────
[script]
[doc('Switch KVM to a node (nas01, k8s01-06, pi01-04, pve01, fw01)')]
kvm-switch node:
    {{ scripts_dir }}/infra-pikvm.sh switch {{ node }}

[script]
[doc('Send Wake-on-LAN to a node via PiKVM')]
wol node:
    {{ scripts_dir }}/infra-pikvm.sh wol {{ node }}

[script]
[doc('Show which KVM port is active')]
kvm-active:
    {{ scripts_dir }}/infra-pikvm.sh active

[script]
[doc('Take a KVM screenshot (optionally with OCR)')]
kvm-screenshot *args:
    {{ scripts_dir }}/infra-pikvm.sh snapshot {{ args }}

[script]
[doc('OCR the current KVM screen')]
kvm-ocr:
    {{ scripts_dir }}/infra-pikvm.sh ocr

[script]
[doc('Show PiKVM system info')]
kvm-info:
    {{ scripts_dir }}/infra-pikvm.sh info

[script]
[doc('Show PiKVM GPIO state (TESmart ports)')]
kvm-gpio:
    {{ scripts_dir }}/infra-pikvm.sh gpio

# ──────────────────────────────────────────────────────────────────────────────
# PDU — CyberPower PDU41001 Power Control (SNMP)
# ──────────────────────────────────────────────────────────────────────────────

[script]
[doc('Power on a node via PDU')]
pdu-on node:
    {{ scripts_dir }}/infra-pdu.sh on {{ node }}

[script]
[confirm('Power off a node via PDU' + node + ' [y|N] ?')]
[doc('Power off a node via PDU (DANGEROUS — requires confirmation)')]
pdu-off node:
    {{ scripts_dir }}/infra-pdu.sh off {{ node }}

[script]
[confirm('Power cycle a node via PDU' + node + ' [y|N] ?')]
[doc('Power cycle a node via PDU (requires confirmation)')]
pdu-reboot node:
    {{ scripts_dir }}/infra-pdu.sh reboot {{ node }}

[script]
[doc('Show PDU outlet status (all outlets or specific node)')]
pdu-status *node:
    {{ scripts_dir }}/infra-pdu.sh status {{ node }}

# ──────────────────────────────────────────────────────────────────────────────
# Compound operations
# ──────────────────────────────────────────────────────────────────────────────

[script]
[confirm('Hard reboot a node: power cycle via PDU + wait for maintenance port' + node + ' [y|N] ?')]
[doc('Hard reboot a k8s node: PDU power cycle + wait for maintenance port')]
hard-reboot node:
    echo "Hard rebooting {{ node }} via PDU power cycle..."
    {{ scripts_dir }}/infra-pdu.sh reboot {{ node }}
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

[script]
[doc('View KVM console for a node: switch KVM + take screenshot')]
console node:
    echo "Switching KVM to {{ node }}..."
    {{ scripts_dir }}/infra-pikvm.sh switch {{ node }}
    sleep 2
    echo "Taking screenshot..."
    outfile="{{ justfile_dir() }}/.private/screenshots/{{ node }}-$(date +%Y%m%d-%H%M%S).jpg"
    mkdir -p "$(dirname "$outfile")"
    {{ scripts_dir }}/infra-pikvm.sh snapshot "$outfile"
    echo "  Screenshot saved: $outfile"
