# Talos Control-Plane Rebuild Runbook

> **Scope:** Rebuild a 3-node Talos control plane from scratch.
> **Talos:** v1.13.0 · **Kubernetes:** v1.36.0 · **Secrets:** Azure Key Vault (`keyvault-kube/talos`)

---

## Quick path (automated)

```bash
# Full rebuild — runs preflight → render → apply → bootstrap → verify
just talos rebuild
```

Or step-by-step:

```bash
just talos preflight   # Check tools, AKV, node reachability
just talos render       # Render + validate configs to talos/rendered/
just talos apply        # Apply configs to maintenance-mode nodes
just talos bootstrap    # Bootstrap etcd + K8s, fetch kubeconfig
just talos verify       # Health checks
```

---

## Detailed runbook

### Prerequisites

| Tool | Required version |
|------|-----------------|
| `talosctl` | v1.13.x |
| `minijinja-cli` | any |
| `yq` | v4.x (mikefarah) |
| `jq` | 1.6+ |
| `az` | 2.x (logged in) |
| `gum` | any |
| `kubectl` | v1.36.x |

### Node inventory

| Node | IP | MAC (bond member 1) | MAC (bond member 2) | Role |
|------|-----|---------------------|---------------------|------|
| k8s01 | 192.168.42.51 | 38:ea:a7:91:e3:9c | 38:ea:a7:91:e3:9d | controlplane |
| k8s02 | 192.168.42.52 | 8c:dc:d4:ac:7a:e8 | 8c:dc:d4:ac:7a:e9 | controlplane |
| k8s03 | 192.168.42.53 | 00:11:0a:68:bd:70 | 00:11:0a:68:bd:71 | controlplane |
| k8s04 | 192.168.42.54 | 38:ea:a7:90:4b:0c | 38:ea:a7:90:4b:0d | worker |
| k8s05 | 192.168.42.55 | (see template) | (see template) | worker |
| k8s06 | 192.168.42.56 | (see template) | (see template) | worker |

---

### Step 0: Wipe CP nodes (DESTRUCTIVE)

> **Only needed if nodes are running a previous Talos install. Skip if nodes are already in maintenance from ISO boot.**

```bash
just talos wipe-cp
```

This runs `talosctl reset --graceful=false --wipe-mode=all --reboot` on all 3 CP nodes.

After wipe, nodes **must** be booted from Talos ISO (USB/PXE). They will enter maintenance mode on port 50000.

**Checkpoint:** Wait until all 3 nodes respond on port 50000:
```bash
for ip in 192.168.42.51 192.168.42.52 192.168.42.53; do
  echo -n "$ip: " && timeout 3 bash -c "echo >/dev/tcp/$ip/50000" 2>/dev/null && echo "READY" || echo "NOT READY"
done
```
**Expected:** All three show `READY`.

**If a node shows NOT READY:**
- Check physical machine is powered on
- Check it has booted from a Talos ISO (not from empty disk)
- Check network cable / LACP bond / DHCP lease on 192.168.42.0/24
- The bond uses 802.3ad (LACP) — both NICs must be connected to a switch with LACP configured

---

### Step 1: Preflight

```bash
just talos preflight
```

**Expected output:** All checks show `OK`. If any show `FAIL`, fix the issue and re-run.

Checks performed:
- Required CLI tools present
- `az` CLI logged in
- AKV `keyvault-kube/talos` secret accessible (14 JSON keys)
- All CP nodes reachable on maintenance port 50000
- Render pipeline produces valid multi-doc YAML

---

### Step 2: Render configs

```bash
just talos render
```

**Expected output:**
```
Rendering k8s01 → .../talos/rendered/k8s01.yaml
.../talos/rendered/k8s01.yaml is valid for metal mode
  hostname=k8s01 type=controlplane endpoint=https://192.168.42.51:6443
(repeat for k8s02, k8s03)
All configs rendered and validated in .../talos/rendered/
```

**Key facts about what this does:**
1. Renders `machineconfig.yaml.j2` with `minijinja-cli`
2. Pipes through `akv-inject.sh` to replace all `azkv://keyvault-kube/talos#...` placeholders with real secrets (from AKV or local files if `AKV_LOCAL_DIR` is set)
3. Applies node-specific patch from `talos/nodes/<node>.yaml.j2` (hostname, MACs, type)
4. Applies bootstrap endpoint patch: `controlPlane.endpoint = https://192.168.42.51:6443` + IP-based certSANs
5. **Post-render guardrails:** Fails if any `azkv://` remains unresolved, if orphan suffix artifacts exist, or if critical secrets are empty
6. Validates with `talosctl validate --mode metal`

**Output:** `talos/rendered/{k8s01,k8s02,k8s03}.yaml` — these contain secrets and are gitignored.

**Checkpoint:** Verify no unresolved placeholders:
```bash
grep "azkv://" talos/rendered/*.yaml && echo "FAIL" || echo "OK: all secrets resolved"
```

---

### Step 3: Apply configs

```bash
just talos apply
```

This applies each rendered YAML to its respective node using:
```
talosctl apply-config --nodes <ip> --endpoints <ip> --insecure --file talos/rendered/<node>.yaml
```

After each apply, it waits for the node to leave maintenance and start apid (up to ~5 minutes).

**Expected output per node:**
```
Applying config to k8s01 (192.168.42.51) ...
  Config applied to k8s01
  Waiting for k8s01 to process config and start services...
  OK: k8s01 (192.168.42.51) is running and apid is responding
```

**If a node times out:**
- The recipe automatically collects `talosctl logs machined` and stops
- Common causes: wrong disk selector (no matching disk), broken bond (LACP not negotiated), bad secrets

---

### Step 4: Bootstrap

```bash
just talos bootstrap
```

This runs `talosctl bootstrap` on k8s01 (192.168.42.51) — the first CP node.

**Bootstrap must run exactly once.** The recipe:
- Checks for `.private/bootstrap.done` marker — warns if bootstrap already ran
- Handles "AlreadyExists" safely (idempotent)
- Uses `--insecure` (no dependency on stale talosconfig)
- Writes `.private/bootstrap.done` on success

After bootstrap succeeds, it fetches kubeconfig and sets the server to the bootstrap IP.

**Expected output:**
```
Bootstrapping Kubernetes on 192.168.42.51...
  Bootstrap command accepted
Bootstrap initiated. Waiting for Kubernetes API...
  kubeconfig written to .../kubeconfig
  kubeconfig cluster server set to https://192.168.42.51:6443
```

---

### Step 5: Verify

```bash
just talos verify
```

**Expected output:**
```
── Cluster health checks ──

Nodes:
NAME    STATUS   ROLES           AGE   VERSION   INTERNAL-IP      ...
k8s01   Ready    control-plane   ...   v1.36.0   192.168.42.51    ...
k8s02   Ready    control-plane   ...   v1.36.0   192.168.42.52    ...
k8s03   Ready    control-plane   ...   v1.36.0   192.168.42.53    ...

Etcd members:
(3 members listed)

Talos services:
(all services Running or Finished on all nodes)
```

**If nodes are NotReady:** This is expected initially — they need a CNI (Cilium). The Flux bootstrap will handle that.

---

### Step 6: (Post-bootstrap) Add workers

Workers can only join after the control plane is healthy.

```bash
# Render and apply worker configs individually:
just talos render-config k8s04 > talos/rendered/k8s04.yaml
talosctl apply-config --nodes 192.168.42.54 --endpoints 192.168.42.54 --insecure --file talos/rendered/k8s04.yaml
# Repeat for k8s05, k8s06
```

Workers do NOT need `talosctl bootstrap` — they join automatically via the cluster discovery service.

---

### Step 7: (Post-bootstrap) Switch to DNS endpoint

After the control plane is stable and Cilium/DNS is running:

1. Ensure `k8s.in.homeops.ca` resolves to a VIP or load-balancer IP
2. Re-render configs without the bootstrap endpoint patch
3. Apply updated configs: `just talos apply-node k8s01` (repeat for each node)

---

## Secrets management

### Architecture

```
machineconfig.yaml.j2
  └─ contains azkv://keyvault-kube/talos#KEY_NAME placeholders
  └─ rendered by minijinja-cli
  └─ piped through scripts/akv-inject.sh
      └─ Mode A (AKV, default): az keyvault secret show
      └─ Mode B (Local): reads from $AKV_LOCAL_DIR/<vault>/<name>.json
      └─ the "talos" secret is a single JSON blob with 14 keys
      └─ each azkv://keyvault-kube/talos#KEY_NAME is replaced with the value of that JSON key
      └─ Uses bash ${//} literal replacement (safe with newlines, /, &, $, etc.)
```

### Two supported modes

#### Mode A: AKV (default)

Normal operations — secrets fetched live from Azure Key Vault.

```bash
# Prerequisites: az login
just talos preflight
just talos render
```

#### Mode B: Local bootstrap

For when AKV is unreachable, air-gapped recovery, or 3am emergencies.

```bash
# Step 1: Export secrets (when AKV IS accessible — do this in advance)
just talos export-secrets
# Creates .private/secrets/keyvault-kube/{talos,azurekv,cloudflare}.json

# Step 2: Use local mode (no 'az' calls at all)
export AKV_LOCAL_DIR=.private/secrets
just talos render
# All azkv:// placeholders resolved from local files
```

**When to use which mode:**
| Scenario | Mode |
|----------|------|
| Normal rebuild | AKV (default) |
| AKV outage / no internet | Local (`export AKV_LOCAL_DIR=.private/secrets`) |
| CI/CD pipeline | AKV (service principal) |
| 3am panic rebuild | Local (if pre-exported) |

**Important:** Local secret files are in `.private/` which is gitignored. They must be pre-populated with `just talos export-secrets` while AKV is accessible.

### Required AKV keys (14 total)

| Key | Description |
|-----|-------------|
| `MACHINE_CA_CRT` | Machine CA certificate |
| `MACHINE_CA_KEY` | Machine CA private key |
| `MACHINE_TOKEN` | Machine authentication token |
| `CLUSTER_CA_CRT` | Cluster CA certificate |
| `CLUSTER_CA_KEY` | Cluster CA private key |
| `CLUSTER_ID` | Cluster ID |
| `CLUSTER_SECRET` | Cluster secret |
| `CLUSTER_TOKEN` | Cluster bootstrap token |
| `CLUSTER_AGGREGATORCA_CRT` | Aggregator CA certificate |
| `CLUSTER_AGGREGATORCA_KEY` | Aggregator CA private key |
| `CLUSTER_ETCD_CA_CRT` | etcd CA certificate |
| `CLUSTER_ETCD_CA_KEY` | etcd CA private key |
| `CLUSTER_SECRETBOXENCRYPTIONSECRET` | Secretbox encryption secret |
| `CLUSTER_SERVICEACCOUNT_KEY` | Service account key |

### Rotating secrets

```bash
just talos rotate-secrets
```

This generates a new secrets bundle with `talosctl gen secrets`, converts it to the AKV JSON format, and uploads it. After rotation, re-render and re-apply configs.

---

## Troubleshooting

### Node stuck in maintenance after apply
```bash
# Check if config was received (--insecure works pre- and post-bootstrap)
talosctl dmesg --nodes <ip> --endpoints <ip> --insecure 2>&1 | tail -30
talosctl logs machined --nodes <ip> --endpoints <ip> --insecure 2>&1 | tail -50
talosctl logs installer --nodes <ip> --endpoints <ip> --insecure 2>&1 | tail -30
talosctl get addresses --nodes <ip> --endpoints <ip> --insecure 2>&1
```

The `just talos apply` recipe automatically collects these logs on timeout.

### etcd won't form
```bash
talosctl etcd members --nodes 192.168.42.51 --endpoints 192.168.42.51 --insecure
talosctl logs etcd --nodes 192.168.42.51 --endpoints 192.168.42.51 --insecure 2>&1 | tail -30
```

### apiserver auth loops
Past symptom: `Authorization error user=apiserver-kubelet-client ... resource=nodes subresource=pods`
Root cause: stale/mismatched secrets. Fix: `just talos rotate-secrets && just talos render && just talos apply`

### kubeprism unhealthy / kubelet EOF to 127.0.0.1:7445
Usually resolves once all etcd members are healthy and apiserver is fully started. Wait 2-3 minutes.

### "wrong" NIC in bond
Cross-check MACs against `talos/nodes/<node>.yaml.j2`:
```bash
yq '.machine.network.interfaces[0].bond.deviceSelectors[].hardwareAddr' talos/nodes/k8s01.yaml.j2
```
Compare with physical NIC labels or NetBox inventory.

### Bootstrap marker prevents re-bootstrap
If `just talos bootstrap` shows the marker warning and you're sure you want to re-bootstrap:
```bash
rm .private/bootstrap.done
just talos bootstrap
```
The `just talos wipe-cp` recipe automatically removes the marker.

### Zigbee / Multus IoT network attached but unreachable
Symptom pattern:
- Zigbee pod has `kube-system/iot` on `net1` with expected static IP/MAC
- Zigbee logs show `connect ETIMEDOUT 192.168.70.37:6638`
- `ip addr show net1` in test pod shows `NO-CARRIER`

Quick checks:
```bash
# 1) Confirm multus attachment + MAC pinning
kubectl describe pod -n default -l app.kubernetes.io/name=zigbee | grep -A 35 "k8s.v1.cni.cncf.io/network-status"

# 2) Confirm host VLAN link exists on each CP node
talosctl --nodes 192.168.42.51 --endpoints 192.168.42.51 get links | grep -E 'bond0(\\.70)?'
talosctl --nodes 192.168.42.52 --endpoints 192.168.42.52 get links | grep -E 'bond0(\\.70)?'
talosctl --nodes 192.168.42.53 --endpoints 192.168.42.53 get links | grep -E 'bond0(\\.70)?'

# 3) Confirm VLAN addresses are present
talosctl --nodes 192.168.42.51 --endpoints 192.168.42.51 get addresses | grep -E 'bond0\\.70|192\\.168\\.70\\.'

# 4) Check Talos network-controller errors
talosctl --nodes 192.168.42.51 --endpoints 192.168.42.51 logs controller-runtime --tail 200 | grep -iE 'bond0\\.70|device or resource busy|network is unreachable'
```

Interpretation:
- If `bond0.70` exists but stays `down` and pods on `net1` show `NO-CARRIER`, this is usually an upstream L2/VLAN path issue (switch trunk / VLAN allow-list / native-tag mismatch) rather than multus annotation syntax.
- If `bond0.70` does not exist on some nodes, re-render and re-apply Talos configs for all CP nodes.

### Multus macvlan NAD VLAN sub-interfaces missing (VLANs 1, 50, 90)

Nodes k8s01–k8s06 should have `bond0.1`, `bond0.50`, and `bond0.90` sub-interfaces for macvlan NADs (blackbox-exporter-vpn, Omada Controller, etc.). CP nodes also have `bond0.70` (IoT). Workers only have 1, 50, 90.

Expected static IP assignments per node:
| Node | VLAN 1 (bond0.1) | VLAN 50 (bond0.50) | VLAN 70 (bond0.70, CP only) | VLAN 90 (bond0.90) |
|------|------------------|--------------------|-----------------------------|---------------------|
| k8s01 | 192.168.0.11/24 | 192.168.50.11/24 | 192.168.70.11/24 | 192.168.90.11/24 |
| k8s02 | 192.168.0.12/24 | 192.168.50.12/24 | 192.168.70.12/24 | 192.168.90.12/24 |
| k8s03 | 192.168.0.13/24 | 192.168.50.13/24 | 192.168.70.13/24 | 192.168.90.13/24 |
| k8s04 | 192.168.0.14/24 | 192.168.50.14/24 | — | 192.168.90.14/24 |
| k8s05 | 192.168.0.15/24 | 192.168.50.15/24 | — | 192.168.90.15/24 |
| k8s06 | 192.168.0.16/24 | 192.168.50.16/24 | — | 192.168.90.16/24 |

```bash
# Verify all VLAN links on all nodes
for node in 192.168.42.51 192.168.42.52 192.168.42.53 192.168.42.54 192.168.42.55 192.168.42.56; do
  echo "=== $node ==="
  talosctl --nodes $node --endpoints $node get links | grep -E 'bond0\.(1|50|70|90)'
done

# Verify addresses on a specific node
talosctl --nodes 192.168.42.51 --endpoints 192.168.42.51 get addresses | grep -E '192\.168\.(0|50|70|90)\.'
```

If sub-interfaces are missing after applying config, re-render and re-apply:
```bash
just talos render-config k8s01 | talosctl apply-config --nodes 192.168.42.51 --file /dev/stdin
```

### Cluster resource policy audit
Use this to find containers missing CPU/memory requests/limits:
```bash
# Count missing by namespace
kubectl get pods -A -o json \
  | jq -r '.items[] as $p | ($p.spec.containers // [])[] as $c |
      select(($c.resources.requests.cpu // "")=="" or ($c.resources.requests.memory // "")=="" or ($c.resources.limits.cpu // "")=="" or ($c.resources.limits.memory // "")=="") |
      $p.metadata.namespace' \
  | sort | uniq -c | sort -nr

# Sample offenders
kubectl get pods -A -o json \
  | jq -r '.items[] as $p | ($p.spec.containers // [])[] as $c |
      select(($c.resources.requests.cpu // "")=="" or ($c.resources.requests.memory // "")=="" or ($c.resources.limits.cpu // "")=="" or ($c.resources.limits.memory // "")=="") |
      [$p.metadata.namespace, $p.metadata.name, $c.name] | @tsv' | head -80
```

---

## Post-bootstrap: GitOps restoration

After `just talos rebuild` succeeds, the cluster has K8s running but no CNI, storage, or apps.
The bootstrap helmfile handles the critical-path installation automatically.

### Phase 1: Platform foundation (automatic via bootstrap helmfile)

Run the full bootstrap orchestration:
```bash
just bootstrap
```

This executes in order:
1. **Cilium** (CNI + BGP + LoadBalancer) — nodes become Ready
2. **CoreDNS** — cluster DNS
3. **Spegel** — registry mirror
4. **Cert-Manager** — TLS certificate issuance
5. **External-Secrets + AzureKV** — ClusterSecretStore for all app secrets
6. **Flux Operator + Flux Instance** — GitOps controller watching this repo

**Checkpoint:** After this completes, Flux begins reconciling `kubernetes/apps/` automatically.

### Phase 2: Platform services (Flux-managed, auto-reconcile)

These will reconcile within ~10-20 minutes after Flux starts:
- **Rook-Ceph** — Distributed storage (OSD formation takes ~5-10 min)
- **OpenEBS LocalPV** — Local hostpath storage
- **Envoy Gateway** — Ingress (internal + external gateways)
- **Cloudflare Tunnel** — External access via `*.homeops.ca`
- **Metrics Server, Snapshot Controller** — Cluster services
- **Kube-Prometheus-Stack** — Monitoring

**Checkpoint:** `kubectl get cephcluster -n rook-ceph` → HEALTH_OK (takes time)

### Phase 3: Applications (Flux-managed, auto-reconcile)

Once storage + secrets are healthy, all apps in `kubernetes/apps/default/` reconcile:
- PVC data may need VolSync restore for persistent apps
- Apps will start in degraded state until PVCs are restored

**VolSync restore:** For each app with prior backup data:
```bash
just kube snapshot <app>  # Trigger restore from Kopia
```

### Known blockers to verify before bootstrap

1. **OPNSense BGP:** Cilium peers with `192.168.0.1` (ASN 64513). Verify BGP daemon is running with neighbors for `.42.51-.56`. Without this, LoadBalancer IPs (192.168.69.0/24) won't be reachable.
2. **NAS availability:** `nas02.in.homeops.ca` must be online with NFS exports for Kopia backups and NFS mounts.
3. **AKV secrets:** All ExternalSecrets depend on the `azurekv` ClusterSecretStore. Verify AKV credentials haven't expired.
4. **Cloudflare Tunnel:** Check tunnel status in Cloudflare dashboard — auth tokens in AKV may need refresh.
