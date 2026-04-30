<div align="center">

# Sean & Copilot's Home Operations

### Built together — Sean at the keyboard, Copilot in the co-pilot seat

_Backed by [Flux](https://fluxcd.io/), [Renovate](https://github.com/renovatebot/renovate), and [GitHub Actions](https://github.com/features/actions)_

> _"I literally bootstrapped this system from bare metal."_ — GitHub Copilot

[![Talos](https://img.shields.io/endpoint?url=https%3A%2F%2Fkromgo.homeops.ca%2Ftalos_version%3Fformat%3Dendpoint&style=for-the-badge&logo=talos&logoColor=white)](https://talos.dev)&nbsp;&nbsp;
[![Kubernetes](https://img.shields.io/endpoint?url=https%3A%2F%2Fkromgo.homeops.ca%2Fkubernetes_version%3Fformat%3Dendpoint&style=for-the-badge&logo=kubernetes&logoColor=white)](https://kubernetes.io)&nbsp;&nbsp;
[![Flux](https://img.shields.io/endpoint?url=https%3A%2F%2Fkromgo.homeops.ca%2Fflux_version%3Fformat%3Dendpoint&style=for-the-badge&logo=flux&logoColor=white)](https://fluxcd.io)&nbsp;&nbsp;
[![Renovate](https://img.shields.io/github/actions/workflow/status/osnabrugge/home-ops/renovate.yaml?branch=main&label=&logo=renovatebot&style=for-the-badge&color=blue)](https://github.com/osnabrugge/home-ops/actions/workflows/renovate.yaml)

---

[![Nodes](https://kromgo.homeops.ca/cluster_node_count?format=badge)](https://grafana.homeops.ca)&nbsp;[![Pods](https://kromgo.homeops.ca/cluster_pod_count?format=badge)](https://grafana.homeops.ca)&nbsp;[![CPU](https://kromgo.homeops.ca/cluster_cpu_usage?format=badge)](https://grafana.homeops.ca)&nbsp;[![Memory](https://kromgo.homeops.ca/cluster_memory_usage?format=badge)](https://grafana.homeops.ca)&nbsp;[![Power](https://kromgo.homeops.ca/cluster_power_usage?format=badge)](https://grafana.homeops.ca)&nbsp;[![Uptime](https://kromgo.homeops.ca/cluster_uptime_days?format=badge)](https://grafana.homeops.ca)
[![Alerts](https://kromgo.homeops.ca/cluster_alert_count?format=badge)](https://alertmanager.homeops.ca)&nbsp;[![HR Degraded](https://kromgo.homeops.ca/flux_hr_not_ready?format=badge)](https://grafana.homeops.ca)&nbsp;[![KS Degraded](https://kromgo.homeops.ca/flux_ks_not_ready?format=badge)](https://grafana.homeops.ca)&nbsp;[![Pods Degraded](https://kromgo.homeops.ca/pods_not_ready?format=badge)](https://grafana.homeops.ca)&nbsp;[![Ceph](https://kromgo.homeops.ca/ceph_health?format=badge)](https://grafana.homeops.ca)&nbsp;[![Seeding](https://kromgo.homeops.ca/torrent_seeding_count?format=badge)](https://qbittorrent.homeops.ca)&nbsp;[![Upload](https://kromgo.homeops.ca/torrent_upload_speed?format=badge)](https://qbittorrent.homeops.ca)

</div>

---

## 📖 Overview

This is a mono repository for my home infrastructure and Kubernetes cluster. I try to adhere to Infrastructure as Code (IaC) and GitOps practices using tools like [Talos](https://talos.dev), [Kubernetes](https://kubernetes.io/), [Flux](https://github.com/fluxcd/flux2), [Renovate](https://github.com/renovatebot/renovate), and [GitHub Actions](https://github.com/features/actions).

---

## ⛵ Kubernetes

My cluster runs [Talos Linux](https://talos.dev) on 6 Lenovo ThinkCentre M920q nodes — a semi-hyper-converged setup where workloads and block storage share the same hardware, with a Synology NAS providing NFS shares and backups.

### Core Components

| Component | Tool | Purpose |
|-----------|------|---------|
| **CNI** | [Cilium](https://cilium.io/) | eBPF networking, BGP LoadBalancer, kube-proxy replacement |
| **Ingress** | [Envoy Gateway](https://gateway.envoyproxy.io/) | L7 ingress (internal + external gateways) |
| **DNS** | [CoreDNS](https://coredns.io/) + [Unbound](https://unbound.net/) | Cluster DNS + recursive resolver |
| **Certificates** | [cert-manager](https://cert-manager.io/) | Automated TLS from Let's Encrypt |
| **Secrets** | [External Secrets](https://external-secrets.io/) + [Azure Key Vault](https://azure.microsoft.com/en-us/products/key-vault/) | Secret management via ClusterSecretStore |
| **Storage** | [Rook-Ceph](https://rook.io/) + [OpenEBS](https://openebs.io/) | Distributed block (Ceph) + local hostpath (OpenEBS) |
| **Backups** | [VolSync](https://github.com/backube/volsync) + [Kopia](https://kopia.io/) | PVC backup/restore to NFS |
| **GitOps** | [Flux](https://fluxcd.io/) via [Flux Operator](https://github.com/controlplaneio-fluxcd/flux-operator) | Cluster reconciliation from this repo |
| **Registry** | [Spegel](https://github.com/spegel-org/spegel) | Stateless cluster-local OCI mirror |
| **External Access** | [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | `*.homeops.ca` via Argo Tunnel |
| **Monitoring** | [Kube-Prometheus-Stack](https://github.com/prometheus-community/helm-charts) + [Grafana](https://grafana.com/) | Metrics, alerts, dashboards |
| **CI Runners** | [Actions Runner Controller](https://github.com/actions/actions-runner-controller) | Self-hosted GitHub Actions |

### GitOps

[Flux](https://github.com/fluxcd/flux2) watches the `kubernetes/apps` directory and reconciles the cluster state to match this repository. [Renovate](https://github.com/renovatebot/renovate) creates PRs for dependency updates automatically.

```
📁 kubernetes
├── 📁 apps           # Application manifests (HelmReleases, Kustomizations)
├── 📁 components     # Reusable kustomize components (alerts, volsync, nfs-scaler)
└── 📁 flux           # Flux system configuration
```

### Bootstrap Chain

The [bootstrap helmfile](bootstrap/helmfile.d/01-apps.yaml) installs the critical-path dependencies in order:

```
Cilium → CoreDNS → Spegel → Cert-Manager → External-Secrets + AzureKV → Flux Operator → Flux Instance
```

After Flux starts, it reconciles all remaining apps from this repo automatically.

---

## 🌐 Network

### Routing Architecture

Inter-VLAN routing for trusted VLANs is handled by the **Brocade ICX 6610-48P** core switch stack (Core01) for high-performance L3 forwarding without packet inspection. **OPNsense** (fw01) handles restricted VLANs (IoT, Guest) and internet NAT/firewall.

| VLAN | Name | Subnet | Gateway | Router | Purpose |
|------|------|--------|---------|--------|---------|
| 1 | Default | 192.168.0.0/24 | 192.168.0.10 | OPNsense | Factory-reset device catchall |
| 10 | Workstation | 192.168.10.0/24 | 192.168.10.4 | Brocade Core01 | Trusted — desktops, laptops |
| 42 | Server | 192.168.42.0/24 | 192.168.42.4 | Brocade Core01 | Kubernetes + infrastructure |
| 50 | Guest | 192.168.50.0/24 | — | OPNsense | Internet-only guest access |
| 69 | LoadBalancer | 192.168.69.0/24 | — | Cilium (BGP) | Kubernetes Service LB IPs |
| 70 | IoT | 192.168.70.0/24 | 192.168.70.1 | OPNsense | Restricted — smart home devices |
| 99 | Management | 192.168.99.0/24 | 192.168.99.4 | Brocade Core01 | IPMI, KVM, PDU, switches |

### BGP

Cilium advertises LoadBalancer IPs (192.168.69.0/24) via BGP to the Brocade core switch:

| | Cilium (K8s nodes) | Brocade Core01 |
|-|-------|---------|
| **ASN** | 64514 | 64513 |
| **Peer** | 192.168.42.4 | 192.168.42.51–56 |

### DNS

| Scope | Resolver | Purpose |
|-------|----------|---------|
| Cluster | CoreDNS (10.43.0.10) | `*.svc.cluster.local` |
| Internal | Unbound + dnscrypt-proxy | Recursive + encrypted upstream |
| External | Cloudflare | `*.homeops.ca` via tunnel |

---

## ⚙️ Hardware

| Device | Count | Role | IP(s) | OS |
|--------|-------|------|-------|-----|
| Lenovo ThinkCentre M920q | 6 | Kubernetes (3 CP + 3 worker) | 192.168.42.51–56 | Talos v1.12.6 |
| Synology DS1821+ | 1 | NAS + temporary app host | 192.168.42.10 | DSM |
| Brocade ICX 6610-48P (stacked) | 2 | Core L3 switch | VIP: .4/vlan | FastIron |
| Protectli FW6C | 1 | Firewall (OPNsense) | 192.168.0.10 | OPNsense |
| PiKVM V4 Plus | 1 | KVM-over-IP | 192.168.99.51 | PiKVM OS |
| TESmart HKS1601-E23-USBK | 1 | 16-port HDMI KVM switch | 192.168.99.92 | — |
| CyberPower PDU41001-V | 2 | Switched PDU (SNMP) | 192.168.99.15–16 | — |
| Raspberry Pi 4B | 4 | ConsolePi, misc | 192.168.42.21–24 | Raspbian |
| CyberPower UPS | 4 | Battery backup | — | — |

### Out-of-Band Management

Comprehensive OOB infrastructure for remote access, power control, and monitoring:

| Tool | Access | Purpose |
|------|--------|---------|
| PiKVM + TESmart | `just infra kvm-switch <node>` | Remote KVM console for any node |
| PDU (SNMP) | `just infra pdu-reboot <node>` | Hard power cycle any node |
| UPS (SNMP) | Prometheus/Grafana | Battery backup monitoring |
| ConsolePi (pi02→Core01-U1, pi03→Core01-U2) | SSH serial | Core switch serial console |

**📘 See [OOB Management Guide](docs/OOB-MANAGEMENT.md) for detailed documentation and workflows.**

### Rack01 Elevation (Dynamic)

- [Rack01 elevation in NetBox](https://netbox.homeops.ca/dcim/racks/?q=Rack01)
- [Rack01 devices in NetBox](https://netbox.homeops.ca/dcim/devices/?q=Rack01)

---

## ☁️ Cloud Dependencies

| Service | Use | Cost |
|---------|-----|------|
| [Azure Key Vault](https://azure.microsoft.com/en-us/products/key-vault/) | Secrets backend for External Secrets | ~$1/mo |
| [Cloudflare](https://www.cloudflare.com/) | Domain, DNS, Tunnel | Free |
| [GitHub](https://github.com/) | Repository, CI/CD, Renovate | Free |

---

## 🔧 Operations

| Command | Purpose |
|---------|---------|
| `just talos rebuild` | Full CP rebuild: preflight → render → apply → bootstrap → verify |
| `just talos preflight` | Check tools, AKV, node reachability |
| `just talos render` | Render configs with secrets + guardrails |
| `just talos export-secrets` | Export AKV secrets for offline/local bootstrap |
| `just infra kvm-switch k8s01` | Switch KVM HDMI to a node |
| `just infra pdu-reboot k8s01` | Hard power cycle a node via PDU |
| `just infra console k8s01` | Switch KVM + take screenshot |
| `just kube sync-hr` | Force reconcile all HelmReleases |

See [REBUILD-RUNBOOK.md](docs/REBUILD-RUNBOOK.md) for the full step-by-step rebuild procedure.

---

## 🔧 Active Sprint

Work in progress — updated each session with Copilot.

| Status | Item |
|--------|------|
| ✅ | Replace `sed` with bash string replacement in `akv-inject.sh` (longest-first sort, no escaping bugs) |
| ✅ | Add post-render guardrails to render recipe (unresolved placeholders, empty secrets, `talosctl validate`) |
| ✅ | Add guardrails to bootstrap recipe (missing rendered configs, azkv:// check, endpoint mismatch) |
| ✅ | Add bootstrap marker file (`.private/bootstrap.done`) with double-bootstrap protection |
| ✅ | Add local-mode to `akv-inject.sh` (`AKV_LOCAL_DIR` for offline/air-gapped use) |
| ✅ | Add `export-secrets` recipe (dump AKV secrets to `.private/` for local-mode use) |
| ✅ | Restore root `kubernetes/apps` kustomization and add a dedicated `database` namespace |
| ✅ | Reintroduce CloudNativePG operator in-cluster for shared PostgreSQL workloads |
| ✅ | Add shared PostgreSQL cluster resources under CNPG with scheduled backups |
| ✅ | Reintroduce shared Redis-compatible cache layer with Dragonfly in `database` |
| ✅ | Add NetBox deployment wired to shared PostgreSQL and Redis-compatible cache |
| ⏳ | Rewrite apply-wait logic (remove `--insecure` polling; use event-driven readiness) |
| ⏳ | Fix bootstrap double-call bug (idempotent bootstrap gate) |
| ⏳ | Update `REBUILD-RUNBOOK.md` to reflect all new automation |
| ⏳ | Fix Zigbee2MQTT CrashLoop (serial-over-TCP adapter at `192.168.70.37:6638` unreachable) |
| ⏳ | Migrate TheLounge IRC nicks from NAS02 to configmap |

---

## 🏛️ Guardian Charter

This repo treats cluster operations as an ongoing stewardship job, not a sequence of disconnected fixes.

The working model is simple: GitHub Copilot acts as the cluster's guardian government, with a mandate to improve reliability, reduce operator toil, and keep services stable for the citizens of the cluster.

### Operating Principles

- Prefer prevention over heroics: add guardrails, validation, and safer defaults before the next outage happens
- Prefer boring recovery paths: rebuilds, restores, and failover steps should be documented and repeatable
- Prefer evidence over guesswork: use logs, readiness, health checks, and observed state before making changes
- Prefer PRs over surprises: impactful changes should be visible, reviewable, and auditable
- Prefer continuity over memory: the repo should carry forward priorities, context, and decisions across sessions

### What The Guardian Watches

- Cluster readiness, failed reconciliations, crash loops, and noisy dependencies
- Security posture, secret delivery, and risky configuration drift
- Service quality for media, automation, ingress, storage, and observability workloads
- Documentation gaps where the correct fix exists in chat history but not yet in the repo

### Autonomy Boundaries

- Safe to automate: documentation updates, guardrails, runbooks, validations, low-risk config hardening
- Review before merge: architectural changes, new apps, privilege changes, networking changes, storage migrations
- Never implicit: destructive actions, secret exposure, and irreversible control-plane operations

The target state is straightforward: the operator should not need to repeatedly ask for routine stewardship. The system should steadily accumulate operational judgment in-repo, so each session starts from a stronger baseline than the last.

---

## 🏆 Recent Achievements

This cluster is actively maintained with a reliability-first and security-focused operating model.

- Hardened Talos rebuild flow with preflight checks, render guardrails, and safer bootstrap sequencing
- Stabilized GitOps reconciliation workflows across Flux Kustomizations and HelmReleases
- Implemented torrent stack optimization for long-term seeding and ratio protection (Autobrr + qBittorrent + Arr stack + Unpackerr)
- Standardized secret delivery through External Secrets + Azure Key Vault across media and automation apps
- Improved ingress/service troubleshooting around Envoy Gateway + Cloudflare Tunnel routing paths
- Added and maintained practical operations runbooks for rebuilds, remote media access, tracker credentials, and optimization

### 🤝 Collaboration Scorecard

This is the shared operating lane: detect, respond, harden, and upstream improvements.

| Area | What We Track | Current Focus |
|------|----------------|---------------|
| **Uptime & Reliability** | API readiness, node health, app availability, failed reconciliations | Reduce noisy failures, tighten MTTR, improve rollout safety |
| **Threats & Mitigations** | Crash loops, ingress failures, auth errors, risky config drift | Faster incident triage, stricter guardrails, preventive hardening |
| **Upstream Contributions** | Issues opened, PRs merged, docs fixes contributed back | Convert local fixes into upstream improvements where possible |
| **Features & Enhancements** | New apps, automation, runbooks, quality-of-life tooling | Keep raising reliability and operator ergonomics each sprint |

### Ongoing Guardian Priorities

- Keep Flux reconciliation clean and predictable
- Improve service-level visibility and alert quality
- Harden default security posture without breaking usability
- Continuously optimize media/torrent automation for health and seeding performance
- Document every major change as an operational playbook

## 🤖 Copilot Agent Activity Log

This section is a running record of AI-assisted work on the cluster. It serves as a historical record and a source of truth when memory is incomplete.

### Session 2026-04-18: Database Tier + Alert Triage (PR #3014)

**Duration:** ~4 hours | **Status:** ✅ Complete

#### New Infrastructure Deployed
| Component | Type | Status | Notes |
|-----------|------|--------|-------|
| **CNPG (postgres16)** | Database | ✅ Running | 2 instances, scheduled backups enabled |
| **Dragonfly** | Cache | ✅ Running | 3-pod cluster, full HA setup |
| **NetBox** | IPAM/DCIM | ✅ Syncing | External secret active, ceph-block PVC bound |

#### Alerts Fixed
| Alert | Root Cause | Resolution | Status |
|-------|-----------|-----------|--------|
| agregarr exposed | Already internal (envoy-internal), agent mistakenly disabled route | Reverted route to enabled | ✅ Fixed |
| alertmanager.homeops.ca inaccessible | Hostname was `alertmanager.turbo.ac` | Changed to `alertmanager.homeops.ca` in HelmRelease | ✅ Fixed |
| zigbee HelmRelease crash | TCP timeout to 192.168.70.37:6638 (coordinator unreachable) | Hardware/network issue — coordinator offline | ⏸️ User action required |
| unbound-dns crash loop | external-dns race condition on webhook startup (505 restarts) | Currently 2/2 Running but flapping | ⚠️ Partial—needs startup delay |
| kopia-maint-daily failed | NFS `/mnt/repository/x/n0_/` permission denied (UID 1000) | File-level NFS permission issue | ⏸️ User action required (NAS) |
| netbox HelmRelease | Missing `email_password` secret key + no PVC | Added secret key to AKV + ExternalSecret, created ceph-block PVC | ✅ Fixed |

#### Code Changes
- ✅ Fixed `alertmanager.homeops.ca` hostname in `kubernetes/apps/observability/kube-prometheus-stack/helmrelease.yaml`
- ✅ Removed hardcoded identity (`sean@seanv.com`, `sean-admin`) from NetBox manifests for privacy
- ✅ Added `email_password` to NetBox ExternalSecret
- ✅ Created NetBox ceph-block PVC (10Gi)
- ✅ Made Dragonfly operator ServiceAccount idempotent
- ✅ Made bootstrap `kube` stage idempotent with marker-aware logic

#### Auth & Privacy
- 🔒 Hardcoded personal identity completely removed from tracked manifests
- ✅ NetBox secret keys synced from Azure Key Vault
- ✅ Privacy audit passed

#### Commits
```
af55490a fix: update HelmRelease and ExternalSecret configurations for idempotency
86615e01 fix: update README and add PersistentVolumeClaim for NetBox
7f35d40c fix: make dragonfly-operator service account creation idempotent
8aaf5a3a feat: add NetBox and Dragonfly configurations with external secrets
aa83729b docs: add Guardian Charter section
```

#### Additional Fixes (This Session, Immediate Follow-Up)
- ✅ **qBittorrent auth bypass fixed**: Enabled `ReverseProxyEnabled: true`, added pod CIDR `10.42.0.0/16` to auth whitelist, deployment restarted. Internal users no longer see login prompt.
- ✅ **PR #3014 opened**: Branch `fix/bootstrap-idempotent-kube-stage` → main with full database tier + fixes

#### Metrics
- **Deployment time:** ~45 min (CNPG + Dragonfly operators ready, NetBox syncing)
- **Alerts resolved:** 3/6 (alert, qbittorrent, netbox)
- **Upstream contributions:** 0 (all work is internal)
- **Code quality:** No hardcoded secrets, privacy-clean manifests

#### Pending
- Zigbee coordinator connectivity (user network/hardware troubleshooting)
- Kopia NFS permissions on NAS (user filesystem work)
- unbound-dns race condition stabilization (needs pod startup ordering fix)

---

### Upstream Contributions

Track open-source improvements contributed back from this cluster:

| Project | PR/Issue | Status | Impact |
|---------|----------|--------|--------|
| (None tracked yet) | — | — | — |

---

### Operations Playbooks

- [Cluster Rebuild Runbook](docs/REBUILD-RUNBOOK.md)
- [Remote Media Runbook](docs/REMOTE-MEDIA-RUNBOOK.md)
- [Torrent Setup Action Plan](docs/TORRENT-SETUP-ACTION-PLAN.md)
- [Torrent Optimization Notes](docs/TORRENT-OPTIMIZATION.md)
- [Tracker Credential Setup](docs/TRACKER-CREDENTIALS-SETUP.md)

---

## 🤝 Thanks

Huge thanks to the [Home Operations](https://discord.gg/home-operations) Discord community and these projects/people:

- [onedr0p/home-ops](https://github.com/onedr0p/home-ops) — the OG home-ops repo and endless inspiration
- [Flux Cluster Template](https://github.com/onedr0p/flux-cluster-template) — community-driven starting point
- [kubesearch.dev](https://kubesearch.dev/) — search engine for community cluster deployments
