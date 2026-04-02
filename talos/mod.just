set quiet := true
set shell := ['bash', '-euo', 'pipefail', '-c']

scripts_dir := justfile_dir() + '/scripts'
talos_dir := justfile_dir() + '/talos'
rendered_dir := talos_dir + '/rendered'

# Control-plane nodes (order matters: first node is bootstrap target)
cp_nodes := "k8s01 k8s02 k8s03"
# Expected IPs for control-plane nodes (must match cp_nodes order)
cp_ips := "192.168.42.51 192.168.42.52 192.168.42.53"
# Bootstrap endpoint: first CP node IP (no DNS/VIP dependency)
bootstrap_ip := "192.168.42.51"

# First configured endpoint from talosctl (or empty if talosctl not configured yet)
controller := `talosctl config info -o yaml 2>/dev/null | yq -r '.endpoints[0] // ""' 2>/dev/null || true`

[private]
default:
    just -l talos

# ──────────────────────────────────────────────────────────────────────────────
# Existing day-2 operations
# ──────────────────────────────────────────────────────────────────────────────

[doc('Apply Talos config to a node')]
apply-node node *args:
    just talos render-config "{{ node }}" | talosctl -n "{{ node }}" apply-config -f /dev/stdin {{ args }}

[doc('Download Talos machine image')]
download-image version schematic:
    gum spin --title "Downloading Talos {{ version }} ..." -- \
    curl -sfL --remove-on-error --retry 5 --retry-delay 5 --retry-all-errors \
        -o "{{ talos_dir }}/talos-{{ version }}-{{ replace_regex(schematic, '^(.{8}).*', '$1') }}.iso" \
        "https://factory.talos.dev/image/{{ schematic }}/{{ version }}/metal-amd64.iso"
    just log info "Downloaded Talos" version "{{ version }}" schematic "{{ schematic }}"

[doc('Generate schematic ID from Talos schematic')]
gen-schematic-id:
    curl -sX POST --data-binary @<(just template "{{ talos_dir }}/schematic.yaml.j2") "https://factory.talos.dev/schematics" | jq -r '.id'

[doc('Reboot a node')]
reboot-node node:
    gum confirm "Reboot node {{ node }}?" --default="No" && \
        talosctl -n {{ node }} reboot -m powercycle || exit 0

[doc('Render Talos config for a node')]
render-config node:
    export IS_CONTROLLER="$(just talos machine-controller {{ node }} | tr -d '\n')"; \
    talosctl machineconfig patch <(just template "{{ talos_dir }}/machineconfig.yaml.j2") \
        -p @<(just template "{{ talos_dir }}/nodes/{{ node }}.yaml.j2")

[doc('Reset a node')]
reset-node node *args:
    gum confirm "Reset node {{ node }}?" --default="No" && \
        talosctl -n "{{ node }}" reset --system-labels-to-wipe STATE --system-labels-to-wipe EPHEMERAL --system-labels-to-wipe u-local-hostpath --graceful=false {{ args }} || exit 0

[doc('Shutdown a node')]
shutdown-node node *args:
    gum confirm "Shutdown node {{ node }}?" --default="No" && \
        talosctl -n "{{ node }}" shutdown --force {{ args }} || exit 0

[doc('Upgrade Kubernetes version on the cluster')]
upgrade-k8s version:
    talosctl -n "{{ controller }}" upgrade-k8s --to {{ version }}

[doc('Upgrade Talos version on a node')]
upgrade-node node *args:
    talosctl -n "{{ node }}" upgrade -i "$(just talos machine-image)" -m powercycle --timeout=10m {{ args }}

[private]
machine-controller node:
    just template "{{ talos_dir }}/nodes/{{ node }}.yaml.j2" \
      | yq -r 'select(.machine) | .machine.type // ""' \
      | grep -qx 'controlplane' && echo true || true

[private]
machine-image:
    just template "{{ talos_dir }}/machineconfig.yaml.j2" | yq -r 'select(.machine) | .machine.install.image // ""'

# ──────────────────────────────────────────────────────────────────────────────
# Rebuild / bootstrap automation
# ──────────────────────────────────────────────────────────────────────────────

[doc('Full rebuild: preflight → render → apply → bootstrap → verify')]
rebuild:
    just log info "Starting full control-plane rebuild"
    just talos preflight
    just talos render
    just talos apply
    just talos bootstrap
    just talos verify
    just log info "Rebuild complete — control plane is healthy"

[doc('Preflight: verify AKV access, az login, node maintenance, tooling')]
preflight:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "── Preflight checks ──"
    fail=0
    # 1. Required tools
    for cmd in talosctl minijinja-cli yq jq az gum; do
      if ! command -v "$cmd" &>/dev/null; then
        echo "FAIL: $cmd not found in PATH"; fail=1
      else
        echo "  OK: $cmd found"
      fi
    done
    # 2. Azure CLI login
    if ! az account show -o none 2>/dev/null; then
      echo "FAIL: az CLI not logged in — run 'az login'"; fail=1
    else
      echo "  OK: az CLI authenticated ($(az account show --query name -o tsv))"
    fi
    # 3. AKV secret accessible
    if ! az keyvault secret show --vault-name keyvault-kube --name talos --query "value" -o tsv 2>/dev/null | jq -e 'keys | length > 0' >/dev/null 2>&1; then
      echo "FAIL: Cannot read talos secret from keyvault-kube"; fail=1
    else
      key_count=$(az keyvault secret show --vault-name keyvault-kube --name talos --query "value" -o tsv | jq 'keys | length')
      echo "  OK: AKV keyvault-kube/talos accessible ($key_count keys)"
    fi
    # 4. Control-plane nodes reachable on maintenance port 50000
    IFS=' ' read -ra nodes <<< "{{ cp_ips }}"
    IFS=' ' read -ra names <<< "{{ cp_nodes }}"
    for i in "${!nodes[@]}"; do
      ip="${nodes[$i]}"
      name="${names[$i]}"
      if timeout 3 bash -c "echo >/dev/tcp/$ip/50000" 2>/dev/null; then
        echo "  OK: $name ($ip) maintenance port 50000 open"
      else
        echo "FAIL: $name ($ip) maintenance port 50000 not reachable — is node booted from Talos ISO?"
        fail=1
      fi
    done
    # 5. Verify render pipeline works (dry run on first node)
    IFS=' ' read -ra names <<< "{{ cp_nodes }}"
    first="${names[0]}"
    if rendered=$(just talos render-config "$first" 2>&1); then
      doc_count=$(echo "$rendered" | yq ea '[.] | length')
      if talosctl validate --config <(echo "$rendered") --mode metal >/dev/null 2>&1; then
        echo "  OK: render pipeline works ($doc_count documents, valid)"
      else
        echo "FAIL: rendered config for $first fails validation"; fail=1
      fi
    else
      echo "FAIL: render pipeline failed for $first: $rendered"; fail=1
    fi
    if [[ "$fail" -ne 0 ]]; then
      echo ""
      echo "PREFLIGHT FAILED — fix the issues above before proceeding."
      exit 1
    fi
    echo ""
    echo "All preflight checks passed."

[doc('Render configs for all CP nodes to talos/rendered/')]
render:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{ rendered_dir }}"
    IFS=' ' read -ra nodes <<< "{{ cp_nodes }}"
    IFS=' ' read -ra ips <<< "{{ cp_ips }}"
    # Build the bootstrap endpoint patch (IP-based, no DNS/VIP)
    bootstrap_patch=$(cat <<'PATCH'
    cluster:
      controlPlane:
        endpoint: https://{{ bootstrap_ip }}:6443
      apiServer:
        certSANs:
          - 192.168.42.51
          - 192.168.42.52
          - 192.168.42.53
          - 192.168.69.120
          - k8s.in.homeops.ca
    PATCH
    )
    for i in "${!nodes[@]}"; do
      node="${nodes[$i]}"
      ip="${ips[$i]}"
      outfile="{{ rendered_dir }}/${node}.yaml"
      echo "Rendering $node → $outfile"
      # Render base config with AKV secrets, then patch bootstrap endpoint
      just talos render-config "$node" \
        | talosctl machineconfig patch /dev/stdin \
            -p @<(printf '%s' "$bootstrap_patch") \
        > "$outfile"
      # ── Post-render guardrails ──
      # 1. FAIL if any azkv:// placeholder was not resolved
      if grep -qF 'azkv://' "$outfile"; then
        echo "FAIL: $outfile contains unresolved azkv:// placeholders:"
        grep -n 'azkv://' "$outfile" >&2
        exit 1
      fi
      # 2. FAIL if orphan suffix artifacts remain (partial replacement corruption)
      if grep -qE '(^|[^A-Z_])BOXENCRYPTIONSECRET|AGGREGATORCA_|SERVICEACCOUNT_KEY' "$outfile"; then
        echo "FAIL: $outfile contains orphan key suffix artifacts — likely partial placeholder replacement:"
        grep -nE '(^|[^A-Z_])BOXENCRYPTIONSECRET|AGGREGATORCA_|SERVICEACCOUNT_KEY' "$outfile" >&2
        exit 1
      fi
      # 3. FAIL if critical secret fields resolved empty
      for check_path in \
        'select(has("machine")) | .machine.ca.crt' \
        'select(has("machine")) | .machine.ca.key' \
        'select(has("machine")) | .machine.token' \
        'select(has("cluster")) | .cluster.ca.crt' \
        'select(has("cluster")) | .cluster.ca.key' \
        'select(has("cluster")) | .cluster.secret' \
        'select(has("cluster")) | .cluster.secretboxEncryptionSecret' \
        'select(has("cluster")) | .cluster.token'; do
        val=$(yq ea "$check_path" "$outfile" 2>/dev/null | head -1)
        if [[ -z "$val" || "$val" == "null" ]]; then
          echo "FAIL: $outfile has empty/null value at: $check_path"
          exit 1
        fi
      done
      # Validate with talosctl
      if ! talosctl validate --config "$outfile" --mode metal; then
        echo "FAIL: $outfile did not pass validation"
        exit 1
      fi
      # Show key facts
      endpoint=$(yq ea 'select(has("cluster")) | .cluster.controlPlane.endpoint' "$outfile")
      hostname=$(yq ea 'select(has("machine")) | .machine.network.hostname' "$outfile")
      machine_type=$(yq ea 'select(has("machine")) | .machine.type' "$outfile")
      echo "  hostname=$hostname type=$machine_type endpoint=$endpoint"
      echo "  OK: all guardrails passed for $node"
    done
    echo ""
    echo "All configs rendered and validated in {{ rendered_dir }}/"

[doc('Apply rendered configs to CP nodes in maintenance')]
apply:
    #!/usr/bin/env bash
    set -euo pipefail
    IFS=' ' read -ra nodes <<< "{{ cp_nodes }}"
    IFS=' ' read -ra ips <<< "{{ cp_ips }}"
    for i in "${!nodes[@]}"; do
      node="${nodes[$i]}"
      ip="${ips[$i]}"
      config="{{ rendered_dir }}/${node}.yaml"
      if [[ ! -f "$config" ]]; then
        echo "FAIL: $config not found — run 'just talos render' first"
        exit 1
      fi
      # Verify node is in maintenance (port 50000 open)
      if ! timeout 3 bash -c "echo >/dev/tcp/$ip/50000" 2>/dev/null; then
        echo "FAIL: $node ($ip) maintenance port 50000 not reachable"
        exit 1
      fi
      echo "Applying config to $node ($ip) ..."
      talosctl apply-config --nodes "$ip" --endpoints "$ip" --insecure --file "$config"
      echo "  Config applied to $node"
      # ── Deterministic wait: detect reboot then confirm apid comes back ──
      # Phase 1: Wait for node to start rebooting (port 50000 drops)
      echo "  Waiting for $node to begin reboot..."
      sleep 5
      reboot_detected=false
      for attempt in $(seq 1 30); do
        if ! timeout 2 bash -c "echo >/dev/tcp/$ip/50000" 2>/dev/null; then
          reboot_detected=true
          echo "  $node is rebooting (port 50000 closed)"
          break
        fi
        sleep 2
      done
      if [[ "$reboot_detected" == false ]]; then
        echo "  WARN: $node port 50000 never closed — node may not have rebooted"
        echo "  Proceeding to check apid anyway..."
      fi
      # Phase 2: Wait for apid to come back (port 50000 reopens with new TLS)
      # Use --insecure since we don't have a talosconfig matching these new secrets yet
      echo "  Waiting for $node apid to respond..."
      retries=0
      max_retries=60
      while [[ $retries -lt $max_retries ]]; do
        if talosctl version --nodes "$ip" --endpoints "$ip" --insecure 2>/dev/null | grep -q "Tag:"; then
          echo "  OK: $node ($ip) is running and apid is responding"
          break
        fi
        retries=$((retries + 1))
        if (( retries % 10 == 0 )); then
          echo "  Still waiting for $node apid... (${retries}/${max_retries})"
        fi
        sleep 5
      done
      if [[ $retries -ge $max_retries ]]; then
        echo "FAIL: $node ($ip) apid did not respond after $((max_retries * 5))s"
        echo ""
        echo "── Collecting diagnostic logs for $node ──"
        echo "--- machined ---"
        talosctl logs machined --nodes "$ip" --endpoints "$ip" --insecure 2>&1 | tail -50 || true
        echo "--- installer ---"
        talosctl logs installer --nodes "$ip" --endpoints "$ip" --insecure 2>&1 | tail -30 || true
        echo "--- network addresses ---"
        talosctl get addresses --nodes "$ip" --endpoints "$ip" --insecure 2>&1 || true
        echo ""
        echo "FAIL: $node did not transition to running. Stopping."
        exit 1
      fi
    done
    echo ""
    echo "All CP nodes configured and running."

[doc('Bootstrap etcd + Kubernetes on first CP node')]
bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail
    bootstrap_ip="{{ bootstrap_ip }}"
    marker="{{ justfile_dir() }}/.private/bootstrap.done"
    # Guard against accidental double-bootstrap
    if [[ -f "$marker" ]]; then
      echo "╔══════════════════════════════════════════════════════════╗"
      echo "║  WARNING: Bootstrap marker exists ($marker)             ║"
      echo "║  Last bootstrap: $(cat "$marker")                       ║"
      echo "║  Re-bootstrapping can corrupt etcd.                     ║"
      echo "╚══════════════════════════════════════════════════════════╝"
      gum confirm "Bootstrap has already run. Proceed anyway?" --default="No" || exit 0
    fi
    echo "Bootstrapping Kubernetes on $bootstrap_ip..."
    # Wait for etcd to be ready for bootstrap
    retries=0
    max_retries=24
    while [[ $retries -lt $max_retries ]]; do
      result=$(talosctl bootstrap --nodes "$bootstrap_ip" --endpoints "$bootstrap_ip" --insecure 2>&1 || true)
      if [[ $? -eq 0 && ! "$result" =~ "rpc error" ]] || echo "$result" | grep -q "AlreadyExists"; then
        if echo "$result" | grep -q "AlreadyExists"; then
          echo "  Bootstrap already done (AlreadyExists)"
        else
          echo "  Bootstrap command accepted"
        fi
        break
      fi
      retries=$((retries + 1))
      echo "  Bootstrap not ready yet, retrying in 10s... (${retries}/${max_retries})"
      if (( retries % 6 == 0 )); then
        echo "  Last error: $result"
      fi
      sleep 10
    done
    if [[ $retries -ge $max_retries ]]; then
      echo "FAIL: Bootstrap did not succeed after $((max_retries * 10))s"
      echo "  Last result: $result"
      exit 1
    fi
    # Write bootstrap marker
    mkdir -p "$(dirname "$marker")"
    date -Iseconds > "$marker"
    echo "  Bootstrap marker written: $marker"
    echo ""
    echo "Bootstrap initiated. Waiting for Kubernetes API..."
    # Fetch kubeconfig (use --insecure since talosconfig may not match new secrets)
    sleep 10
    talosctl kubeconfig --nodes "$bootstrap_ip" --endpoints "$bootstrap_ip" \
      --insecure \
      --force --force-context-name main "{{ justfile_dir() }}"
    echo "  kubeconfig written to {{ justfile_dir() }}/kubeconfig"
    # Point kubeconfig to the bootstrap IP (not DNS)
    kubectl config set-cluster main --server "https://$bootstrap_ip:6443" --kubeconfig "{{ justfile_dir() }}/kubeconfig"
    echo "  kubeconfig cluster server set to https://$bootstrap_ip:6443"

[doc('Verify cluster health after bootstrap')]
verify:
    #!/usr/bin/env bash
    set -euo pipefail
    export KUBECONFIG="{{ justfile_dir() }}/kubeconfig"
    echo "── Cluster health checks ──"
    # 1. Nodes
    echo ""
    echo "Nodes:"
    retries=0
    while [[ $retries -lt 30 ]]; do
      if kubectl get nodes 2>/dev/null | grep -q "Ready"; then
        kubectl get nodes -o wide
        break
      fi
      retries=$((retries + 1))
      echo "  Waiting for nodes to appear... (${retries}/30)"
      sleep 10
    done
    if [[ $retries -ge 30 ]]; then
      echo "FAIL: No nodes became Ready after 300s"
      exit 1
    fi
    # 2. Etcd members
    echo ""
    echo "Etcd members:"
    talosctl etcd members --nodes "{{ bootstrap_ip }}" --endpoints "{{ bootstrap_ip }}" \
      --insecure 2>&1 || true
    # 3. System pods
    echo ""
    echo "System pods:"
    kubectl get pods -A 2>/dev/null || true
    # 4. Talos service health on all CP nodes
    echo ""
    echo "Talos services:"
    IFS=' ' read -ra ips <<< "{{ cp_ips }}"
    for ip in "${ips[@]}"; do
      echo "  --- $ip ---"
      talosctl service --nodes "$ip" --endpoints "$ip" \
        --insecure 2>&1 | grep -E "STATE|Running|Finished" || true
    done
    echo ""
    echo "Cluster verification complete."

[doc('Wipe all CP nodes (DESTRUCTIVE — requires confirmation)')]
wipe-cp:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  DESTRUCTIVE: This will wipe ALL control-plane nodes    ║"
    echo "║  Nodes: {{ cp_nodes }}                              ║"
    echo "║  IPs:   {{ cp_ips }}                                ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    gum confirm "Proceed with wiping ALL control-plane nodes?" --default="No" || exit 0
    # Remove bootstrap marker so next bootstrap is clean
    rm -f "{{ justfile_dir() }}/.private/bootstrap.done"
    IFS=' ' read -ra ips <<< "{{ cp_ips }}"
    IFS=' ' read -ra names <<< "{{ cp_nodes }}"
    for i in "${!ips[@]}"; do
      ip="${ips[$i]}"
      name="${names[$i]}"
      echo "Resetting $name ($ip) ..."
      talosctl reset --nodes "$ip" --endpoints "$ip" \
        --insecure \
        --graceful=false --wipe-mode=all --reboot 2>&1 || true
      echo "  Reset sent to $name"
    done
    echo ""
    echo "All CP nodes reset. They will reboot into maintenance (ISO/PXE required)."
    echo "Wait for nodes to become available on port 50000 before proceeding."

[doc('Regenerate Talos secrets and upload to Azure Key Vault')]
rotate-secrets:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  This will generate NEW Talos secrets and upload them   ║"
    echo "║  to Azure Key Vault (keyvault-kube/talos).              ║"
    echo "║  The OLD secrets will be overwritten.                   ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    gum confirm "Generate and upload new Talos secrets?" --default="No" || exit 0
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' EXIT
    talosctl gen secrets -o "$tmpdir/secrets.yaml" --force
    echo "  Generated secrets bundle"
    # Convert talosctl secrets.yaml to the JSON format expected by AKV
    secrets_json=$(yq -r -o=json '.' "$tmpdir/secrets.yaml")
    # Build the AKV JSON payload mapping
    akv_json=$(jq -n \
      --arg MACHINE_CA_CRT    "$(echo "$secrets_json" | jq -r '.machine.ca.crt')" \
      --arg MACHINE_CA_KEY    "$(echo "$secrets_json" | jq -r '.machine.ca.key')" \
      --arg MACHINE_TOKEN     "$(echo "$secrets_json" | jq -r '.machine.token')" \
      --arg CLUSTER_CA_CRT    "$(echo "$secrets_json" | jq -r '.cluster.ca.crt')" \
      --arg CLUSTER_CA_KEY    "$(echo "$secrets_json" | jq -r '.cluster.ca.key')" \
      --arg CLUSTER_ID        "$(echo "$secrets_json" | jq -r '.cluster.id')" \
      --arg CLUSTER_SECRET    "$(echo "$secrets_json" | jq -r '.cluster.secret')" \
      --arg CLUSTER_TOKEN     "$(echo "$secrets_json" | jq -r '.cluster.bootstraptoken // .cluster.token')" \
      --arg CLUSTER_AGGREGATORCA_CRT "$(echo "$secrets_json" | jq -r '.cluster.aggregatorCA.crt // .cluster.aggregatorca.crt')" \
      --arg CLUSTER_AGGREGATORCA_KEY "$(echo "$secrets_json" | jq -r '.cluster.aggregatorCA.key // .cluster.aggregatorca.key')" \
      --arg CLUSTER_ETCD_CA_CRT "$(echo "$secrets_json" | jq -r '.cluster.etcd.crt // .cluster.etcd.ca.crt')" \
      --arg CLUSTER_ETCD_CA_KEY "$(echo "$secrets_json" | jq -r '.cluster.etcd.key // .cluster.etcd.ca.key')" \
      --arg CLUSTER_SECRETBOXENCRYPTIONSECRET "$(echo "$secrets_json" | jq -r '.cluster.secretboxEncryptionSecret // .cluster.secretboxencryptionsecret')" \
      --arg CLUSTER_SERVICEACCOUNT_KEY "$(echo "$secrets_json" | jq -r '.cluster.serviceAccount.key // .cluster.serviceaccount.key')" \
      '{
        MACHINE_CA_CRT: $MACHINE_CA_CRT,
        MACHINE_CA_KEY: $MACHINE_CA_KEY,
        MACHINE_TOKEN: $MACHINE_TOKEN,
        CLUSTER_CA_CRT: $CLUSTER_CA_CRT,
        CLUSTER_CA_KEY: $CLUSTER_CA_KEY,
        CLUSTER_ID: $CLUSTER_ID,
        CLUSTER_SECRET: $CLUSTER_SECRET,
        CLUSTER_TOKEN: $CLUSTER_TOKEN,
        CLUSTER_AGGREGATORCA_CRT: $CLUSTER_AGGREGATORCA_CRT,
        CLUSTER_AGGREGATORCA_KEY: $CLUSTER_AGGREGATORCA_KEY,
        CLUSTER_ETCD_CA_CRT: $CLUSTER_ETCD_CA_CRT,
        CLUSTER_ETCD_CA_KEY: $CLUSTER_ETCD_CA_KEY,
        CLUSTER_SECRETBOXENCRYPTIONSECRET: $CLUSTER_SECRETBOXENCRYPTIONSECRET,
        CLUSTER_SERVICEACCOUNT_KEY: $CLUSTER_SERVICEACCOUNT_KEY
      }')
    echo "  Uploading to keyvault-kube/talos ..."
    az keyvault secret set \
      --vault-name keyvault-kube \
      --name talos \
      --value "$akv_json" \
      -o none
    echo "  OK: Secrets uploaded to AKV"
    echo ""
    echo "New secrets are in AKV. Run 'just talos render' to generate new configs."

[doc('Export AKV secrets to .private/secrets/ for local/offline bootstrap')]
export-secrets:
    #!/usr/bin/env bash
    set -euo pipefail
    local_dir="{{ justfile_dir() }}/.private/secrets/keyvault-kube"
    mkdir -p "$local_dir"
    echo "Exporting AKV secrets to $local_dir/ ..."
    failed=0
    for secret_name in talos cloudflare; do
      outfile="$local_dir/${secret_name}.json"
      if ! value=$(az keyvault secret show --vault-name keyvault-kube --name "$secret_name" --query value -o tsv 2>&1); then
        echo "WARN: Could not read keyvault-kube/$secret_name from AKV — skipping"
        failed=$((failed + 1))
        continue
      fi
      printf '%s' "$value" > "$outfile"
      key_count=$(printf '%s' "$value" | jq 'keys | length' 2>/dev/null || echo "?")
      echo "  OK: keyvault-kube/$secret_name → $outfile ($key_count keys)"
    done
    # azurekv secret (ESO bootstrap credentials) — may not exist yet
    if value=$(az keyvault secret show --vault-name keyvault-kube --name azurekv --query value -o tsv 2>/dev/null); then
      printf '%s' "$value" > "$local_dir/azurekv.json"
      key_count=$(printf '%s' "$value" | jq 'keys | length' 2>/dev/null || echo "?")
      echo "  OK: keyvault-kube/azurekv → $local_dir/azurekv.json ($key_count keys)"
    else
      echo "  WARN: keyvault-kube/azurekv not found in AKV"
      echo "  This secret holds Azure SP credentials for External Secrets Operator."
      echo "  Create it with: az keyvault secret set --vault-name keyvault-kube --name azurekv --value '{\"AZURE_CLIENT_ID\":\"...\",\"AZURE_CLIENT_SECRET\":\"...\",\"AZURE_TENANT_ID\":\"...\"}'"
      failed=$((failed + 1))
    fi
    echo ""
    if [[ $failed -gt 0 ]]; then
      echo "$failed secret(s) could not be exported — see warnings above."
      echo "Local mode may not work for bootstrap resources until these are populated."
    fi
    echo "Secrets exported. To use local mode:"
    echo "  export AKV_LOCAL_DIR={{ justfile_dir() }}/.private/secrets"
    echo "  just talos render"
