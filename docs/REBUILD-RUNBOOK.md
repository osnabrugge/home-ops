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

| Tool            | Required version |
| --------------- | ---------------- |
| `talosctl`      | v1.13.x          |
| `minijinja-cli` | any              |
| `yq`            | v4.x (mikefarah) |
| `jq`            | 1.6+             |
| `az`            | 2.x (logged in)  |
| `gum`           | any              |
| `kubectl`       | v1.36.x          |

### Node inventory

| Node  | IP            | MAC (bond member 1) | MAC (bond member 2) | Role         |
| ----- | ------------- | ------------------- | ------------------- | ------------ |
| k8s01 | 192.168.42.51 | 38:ea:a7:91:e3:9c   | 38:ea:a7:91:e3:9d   | controlplane |
| k8s02 | 192.168.42.52 | 8c:dc:d4:ac:7a:e8   | 8c:dc:d4:ac:7a:e9   | controlplane |
| k8s03 | 192.168.42.53 | 00:11:0a:68:bd:70   | 00:11:0a:68:bd:71   | controlplane |
| k8s04 | 192.168.42.54 | 38:ea:a7:90:4b:0c   | 38:ea:a7:90:4b:0d   | worker       |
| k8s05 | 192.168.42.55 | (see template)      | (see template)      | worker       |
| k8s06 | 192.168.42.56 | (see template)      | (see template)      | worker       |

---

### Step 0: Wipe CP nodes (DESTRUCTIVE)

> **Only needed if nodes are running a previous Talos install. Skip if nodes are already in maintenance from ISO boot.**

```bash
just talos wipe-cp
```

This runs `talosctl reset --graceful=false --wipe-mode=all --reboot` on all 3 CP nodes.

After wipe, nodes **must** be booted from Talos ISO (USB or PXE). They will enter maintenance mode on port 50000.

#### PXE boot (recommended)

If **netboot.xyz** is deployed (see `kubernetes/apps/network/netboot-xyz/` and [docs/NETBOOT-PXE.md](NETBOOT-PXE.md)),
nodes will network-boot automatically after the wipe reboot, as long as:

1. The node's UEFI/firmware is set to PXE boot on the first boot attempt
2. dnsmasq on fw01 is configured with the boot options (see [docs/NETBOOT-PXE.md](NETBOOT-PXE.md))
3. The netboot.xyz LoadBalancer service is reachable at `192.168.69.131`

Select **Talos Linux** from the netboot.xyz menu, then wait for maintenance mode.
For SecureBoot-enabled nodes, use the Talos Image Factory URL for a signed image.

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

| Scenario                 | Mode                                            |
| ------------------------ | ----------------------------------------------- |
| Normal rebuild           | AKV (default)                                   |
| AKV outage / no internet | Local (`export AKV_LOCAL_DIR=.private/secrets`) |
| CI/CD pipeline           | AKV (service principal)                         |
| 3am panic rebuild        | Local (if pre-exported)                         |

**Important:** Local secret files are in `.private/` which is gitignored. They must be pre-populated with `just talos export-secrets` while AKV is accessible.

### Required AKV keys (14 total)

| Key                                 | Description                  |
| ----------------------------------- | ---------------------------- |
| `MACHINE_CA_CRT`                    | Machine CA certificate       |
| `MACHINE_CA_KEY`                    | Machine CA private key       |
| `MACHINE_TOKEN`                     | Machine authentication token |
| `CLUSTER_CA_CRT`                    | Cluster CA certificate       |
| `CLUSTER_CA_KEY`                    | Cluster CA private key       |
| `CLUSTER_ID`                        | Cluster ID                   |
| `CLUSTER_SECRET`                    | Cluster secret               |
| `CLUSTER_TOKEN`                     | Cluster bootstrap token      |
| `CLUSTER_AGGREGATORCA_CRT`          | Aggregator CA certificate    |
| `CLUSTER_AGGREGATORCA_KEY`          | Aggregator CA private key    |
| `CLUSTER_ETCD_CA_CRT`               | etcd CA certificate          |
| `CLUSTER_ETCD_CA_KEY`               | etcd CA private key          |
| `CLUSTER_SECRETBOXENCRYPTIONSECRET` | Secretbox encryption secret  |
| `CLUSTER_SERVICEACCOUNT_KEY`        | Service account key          |

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
- If `bond0.70` does not exist on some nodes, re-render and re-apply Talos configs for all nodes (CP and worker).

### Omada switch commissioning: VLAN 1 bootstrap, VLAN 99 management

Scope one identified switch and back up its configuration before an approved
reset. Do not reset working devices, change core routing/LAGs, or Forget an
existing controller record merely to clear its displayed status.

1. Make DHCP available on the selected VLAN 1 bootstrap path before adoption.
   The cluster controller has direct attachments at `192.168.0.30` on VLAN 1 and
   `192.168.99.30` on VLAN 99. Verify the actual interfaces and on-link routes,
   rather than assuming discovery crosses the firewall.
2. Stage the site with LAN/default VLAN 1 and the intended management VLAN 99.
   Keep core01's separate default/parking VLAN 4040 and all-tagged PVE links
   unchanged; the core's default VLAN need not match the Omada site's default.
3. Match the switch-facing uplink to the existing core port's wire contract:

    | End                             | Native/PVID | Untagged | Tagged                                 |
    | ------------------------------- | ----------- | -------- | -------------------------------------- |
    | Core uplink using `dual-mode 1` | 1           | 1        | 99 and other required trunk VLANs      |
    | Omada uplink profile            | LAN 1       | LAN 1    | Management 99 and matching trunk VLANs |

    VLAN 99 untagged on the Omada end but tagged on the core end can send the
    management DHCP request into VLAN 1 and retain a bootstrap-subnet address.
    Resolve profile network IDs against current VLAN definitions after renaming
    networks; profile names alone are not proof of membership.

4. Configure the switch's management interface for VLAN 99 and its intended DHCP
   reservation. A VLAN-only site network definition is not proof the management
   handoff occurred. Do not force a VLAN 99 address onto traffic still using VLAN 1.
5. Observe the adoption/configuration timeline in VictoriaLogs. Verify the exact
   device MAC has a VLAN 99 DHCP lease, a fresh management connection to the
   controller's VLAN 99 address, and stable online/consistent configuration across
   repeated checks. A stale IP, a green health score, or an initial adoption-success
   event is not sufficient. Also verify its MAC is learned on the production uplink
   in VLAN 99 and the intended LAG member is forwarding.

Once the saved profile is correct, use reprovisioning if the management connection
is still available rather than repeatedly wiping the device. Any reboot or further
network change needs its own checked scope and rollback. This recipe does not prove
all firmware supports configuration retention during adoption, nor does the newer
tagged-native UI option eliminate the factory bootstrap requirement.

### Frigate camera stream failures

Check `/api/stats` and go2rtc's `/api/streams` from inside the Frigate container.
A healthy main-stream producer does not prove that the separate detection
substream works. A `404` on RTSP `DESCRIBE` can mean that the selected camera
substream is disabled; it is not proof of a VLAN fault or bad credentials.

Use the bundled `ffprobe` under `/usr/lib/ffmpeg/` to verify the exact subtype,
codec and dimensions without printing password-bearing URLs. Cam01 and cam02
currently provide their 1280x720 detection feeds on subtype 2, including cam03.
Keep the go2rtc URL and Frigate's declared detection dimensions consistent.

For USB Coral troubleshooting, check the loaded `/api/config` detector type,
`/api/stats` inference time and the detector process's open `/dev/bus/usb` file
descriptors. CPU utilization reported for that process does not mean inference
uses the CPU. NFD labels identify USB devices but do not allocate them; this
workload uses the mounted USB bus. USB Corals do not require the PCIe
`gasket-driver` extension or `/dev/apex_*`.

Frigate+ model selection is separate from accelerator discovery. An empty
`/api/plus/models` catalogue does not mean a Coral is unsupported. Select a
Frigate+ YOLOv9 `edgetpu` variant for Coral, and verify that the account's
catalogue supplies a compatible model before changing the deployed model.
After a configuration rollout, require advancing frame counts and approximately
5 camera/process FPS on every enabled camera, not only a Ready pod.

Camera web access is separate from RTSP. Test explicit HTTP and HTTPS before
changing browser security or network configuration. An HTTP-only camera and a
browser's cached HTTPS upgrade can produce different results across browser
profiles; do not clear parent-domain HSTS or disable IPv6 as a generic repair.

Frigate's existing `init-config` step preserves `/config/.jwt_secret` with
UID/GID 1000 and mode 0600 so the ordinary non-root mover can read it. An
existing value is never replaced; a missing file is initialized using Frigate's
own `secrets.token_hex(64)` scheme. Empty files and symlinks fail explicitly.
This avoids enabling privileged movers for the entire `default` namespace or
making the secret group/world-readable. File errors must fail the backup, not
silently produce a supposedly complete snapshot.
Verify `filesFailed: 0` and the protected file's presence after an isolated
restore before declaring the backup repaired.

### Shared RBD client read-only recovery

`emergency_ro` is ext4's protective response to an I/O failure. Healthy Ceph
servers do not reset a failed node client or make an aborted journal writable.
Inspect native mount options and actual application writes; Ready pods and
HTTP 200 responses are insufficient.

1. Verify Ceph quorum/OSDs/PGs and current network stability. Map affected RBD
   devices to PVCs and compare `/sys/block/rbdN/device/client_id`. Include
   apparently writable mappings sharing the failed client.
2. Record replica counts, PVC UIDs/PV bindings and every reconciliation pause.
   Hold the affected Flux Kustomizations/HelmReleases, operator owners,
   autoscalers and backup scheduling. Take CSI checkpoints of the original
   claims; check StatefulSet claim retention before scaling down.
3. Stop all consumers of that client normally, including shared-PVC workers.
   Wait for pods to exit and for its kernel RBD devices/mounts to disappear.
   Do not force-unmap, delete PVCs, change Ceph keys or reboot healthy nodes.
4. Restore the original replica counts. Verify live watchers, absence of
   `emergency_ro`, database integrity and committed application writes. Exercise
   a fresh mapping on the original node with an isolated synthetic write test.
5. Restore every held reconciler, autoscaler and schedule, preserving prior
   values rather than blindly enabling everything. Keep rollback checkpoints
   until data verification is complete, and check alerts and backups again.

If normal unmount or CSI filesystem checks fail, preserve the checkpoints and
collect the exact error before escalating. Filesystem repair or a forced reset
is a separate approval boundary. Do not mount an unhealthy filesystem writable
or disable ext4's protection to hide the failure. The original trigger must be
established from retained kernel, Ceph and network evidence; a successful
remount alone does not prove which network/authentication event caused it.

Home Assistant and both memory backends use write-aware readiness checks.
Grafana keeps its native HTTP check and adds a small storage-readiness
container. They create, flush and remove only temporary files on their own
data volumes, without modifying application records. Nonblocking locks prevent
overlapping probes from launching more writes while an earlier probe is stuck
in kernel I/O. Failed readiness exposes the fault; it does not pretend that a
container restart can repair a shared node client.

### Grafana operator dashboards

`Login failed / User sync failed` together with `attempt to write a readonly
database` is an application-storage failure, not proof of an IdP/password error.
Check the actual data mount for `emergency_ro`, RBD watcher/client health and
native database writes. Do not switch issuers, reset users or replace a PVC as
login recovery. A watchless shared node client needs the approved coordinated
remount procedure; restarting one container or clearing a blocklist alone can
leave the poisoned client in place.

Dashboard datasource names and generated UIDs are different. Keep datasource
variables/runtime substitutions wired through Grafana Operator instead of
hardcoding a generated UID into imported JSON. Preserve pinned dashboard
provenance and validate the variables and actual panel queries after import.

The CloudNativePG dashboard selects `cnpg_cluster`, not Prometheus's estate-wide
`cluster` label. All three database clusters need their own healthy PodMonitor;
Kritika's database permits only Prometheus on TCP 9187. A single-instance cluster
has primary metrics but legitimately no replica series. External Secrets'
error-only panels can be empty when there are no errors; that alone is not
broken collection. Check real metrics before adding success-shaped zeros.

For Omada, verify the exporter can authenticate to the current controller and
its selected site before changing dashboard filters. A healthy `/metrics`
endpoint alone does not prove that device/client series are fresh.

### SMTP and model-key policy recovery

Maddy's public image needs no registry pull credentials. Inspect the failed
pull, Pod and ServiceAccount references before changing mail configuration;
retired registry credentials can produce a 403 even for a public image.
An EHLO/NOOP check must not send real mail or weaken SMTP authentication.

LiteLLM's key-policy controller retries bounded read-only lookups for transient
HTTP/transport failures. Exhausted retries remain failures; writes and key
creation are not retried blindly. Require a new native CronJob success and
preserved policy before treating an older failed Job as obsolete history.

### Kritika pilot recovery

Keep the application/tools image digests paired through the pinned chart.
For the 0.0.118 upgrade, remove retired `review.replies` and validate the actual
application configuration. Confirm native UI assets, login/logout/session
revocation, indexed generation and isolated runner behavior; a proxy's HTTP
response is not a human-login or review-publication test.

The running pilot uses a separate `kritika-db` PostgreSQL/VectorChord cluster.
Do not attach, reinitialize or delete the original held `kritika-postgres-1`
volume as startup recovery. Verify all eight Kritika Kustomizations, its
HelmRelease and the database are Ready before investigating the application.
The namespace allows five PVCs within the unchanged 20Gi aggregate storage
ceiling. The held database, running database, embedding cache and 2Gi backup
cache use four claims and 19Gi, leaving one transient restore-cache claim slot.
This does not authorize creating or replacing a production volume.
The owner permits maintenance downtime for the singleton `kritika-db` and
`litellm-db` pilots: both declare `enablePDB: false` through CNPG rather than
patching operator-owned budgets. Eviction can take their applications offline
until the database returns; LiteLLM's node pinning also keeps it pending while
its selected node is cordoned. Reassess protection before adding replicas.

The repository-policy Job reruns its transactional, idempotent SQL when its
image or template changes. Its resource-scoped Flux `force: enabled` annotation
allows replacement of that stateless Job; do not extend forced replacement to
database resources or PVCs.

An index job cancelled with `no embedder is configured` is a real configuration
gap, not a GitHub App permission failure. Check `kritika-embeddings`, its
`granite-embedding:30m` model-bootstrap Job and the configured local 384-dimension
embedder. Require a completed native `index_runs` generation with nonzero chunks,
not merely a Ready server or a discovered repository. The monthly token ceiling
includes local indexing; the per-review bound is separate. Automatic PRs skipped
with reason `filter` are deliberately held until an approved manual test.

Bootstrap is ordered: `kritika-embeddings` waits for the server API, then
`kritika-embedding-model` pulls the model, and only then can Kritika start using
it. Do not combine server startup and its first client Job into a race or make
the server wait for a model whose bootstrap is waiting for that server.

The isolation-check-only Kustomization recreates its stateless Job when an image
update changes the immutable pod template. Do not copy its `force: true` setting
onto database, volume or application Kustomizations.

The private dashboard has both Authentik and native application login.
Only signed `POST /hooks/github` callbacks are publicly routed; unsigned requests
return 401 and public dashboard/API requests return 404. Endpoint readiness does
not mean GitHub delivery or real reviews have been enabled. Do not recover model
quota/capacity errors by enabling paid fallbacks, or silently enable repositories,
automatic reviews or the owner's webhook. See
[the verified pilot and first-review gate](AI-WORKFLOW.md#kritika-bounded-free-only-pilot)
for credentials, local network-path constraints and owner-authorized testing.

### Container OOM notifications

Correlate the terminated container, node kernel cgroup and Prometheus restart
history before increasing resources. `CONSTRAINT_MEMCG` identifies a container
budget failure; available node RAM can remain plentiful. A deleted old pod's
missing status does not erase its historical OOMs.

Autobrr has a 1536Mi container limit, a 768MiB Go soft memory limit and a 256Mi
request, leaving headroom outside the managed heap. Verify the runtime's reported
memory limit, RSS and restart count after rollout. This is mitigation for measured
cgroup OOMs, not proof that an upstream leak is fixed; verify across the natural
six-hour refresh (including 06:00 UTC), not only an idle interval. Do not trigger
release cleanup, downloads or tracker operations just to generate load.

### Multus macvlan NAD VLAN sub-interfaces missing (VLANs 1, 50, 70, 90)

All nodes k8s01–k8s06 should have `bond0.1`, `bond0.50`, `bond0.70`, and `bond0.90` sub-interfaces for macvlan NADs (IoT/Zigbee, blackbox-exporter-vpn, Omada Controller, etc.).

Expected static IP assignments per node:

| Node  | VLAN 1 (bond0.1) | VLAN 50 (bond0.50) | VLAN 70 (bond0.70) | VLAN 90 (bond0.90) |
| ----- | ---------------- | ------------------ | ------------------ | ------------------ |
| k8s01 | 192.168.0.11/24  | 192.168.50.11/24   | 192.168.70.11/24   | 192.168.90.11/24   |
| k8s02 | 192.168.0.12/24  | 192.168.50.12/24   | 192.168.70.12/24   | 192.168.90.12/24   |
| k8s03 | 192.168.0.13/24  | 192.168.50.13/24   | 192.168.70.13/24   | 192.168.90.13/24   |
| k8s04 | 192.168.0.14/24  | 192.168.50.14/24   | 192.168.70.14/24   | 192.168.90.14/24   |
| k8s05 | 192.168.0.15/24  | 192.168.50.15/24   | 192.168.70.15/24   | 192.168.90.15/24   |
| k8s06 | 192.168.0.16/24  | 192.168.50.16/24   | 192.168.70.16/24   | 192.168.90.16/24   |

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

### NVMe-backed OSD reports zero capacity or no BlueStore label

A namespace reporting zero bytes, a dead NVMe controller, or a controller absent
from PCI enumeration is a hardware-access problem first. `No valid bdev label`
against a zero-size device does not prove that the original BlueStore metadata
was erased. Do not purge/recreate the OSD, rewrite labels, or delete PVCs/PVs as
a shortcut.

1. Verify the remaining Ceph placement groups are active and clean and monitor
   quorum is healthy. Record the original OSD UUID, cluster FSID, replica count,
   and persistent PVC identities; identify the boot disk separately.
2. Wait for in-flight Kopiur backups to reach **Succeeded**, not merely
   **SourceStaged**. A staging clone can have node affinity, so cordoning its
   node while its mover is pending can fail the backup without losing the
   original data PVC.
3. Keep controller-reset attempts bounded. If supported resets cannot recover
   the device, plan a genuine AC removal using the verified, dedicated outlet.
   `talosctl reboot --mode=powercycle` bypasses kexec but is still a firmware
   reboot, not proof that the NVMe power rails lost power.
4. Hold only the failed OSD, drain its node through normal evictions/PDBs, and
   verify application volumes are unmounted. Follow the
   [PDU safety checks](./OOB-MANAGEMENT.md#safety-features): BIOS Last State and an
   unavailable WoL link require quiescent, powered-on firmware staging rather
   than assuming a powered-off node will boot when its outlet turns on. Record
   the single power request before sending it; never blindly repeat a timeout.
5. After power returns, discover the actual device again. Require full capacity,
   native SMART health, and read-only verification of the **original** BlueStore
   OSD UUID and cluster FSID before restoring its replicas and uncordoning.
6. Require all configured OSDs up/in, all placement groups active+clean, sustained
   pod readiness, and no new controller timeout/reset errors. Re-run any
   maintenance-interrupted backups and verify their successful snapshot IDs.
   Preserve crash evidence; acknowledge only the exact resolved crash after
   recovery is stable, not all crashes to make health appear green.

### CephNodeNetworkBondDegraded on k8s06 / `enp1s0f1`

Known-good desired state in Git:

- `talos/nodes/k8s06.yaml.j2` defines `bond0` as 802.3ad/LACP over `enp1s0f0`
  and `enp1s0f1`.
- The saved core01 config maps `k8s06-enp1s0f0` to `ethernet 1/2/8` and
  `k8s06-enp1s0f1` to `ethernet 2/2/8` in dynamic LAG `k8s06`.

If `CephNodeNetworkBondDegraded` fires for `192.168.42.56:9100` and
`enp1s0f1` is still down after `no deploy` / `deploy` on the core01 LAG, treat
it as a secondary-path physical/link fault rather than a GitOps drift issue.
The LACP and VLAN intent in Git is already correct; repeatedly redeploying the
LAG will not restore carrier if the NIC, cable, transceiver, or `2/2/8` switch
path is down.

Read-only checks:

```bash
# Talos side: confirm bond membership and which slave lacks carrier.
talosctl --nodes 192.168.42.56 --endpoints 192.168.42.56 read /proc/net/bonding/bond0
talosctl --nodes 192.168.42.56 --endpoints 192.168.42.56 get links | grep -E 'bond0|enp1s0f[01]'
talosctl --nodes 192.168.42.56 --endpoints 192.168.42.56 dmesg | grep -iE 'enp1s0f1|igb|ixgbe|i40e|link'

# Switch side: inspect the secondary k8s06 member, not only the LAG summary.
show lag k8s06
show interfaces brief ethernet 2/2/8
show interfaces ethernet 2/2/8
show logging | include 2/2/8
```

Approval-gated diagnostics workflow (for this issue and future recurrences):

1. Capture evidence first from Talos + Kubernetes + Ceph (commands above), then paste
   the outputs into the incident issue before taking manual action.
2. If the issue still has no clear root cause, request authorized operator approval to
   run switch-side deep diagnostics for **only** `k8s06` LAG and member port `2/2/8`.
3. Use time-bounded diagnostics (for example 10-15 minutes), then revert to baseline
   logging levels and keep all captured output in the issue for future comparison.

Temporary elevated diagnostics (requires explicit approval on core01):

- Increase logging only for the affected LAG/member path (`k8s06`, `2/2/8`) so we can
  capture LACP/member flaps, physical layer errors, and state transitions during the
  incident window.
- Collect at least three snapshots (`t0`, `t+5m`, `t+15m`) of:
    - `show lag k8s06`
    - `show interfaces brief ethernet 2/2/8`
    - `show interfaces ethernet 2/2/8`
    - `show logging | include 2/2/8`
- If no events appear even with temporary increased logging, treat that as evidence
  and prioritize host-side causes (NIC, PCIe seating/riser, firmware/driver, thermal).

Manual remediation path:

1. Verify Ceph is healthy before touching the host network path.
2. Reseat or replace the cable/transceiver between k8s06 `enp1s0f1` and core01
   `ethernet 2/2/8`.
3. If the link still has no carrier, move only that secondary leg to a
   known-good spare switch port and update the core01 LAG member mapping to the
   new port.
4. If the switch port comes up on another device but k8s06 still shows
   `enp1s0f1` down, schedule k8s06 maintenance for NIC/PCIe inspection or NIC
   replacement.
5. Confirm recovery with `/proc/net/bonding/bond0`: both slaves should report
   `MII Status: up`, and the Prometheus alert should clear after the rule's
   `for` interval.

### Proxmox Datacenter Manager

PDM runs in its own `proxmox` namespace at `https://pdm.homeops.ca`, through
`envoy-internal` only. It is an optional management plane; neither Proxmox host
nor its guests depends on it to run. Retain direct host and out-of-band access.

The pinned LongQT-sea image contains PDM 1.1.9. Its default systemd entrypoint
is deliberately bypassed: Kubernetes starts the native privileged API as a
restartable init sidecar, configures it, then starts the web API as UID 33.
The Pod uses a native user namespace, no Kubernetes token, no host mounts or
host networking, read-only roots and RuntimeDefault seccomp. Only the mapped
root setup/helper receives CHOWN, DAC_OVERRIDE and FOWNER; neither daemon gets
SYS_ADMIN or NET_ADMIN. SSH/systemd are not started. Do not copy upstream's
unconfined Docker example into this deployment.
The two daemons share the Pod's process namespace, not the host's: their native
control sockets include the PID, so separate container PID namespaces would
make both PID 1 and cause an address collision.

Authentik supplies native OIDC, not an additional proxy login. Its app-owned
provider admits the existing owner and administrator group; PDM's separate ACL
grants only the declared administrator identity. Additional OIDC users do not
automatically receive a PDM role. The default realm is `authentik`.
`recovery@pdm` is an application-only recovery administrator, with its generated
password in Key Vault `proxmox-datacenter-manager` → `RECOVERY_PASSWORD`.
It is not a Linux/SSH or cross-platform automation account. Recovery state is
created only on a fresh volume; startup must not reset existing users, passwords
or MFA. Rotate a recovery password through PDM and the approved secret store
together. OIDC/remote drift fails bootstrap explicitly rather than overwriting
an existing integration.

Initial remote enrollment uses pve02's existing audit-only API token. Adding a
remote is not permission to create remote tokens, change host ACLs or enable
VM/network/storage writes. Validate its TLS certificate and real read-only API
access first; never compensate for a failed credential with root credentials.
The current policy permits only the declared Proxmox API endpoint, the private
OIDC endpoint and cluster DNS. Broaden both the reviewed bootstrap allowlist and
network policy deliberately when enrolling another remote.

One retained Ceph PVC holds configuration, keys, native users, remote credentials,
state, RRD cache and logs. A memory-backed runtime directory is required for
PDM's shared configuration cache. Image upgrades occur through GitOps, not the
container's host-package-management UI. Host hardware/disk statistics and
systemd-dependent administration pages are not representative of the Proxmox
remotes when PDM itself runs in a container.

Hourly Kopiur backups stream `pdm.tar` from the mapped-root helper into the
existing encrypted repository; the mover remains non-root. Namespace-scoped
stream-exec opt-in and repository credentials are required. The tar contains
`config`, `state` and `cache`, not transient sockets or growing request logs.
Test extraction into a separate empty target first; never restore over live
PDM state. Validate native login, remote visibility, OIDC redirect/denial and
state/key identities after a rollout. Anonymous access to the realm list is
expected; protected APIs must reject anonymous requests.

### NetBox Diode integration

Running Diode Pods are not proof that inventory is synchronizing. NetBox must
run an immutable image containing the compatible `netboxlabs-diode-netbox-plugin`
package, enable `netbox_diode_plugin`, and apply its migrations. Preserve the
existing NetBox version, credentials, database and media PVC during that change.
Build reusable images in the `containers` fork, not in this manifests repository.
Do not install a plugin into the live application virtualenv as a substitute for
a reproducible image.
The deployed variant keeps NetBox 4.7.4 and pins plugin 1.19.0. Its reusable
recipe and container tests live in the `containers` fork; the
`container-images` publication workflow builds that exact source revision.
The chart pins the published image digest, and plugin OAuth settings come from
the existing Key Vault data through a separate ExternalSecret.

The Diode Auth initializer creates absent Hydra clients from the existing
ExternalSecret and verifies a real token with the exact role-specific scopes.
It does not overwrite existing client settings or rotate a mismatched secret.
Unexpected scopes, credentials or transport failures keep initialization failed
instead of silently widening access.
Hydra must use `STRATEGIES_JWT_SCOPE_CLAIM=string`: `list` emits an `scp` array,
but the released Diode authorizer requires a `scope` string. Bootstrap checks
that JWT representation as well as the token response. After changing it,
restart the stateless reconciler once to discard a cached incompatible token.
Hydra's administrative port is restricted to Diode Auth's Pod, including its
initializer. The reconciler can use only the public token port; unrelated Pods
must not be able to create or reset OAuth clients through Hydra's admin API.
This cluster requires explicit service-return ingress rules for approved DNS
and PostgreSQL peers in the client port range, as used by LiteLLM. These are
bounded transport exceptions, not an upstream Cilium repair or permission for
those peers to access Hydra's administrative port.

The reconciler uses NetBox's `/api/plugins/diode` endpoint. The NetBox plugin and
discovery agents also need a front door serving both prefixed Diode gRPC methods
and `/diode/auth` HTTP endpoints on the same authority, with authentication on
gRPC requests and no unauthenticated direct-backend bypass. The internal
`netbox-diode:8080` gateway provides this contract; it has no public HTTPRoute.
Backend policy permits raw gRPC only from that gateway. Keep the Diode service
account non-superuser and retain normal NetBox change logging.

The rootless Orb agent currently polls only `pdu01`, `pdu02`, `ups01` and
`ups02` every five minutes using the existing read-only SNMP credential.
Each target declares its existing NetBox primary key; names are not discovered
or renamed. Only device facts are ingested: their platform and SNMP system
description, with the existing site, role and device type explicitly preserved.
Rack placement, addresses, cabling, custom fields and comments are not emitted.
These devices return ambiguous or non-printable interface names, so their
interface proposals are disabled rather than creating duplicate or invalid
interfaces. This is not fleet-wide hardware, port or cable discovery.

The SNMP credential is SOPS-encrypted, not embedded in the agent ConfigMap.
Seed the existing namespace decryption key with
`just kube seed-sops-key observability` when rebuilding. The ConfigMap disables
Flux substitution so Orb resolves credential environment variables at runtime.
The agent has no Kubernetes API token and egress is limited to the four SNMP
endpoints, cluster DNS and the authenticated gateway.

Commission discovery only after a real authenticated ingestion reconciles a
known live fact onto the intended existing NetBox object and a repeat run is
idempotent. Start with explicit targets and matching IDs; preserve manual names,
rack assignments, cabling and fields the collector cannot actually discover.
An OAuth token or Ready HelmRelease alone is not end-to-end verification.
Verify both real scheduled ingestion and its applied NetBox changes, followed
by a repeat cycle without duplicate objects or repeated data changes. Retain
the manual-field baseline during commissioning. Negative controls must reject
bad secrets, forged JWTs, valid tokens lacking ingestion scope and direct
connections to the raw ingester or Hydra admin API. Redact runtime credentials
when examining agent logs.

#### Discovery operations and enrollment

The four enrolled devices reconcile automatically; there is no manual action
per polling cycle or per observed field change. Diode is ingestion plumbing;
Orb performs discovery. The installed plugin's **Diode** menu contains
**Settings** and **Client Credentials**, not a commissioned discovery dashboard
or an approval queue.

Check scheduled collection with the repository kubeconfig:

```sh
kubectl -n observability logs deployment/netbox-diode-discovery --since=15m
```

Look for `SNMP crawl complete` and `entities ingested successfully` for each
target. Those establish collection/submission, not applied changes by themselves:
check the reconciler for errors and the intended NetBox device's change log
when a discovered fact changes. Repeated identical data is deduplicated and need
not produce a new NetBox change record. Pod readiness alone is not freshness.

To enroll another existing device under the current policy:

1. Confirm its existing NetBox ID, live management endpoint, supported collector
   and approved read-only credentials.
2. Inspect a separate collector's dry-run payload first. Orb supports
   `orb.backends.common.diode.dry_run: true` with
   `dry_run_output_dir: /opt/orb`; use disposable scratch storage, not a change
   that stops the production collector from ingesting.
3. Add the reviewed target/ID and preserved type/role defaults to
   `kubernetes/apps/observability/netbox-diode/app/agent.yaml`. Extend both SNMP
   peer lists in the adjacent `discovery-networkpolicy.yaml`; otherwise the
   collector cannot reach the new device. Keep credentials in approved secret
   storage, not the ConfigMap.
4. Build the `netbox-diode` Flux Kustomization, commit/push and request
   reconciliation. Reloader rolls discovery when its generated ConfigMap changes;
   verify that rollout and two scheduled cycles, correct object matching,
   unchanged manual fields and repeat-run idempotency.

Automatic address discovery is supported by the deployed Orb version:
`scope.targets[].host` accepts a CIDR or IP range. It is not enabled here.
Crucially, `netbox_id` is ignored for range targets, so replacing the explicit
list with a subnet does not preserve this policy's exact-ID matching guarantee.
SNMPv2c range probes also send the community to every scanned address; prefer
SNMPv3 for scanning outside a trusted scope.

For less manual enrollment, an inventory-to-policy generator can select approved,
tagged NetBox devices and emit exact IDs/endpoints. That generator is not deployed.
Orb's supported local/Git config managers do not themselves query NetBox for
targets. Git-managed policies can refresh separately, but initial backend and
config-manager settings still require a restart. Choose an explicit discovery
scope and matching policy before enabling broad automatic ingestion.

### Radar ingress hostname and authentication

Radar now uses the app-owned Authentik proxy application and native proxy-mode
authentication. The internal HTTPRoute sends traffic to Authentik; a NetworkPolicy
allows only the outpost and Prometheus to reach Radar's backend. Only
`/api/health` is anonymous.

Radar's unauthenticated shared listener checks the request hostname. Its
`allowedHosts` Helm value is a list of hostnames, not client IP ranges:

```yaml
allowedHosts:
    - radar.homeops.ca
```

The HTTPRoute is managed separately from Radar's chart, so the chart cannot
automatically add that route's hostname. Keep this route on `envoy-internal`.
Commit and push the HelmRelease before requesting Flux reconciliation; local
commits and working-tree edits are not deployment sources.

After reconciliation, verify both the UI and a fresh MCP initialization. A
client that cached the earlier initialization failure may need reconnecting.
The hostname allow-list is not authentication.

The operator-managed application admits the existing `authentik Admins` group,
explicitly approved application users, and the native `radar-mcp` service principal. Radar reads the username from
`X-Authentik-Username` and the app-scoped role from `X-Authentik-Meta-App`.
Using the app slug avoids treating Authentik's pipe-separated directory groups
as Radar's comma-separated group list. The corresponding Kubernetes group is
`radar`, bound to workload operations and read-only views, not `cluster-admin`.
It can restart/scale workloads and manage Jobs, but cannot delete PVCs or write
RBAC. `trustedOrigins` retains browser-origin validation through the proxy.
The owner-approved `radar-read-secrets` binding also grants the group
`get/list/watch` on Secrets for Helm release history. Kubernetes RBAC cannot
filter Secret lists by Helm's type or labels: this includes other Secrets
cluster-wide, not just release records. Keep application admission restricted;
this grant does not include Secret writes, RBAC changes or PVC deletion.

Grant application access in that application's `AuthentikApplication`
`spec.access.rules`, referencing an existing user or a dedicated non-superuser
group. Commit and reconcile the identity Kustomization, then verify the actual
policy result for the intended user. Do not add a user to `authentik Admins`
merely to expose an application: directory administrator status is a separate
privilege. UI-only bindings on operator-managed applications can be reconciled
away. Each application's admission policy is independent of its backend role
mapping, and successful policy evaluation is not proof of a human browser login.

The machine principal has no Authentik groups, roles or administrative API
credential. Its app password and Radar's persistent cookie-signing secret are
stored in Key Vault `radar-auth`; ESO delivers only the signing key to Radar.
MCP clients use the outpost's supported HTTP Basic app-password authentication,
not an Authentik API token or anonymous alternate route. Keep the header only in
private, ignored client configuration; never commit it. Reconnect the MCP
client after changing its authentication configuration.

For validation, use a disposable Deployment: perform the restart through the
authenticated Radar API/MCP, verify the restart annotation and Ready replica,
then remove only that fixture. Also verify anonymous MCP/API requests redirect
to authentication, invalid credentials fail, and an untrusted pod cannot reach
the backend with forged identity headers.

### Cluster resource policy audit

Scheduling uses resource **requests**, not current usage. Compare the allocated
requests in `kubectl describe node <name>` with `kubectl top node <name>`.
A node can have idle CPU and free memory but insufficient unreserved CPU for
another pod. Check the requested resource and workload placement before
reducing requests or moving stateful Ceph workloads.

CephFS controller placement is configured through the CSI Driver's supported
node-affinity values, not by patching its generated Deployments. Prefer workers
while retaining both replicas, hostname anti-affinity and existing resource
requests. Verify actual placement and scheduling headroom after reconciliation.

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

### Download retention and seeding recovery

Arr import completion and tracker seeding completion are different lifecycles.
Completed torrents can correctly disappear from an Arr queue while still
needing to seed. Cross-seeds can share one physical download path, so deleting
one torrent's files can break another torrent's tracker obligations.

Radarr, Sonarr and Lidarr therefore leave completed torrents in qBittorrent;
`removeCompletedDownloads` is disabled. Cleanrr's `remove_from_client` remains
false. Do not enable file cleanup merely because an Arr queue is empty.
TorrentDay retains its configured seed-time target without a ratio-only early
stop. Agregarr syncs only the owner's configured watchlist, not other users'
watchlists.

The unmanaged legacy Radarr `Any` profile does not automatically upgrade
existing files. Movie monitoring, missing-movie intake and the Recyclarr-managed
quality profiles retain their existing behavior. Recovered torrents are held for
reseeding instead of trusting historical local seed counters while tracker
obligations are being checked.

Recover missing payloads only from recorded import paths with matching file
sizes. Create non-overwriting hardlinks on the existing data filesystem; never
silently fall back to copying, moving, deleting, or redownloading media. Stop
only the already-broken torrent, force a hash check, and resume only after the
entire torrent verifies complete. Incomplete or unavailable data stays stopped
for an explicit recovery decision. qBittorrent 5.3 share-limit API calls require
both `shareLimitAction` and `shareLimitsMode` as well as the numeric limits.

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

1. **Brocade BGP:** Cilium peers with `192.168.42.4` (ASN 64513). Verify BGP daemon is running with neighbors for `.42.51-.56`. Without this, LoadBalancer IPs (192.168.69.0/24) won't be reachable.
2. **NAS availability:** `nas02.in.homeops.ca` must be online with NFS exports for Kopia backups and NFS mounts.
3. **AKV secrets:** All ExternalSecrets depend on the `azurekv` ClusterSecretStore. Verify AKV credentials haven't expired.
4. **Cloudflare Tunnel:** Check tunnel status in Cloudflare dashboard — auth tokens in AKV may need refresh.

### NAS01 SMART exporter recovery

The host-owned source is `/mnt/local/docker-compose.yml` on NAS01. Edit only
the `smartctl-exporter` service and validate Compose before recreating that
service with `docker compose up -d --no-deps smartctl-exporter`; do not restart
Garage or change pool/disk configuration for an exporter problem.

- Use verified `/dev/disk/by-id` paths with the actual `scsi`, `sat` or `nvme`
  type and the read-only identity-directory mount. Linux `sdX` enumeration is not
  a durable device identity; update the explicit list when replacing hardware.
- The zero-capacity UDISK USB device that appeared as `/dev/sdr` has no supported
  SMART interface and must not be forced into the monitored disk list.
- Version 0.15.0 has a reproduced missing-SAS-descriptor regression:
  [prometheus-community/smartctl_exporter#403](https://github.com/prometheus-community/smartctl_exporter/issues/403),
  with [prometheus-community/smartctl_exporter#397](https://github.com/prometheus-community/smartctl_exporter/pull/397)
  still unmerged at the repair. NAS01 is pinned to official
  `quay.io/prometheuscommunity/smartctl-exporter:v0.14.0` digest
  `sha256:cfe22c36d7d2fac48ebf619707305acb65eb0fb670656eb80f356e606d782bc1`.
  This is a rollback mitigation, not a claim that the upstream bug is fixed.
- After reseating the 8 TB member, the supported inventory is
  35 physical disks: four SAS, twenty-three SATA and eight NVMe.
  The previously unmonitored SATADOM remains omitted: its duplicate ATA
  attribute ID 1 causes duplicate Prometheus samples. A native SMART read
  passes health but reports an unsupported-command bit; do not call it a
  failed disk or claim complete SATADOM telemetry.
- Downgrading alone is insufficient if the SATADOM is included: both versions
  reject its duplicate samples. Changing between `sdX` and stable IDs cannot
  fix either upstream metrics bug.
- Verify `/metrics` returns HTTP 200 after a full five-minute repoll,
  `smartctl_devices` is 35 and the Prometheus target is up. That counter is
  configured inventory, not proof of 35 fresh SMART reads. The default
  `--smartctl.powermode-check=standby` skips sleeping disks; verify missing
  readings with the same `smartctl --nocheck=standby` command and require actual
  standby messages rather than assuming an open failure is harmless.
  Active devices must expose their expected health series. Preserve disk
  spindown; do not silently change the check to `never` just to fill the metrics
  cache. Preserve real historical-error bitmasks and failing-disk alerts.
- Original Compose rollback copies are retained beside the host source.
  Confirm other container identities and `zpool status -x` are unchanged.

### NAS01 stalled shutdown and self-test reporter

- PiKVM **Shortcuts -> Alt+SysRq** provides kernel recovery independent of
  systemd. `S` attempts sync and `U` attempts read-only remount; wait for actual
  completion messages. `B` is an emergency reboot without an implicit flush,
  not a guaranteed clean shutdown. Verify the selected NAS channel, emergency
  reset approval, new boot ID, native jobs and pool state. Do not blindly use
  every REISUB key: the configured bitmask may allow only some operations.
- [nas01_smart_report.py](../scripts/nas01_smart_report.py) is the source for
  `/mnt/local/scripts/smart-report.py`, called by the existing native cron task.
  It discovers every nonzero-capacity rotational `sd*` disk through sysfs and
  opens stable whole-disk `by-id` paths with automatic SAS/SATA detection.
  It reads existing self-test logs; it never starts tests or changes disks.
- Preserve the original 180-second read budget: a healthy drive's native
  command timeout can be 60 seconds. After a read timeout, kill/reap has a
  separate three-second bound and no further devices are probed in that run.
  The inherited lock and bounded kill/reap prevent a stuck SMART child from
  wedging the reporter or causing subsequent invocations to launch more probes.
  They do not repair uninterruptible kernel I/O or a failing controller.
- `nas01_smart_selftest_probe_success` covers every discovered HDD.
  `nas01_smart_selftest_available=0` means no completed stored test, not a
  fabricated pass. Aborted, reset-interrupted or in-progress entries are skipped
  in favor of the most recent completed test, preserving a preceding failure.
  On collection failure the script exits nonzero, reports failure explicitly,
  and retains the previous failed-test/age snapshot and timestamp. The timestamp
  advances only after a complete successful collection; collection and hardware
  failures have separate alerts.
- Before updating the host, retain a protected exact-source rollback copy,
  preserve owner/mode and the existing cron command, and validate:
  `python3 -m unittest discover -s scripts -p test_nas01_smart_report.py`.
  Check native cron completion and actual per-disk Prometheus coverage after
  deployment. Never dismiss real disk failures just to make monitoring green.

### Unpackerr v1 insights and recovery

- The internal-only `unpackerr.homeops.ca` route goes to Authentik's embedded
  proxy, not directly to Unpackerr. Its app-owned
  [identity declaration](../kubernetes/apps/default/unpackerr/identity/application.yaml)
  permits the existing `authentik Admins` group. No local UI password or new
  interactive agent account is provisioned.
- The UI role is limited to queue, history, logs, statistics and system
  information. Queue mutations and configuration writes are denied; existing
  Starr settings and API keys remain GitOps/External Secrets owned.
- The [network policy](../kubernetes/apps/default/unpackerr/app/networkpolicy.yaml)
  allows backend ingress only from Authentik server pods and Prometheus. A
  spoofed identity header from another pod must not reach the application.
  Keep the trusted-proxy settings and policy together.
- Port 5656 serves the UI/API/WebSocket and authenticated metrics. Prometheus
  uses a separate `system:metrics:read` key from the `unpackerr` Key Vault
  secret, through External Secrets; that key cannot access the UI API.
- The `unpackerr` PVC stores `/config`, logs and JSONL history and is backed up
  by Kopiur. The NFS downloads mount is unchanged. Keep a single extractor:
  the workload uses `Recreate`, not overlapping rolling-update workers.
  Settings remain environment/External Secrets owned; an optional TOML file is
  not required in this mode. JSONL history is created when extraction events
  occur, not merely because an idle process starts.
- Before a future major update, use an isolated synthetic archive with no
  production Starr credentials or writable downloads. Verify authentication,
  rejected writes, metrics, WebSocket updates and history across restart.
  The v1 extractor intentionally changes the default Starr expansion-ratio cap
  from 5:1 to 7.5:1; do not claim identical extraction behavior or invent an
  unsupported setting to hide that change.
- Rollback requires quiescing the extractor, pinning the prior image, disabling
  its new web exposure as appropriate, and preserving the PVC/history and
  source downloads. Do not delete the PVC or use a force Helm upgrade to
  recover a configuration problem.

---

## Torrent port-forward configuration

qBittorrent uses a dedicated LoadBalancer IP (`192.168.69.123`) on port `31288` for inbound BitTorrent peer connections. This is separate from the web UI (which goes through envoy-internal at `192.168.69.121`).

### Firewall port-forward on fw01 (OPNsense)

The firewall NAT rule must forward WAN:31288 → `192.168.69.123:31288`.
The alias that backs the destination (e.g., `torrent_hosts`) **must contain only the direct IP** — never the hostname `qbittorrent.homeops.ca`.

**Why:** `qbittorrent.homeops.ca` resolves to `192.168.69.121` (envoy-internal) via unbound DNS override.
If the hostname is in the alias alongside the direct IP, OPNsense creates a round-robin table entry and 50% of inbound torrent connections will be forwarded to the wrong IP, silently breaking peering with private trackers and causing ratio degradation.

**Correct alias config (torrent_hosts):**

```
192.168.69.123    ← direct LB IP only
```

**Verify port-forward is working:**

```bash
# From fw01: confirm pf state table shows ESTABLISHED connections on :31288
pfctl -ss | grep 31288

# From a LAN host: confirm the port is reachable
nc -zv 192.168.69.123 31288

# From Gatus: the "qBittorrent BitTorrent Port" service endpoint should show success
# at https://status.homeops.ca
```

### Monitoring

After a rebuild, verify:

- Gatus endpoint `services / qBittorrent BitTorrent Port` → green (TCP 192.168.69.123:31288)
- Prometheus alert `QBittorrentUploadStalled` is NOT firing (upload > 1 KB/s when seeders > 10)
- Reannounce all torrents to trackers after any port-forward disruption:
    - qBittorrent → select all → right-click → Force Reannounce
    - or via API: `curl -X POST 'http://qbittorrent.homeops.ca/api/v2/torrents/reannounce?hashes=all'`
