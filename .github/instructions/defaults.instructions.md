---
description: >-
  Default route instructions for all agents operating on this repository.
  These instructions apply when no task-specific or user-provided instructions
  override them. Priority: user instructions > task-specific instructions > these defaults.
  Agents MUST consult this file before starting work, during work, and before signaling completion.
---

# Default Agent Instructions — home-ops

## 1. Mandatory Completion Protocol

**You are NOT done until you have completed ALL of the following steps.** Do not signal task completion, summarize, or stop executing until every item is checked off.

### 1.1 Validate Your Changes
- After EVERY file edit, run the relevant reconciliation or build command to confirm the change took effect.
- After EVERY Kubernetes manifest change: `flux reconcile` the relevant Kustomization and verify pod/service status.
- After EVERY Talos config change: `talosctl apply-config` and verify with `talosctl get machinestatus`.
- After EVERY firewall change: verify with `drill`/`dig` or `pfctl` that the expected behavior is observed.
- Never assume a change worked — **prove it** with a command that shows the new state.

### 1.2 Update Documentation
- If you change infrastructure, update the relevant section in `docs/REBUILD-RUNBOOK.md` or add comments in the affected manifests.
- Keep commit messages descriptive: `fix(network): restore homeops.ca DNS overrides on fw01 unbound` not `fix stuff`.

### 1.3 Clear Change Record
- After completing a set of changes, run `git status` to confirm there are no uncommitted changes.
- If changes were made, commit and push them. Do not leave dirty working trees.

### 1.4 Post-Change Health Check (MANDATORY — Every Time)
After completing your primary task, you MUST perform a full health check pass before stopping:

```
# 1. Flux status — all KS and HR must be True/Ready
flux get ks --no-header | grep -v True
flux get hr -A --no-header | grep -v True

# 2. Gatus endpoints — check for failures
curl -sk https://status.homeops.ca/api/v1/endpoints/statuses | python3 -c "
import sys,json; data=json.load(sys.stdin)
ok=sum(1 for e in data if e.get('results',[{}])[-1].get('success'))
fail=sum(1 for e in data if not e.get('results',[{}])[-1].get('success'))
print(f'Gatus: {ok} healthy, {fail} unhealthy')
[print(f'  FAIL [{e.get(\"group\",\"\")}] {e[\"name\"]}') for e in data if e.get('results',[{}]) and not e['results'][-1].get('success')]
"

# 3. Alertmanager — list all active (non-Watchdog) alerts
curl -sk https://alertmanager.homeops.ca/api/v2/alerts | python3 -c "
import sys,json
alerts=[a for a in json.load(sys.stdin) if a['status']['state']=='active' and a['labels'].get('alertname')!='Watchdog']
print(f'Active alerts: {len(alerts)}')
for a in alerts:
  print(f'  [{a[\"labels\"].get(\"severity\",\"?\")}] {a[\"labels\"][\"alertname\"]}')
"

# 4. Pod health — no CrashLoopBackOff or Error pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers | grep -v Completed

# 5. CNPG database cluster
kubectl get cluster -n database -o jsonpath='{.items[0].status.phase}: {.items[0].status.readyInstances}/{.items[0].status.instances}'

# 6. Ceph health
kubectl exec -n rook-ceph deploy/rook-ceph-tools -- ceph status 2>/dev/null | head -5
```

**You must report the results of this health check.** If any system is degraded, either fix it or explicitly document why it cannot be fixed right now.

## 2. Production Safety Rules

### 2.1 Firewall (fw01 — 192.168.42.1, OPNsense/FreeBSD)
- **NEVER** modify `/conf/config.xml` directly for anything other than SSH key management without explicit user approval.
- **NEVER** restart services like unbound, pf, or the firewall itself without explicit user approval.
- DNS overrides via `unbound-control` are acceptable for immediate fixes but MUST be persisted in `/var/unbound/etc/homeops-override.conf`.
- After ANY DNS change on fw01, verify with `drill <hostname> @127.0.0.1` from fw01 AND test from a LAN client.
- Port forwards and NAT rules: verify with `pfctl -sr | grep <port>` and `pfctl -t <table> -T show`.

### 2.2 NAS (nas02 — 192.168.42.10)
- Do not modify NFS exports, ZFS datasets, or system services without explicit user approval.
- File permission fixes (chown/chmod) on NFS shares are acceptable when fixing known issues.

### 2.3 Proxmox (pve01 — 192.168.99.40)
- Do not modify VMs, storage, or networking without explicit user approval.

### 2.4 Talos Nodes (k8s01-06)
- Config changes require `talosctl apply-config`. Never use `--mode=reboot` without explicit user approval.
- Verify all 3 etcd members and API servers are healthy after ANY control plane change.

## 3. Architecture Reference

### 3.1 DNS Resolution Flow
- **LAN clients** → fw01 unbound (192.168.42.1:53) → internal apps override to envoy-internal (192.168.69.121), external apps passthrough to Cloudflare.
- **Cluster pods** → CoreDNS → template plugin resolves `*.homeops.ca` to 192.168.69.121.
- **External users** → Cloudflare DNS → CNAME → Cloudflare Tunnel → envoy-external (192.168.69.126).
- The fw01 unbound DNS override file is at `/var/unbound/etc/homeops-override.conf`. When adding a new internal-only app, add its `local-data` entry here.

### 3.2 Gateway Routing
- **envoy-internal** (192.168.69.121): All internal-only HTTPRoutes + some dual-homed apps (plex).
- **envoy-external** (192.168.69.126): External-facing apps (gatus/status, seerr, home-assistant, plex, echo, kromgo, flux-webhook).
- New internal apps need: HTTPRoute with `parentRef: envoy-internal` AND a DNS entry in fw01's homeops-override.conf.
- New external apps need: HTTPRoute with `parentRef: envoy-external` AND a Cloudflare DNS record (managed by external-dns or manually).

### 3.3 Key IPs
| Resource | IP | Notes |
|---|---|---|
| fw01 (OPNsense) | 192.168.42.1 | Primary firewall, DNS server for all VLANs |
| nas02 (TrueNAS) | 192.168.42.10 | NFS storage for PVCs |
| pve01 (Proxmox) | 192.168.99.40 | Hypervisor hosting gw01 VM |
| k8s01-03 (CP) | 192.168.42.51-53 | Talos control plane nodes |
| k8s04-06 (Workers) | 192.168.42.54-56 | Talos worker nodes |
| envoy-internal | 192.168.69.121 | Internal gateway LB |
| envoy-external | 192.168.69.126 | External gateway LB |
| kube-api LB | 192.168.69.120 | Kubernetes API LoadBalancer |
| qbittorrent LB | 192.168.69.123 | Torrent client (port 31288) |
| smtp-relay | 192.168.69.122 | Maddy SMTP relay (port 587) |

### 3.4 Secrets Management
- Azure Key Vault (`keyvault-kube`) via ExternalSecrets operator.
- `scripts/akv-inject.sh` injects AKV secrets into Talos configs. **WARNING**: Sort placeholders longest-first to avoid prefix corruption (see repo memory).

## 4. GitOps Workflow
- All changes go through Git → Flux reconciliation. Do not `kubectl apply` manifests directly except for emergency hotfixes.
- Emergency hotfixes MUST be followed by committing the equivalent change to Git.
- Flux source: `osnabrugge/home-ops` on GitHub, branch `main`.
- HelmReleases use `oci://` charts where possible.

## 5. Monitoring & Alerting Expectations
- **Gatus** at `status.homeops.ca` — monitors all HTTP endpoints. Target: 0 unhealthy.
- **Alertmanager** at `alertmanager.homeops.ca` — target: only Watchdog alert active.
- **Prometheus** at `prometheus.homeops.ca` — all scrape targets should be UP.
- **Grafana** at `grafana.homeops.ca` — dashboards for Ceph, node metrics, Flux.

## 6. When You Think You Are Done — READ THIS

**Stop. You are not done.** Before calling task_complete or telling the user you are finished:

1. Re-read the user's original request. Did you address EVERY point?
2. Run the Section 1.4 health check. Report the results.
3. If there are new failures that weren't there before you started, FIX THEM before stopping.
4. If you made changes to the cluster, verify they are committed and pushed to Git.
5. Summarize what you did, what the current health status is, and what (if anything) remains to be done.

**The minimum acceptable output is**: changes made + validation proof + health check results + remaining issues list.

Do NOT:
- Stop after completing one item from a multi-item request.
- Signal completion without running validation commands.
- Leave uncommitted changes in the working tree.
- Ignore alerts or failures that appeared during your work.
- Make a single-item todo list when the user gave you multiple tasks.
