# Operations Backlog

This file is the persistent task tracker. **It is the source of truth, not the chat.**

> **Working rule (added 2026-08-03, after repeatedly losing scope):**
> Any multi-part request gets written here *before* work starts. When a request is
> answered only partially, the untouched parts stay listed here as `[ ]` — they are
> never silently dropped because the conversation moved on. Every session should
> start by reading this file and end by updating it. Long term this moves into
> NetBox so inventory + tasks live in one queryable place.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[?]` needs a decision from Sean

---

## A. Active program — nas01 storage design (requested 2026-08-03)

**Context Sean gave:** nas01 is greenfield, no data needed preserving. The ask was
never "just build a pool" — it was **design options → benchmarks → optimization →
baseline**, chosen against his actual workloads and the hardware present. That did
not happen; `vault` was created unilaterally with one `kopiur` dataset and no
rationale. This section is the redo.

- [ ] P0: Write up **why the current `vault` layout exists** (6× 2-way mirror + mirrored
      Optane SLOG + 1 L2ARC) and its trade-offs — Sean never got an explanation
- [ ] P0: Produce **≥3 design options** with explicit trade-offs (capacity vs IOPS vs
      resilience vs rebuild risk), costed against hardware actually on hand
- [ ] P0: Benchmark plan + **baseline numbers** (only `seqwrite1m = 788.3 MB/s` exists so far)
- [ ] P0: Post-design optimization pass (recordsize per dataset, ashift, compression,
      special vdev, ARC/L2ARC decision) — all measured, not folklore
- [ ] P1: Charts/graphs of results, not just tables (Sean asked for this explicitly)

### A.1 What currently depends on nas01 (must not break)

- [x] P0: **ANSWERED 2026-08-03 — nas01 holds ZERO data and can be rebuilt freely.**
      Evidence:
      - Exactly **one** reference to nas01 in all of `kubernetes/`: netboot-xyz mounts
        `nas01.in.homeops.ca:/mnt/vault/netboot` for ISO assets.
      - That directory is **empty** (no ISOs were ever placed there).
      - kopiur's only `ClusterRepository` is **`nas02`** — backups do **not** go to nas01.
        The `vault/kopiur` dataset exists but is unused (96 K).
      - `vault` total allocated: **1.96 MB** across `vault/kopiur` + `vault/netboot`.
      **Implication: no cutover, no fallback, no data preservation required.** The pool
      can be destroyed and rebuilt to whatever design we choose. The only cleanup is
      recreating a `netboot` dataset afterwards (or repointing netboot-xyz).


### A.2 Drive inventory available to the design

| Qty | Device | Where | Notes |
|---|---|---|---|
| 12 | mixed HDD (6×4TB, 4×8TB, 2×10TB) | in nas01 `vault` | current pool |
| 4 | 12TB Ironwolf | **in nas02** | free after migration completes |
| 1 | 12TB Ironwolf | **on desk, new spare** | → 5× 12TB total |
| 4 | 20TB Ironwolf | ? confirm location | |
| 4 | Crucial P3 1TB NVMe | nas01 carrier, `CPU2 SLOT 5` | **3 stranded — bifurcation off** |
| 2 | Intel Optane P1600X 118G | nas01 M.2-C1/C2 | SLOG mirror |
| 2 | SATADOM 60G | nas01 | boot-pool (currently **no redundancy**) |
| 3 | 2.5" SATA SSD | spare | Sean suggests → pve01 instead |

- [ ] P0: **Fix PCIe bifurcation** (`CPU2 SLOT 5` → `x4x4x4x4`) to recover 3 NVMe.
      Needs reboot window. No BMC creds stored — iKVM at `192.168.99.45` or `sum`.
- [ ] P1: Confirm location/count of the 4× 20TB Ironwolf
- [ ] P1: Chassis: 36 front bays (12 used) + 24 rear bays — rear needs **3D-printed trays**
- [ ] P2: `boot-pool` redundancy — `sdn` is healthy+idle, can mirror (destroys old `rpool`)

### A.3 Networking for nas01

- [ ] P1: Decide NIC. Options:
      (a) **Silicom PE310G4i71LB-XR** quad SFP+ — on hand, but full-height bracket,
          needs a 3D-printed half-height bracket designed
      (b) **ConnectX-3/4 dual SFP+** from eBay — cheap, but need guidance on which
          models cross-flash and which genuinely support **RDMA**
- [ ] P1: Produce a "what to look for on eBay" note for CX3/CX4 (model numbers,
      OEM-branded vs retail, firmware cross-flashing, RoCE support caveats)

---

## B. Cluster bugs (reported 2026-08-03)

### B.0 RBD `emergency_ro` cascade — ROOT CAUSE FOUND 2026-08-04

Recurred 4 times (Jul 31, Aug 1, Aug 3, Aug 4) because the fix was wrong, not because
the fault kept re-firing.

**Mechanism:** an ext4 journal abort (`ext4_journal_check_start`) from a transient I/O
error flips the filesystem to `emergency_ro`. The mount still *reports* `rw`:
`/dev/rbd2 on /config type ext4 (rw,...,emergency_ro)` — so it looks fine.
**`kubectl rollout restart` CANNOT clear it.** The CSI driver keeps the device staged
at a **globalmount**; the replacement pod lands on the same node, bind-mounts the same
read-only globalmount, and inherits RO. It looks fixed, then fails again.

**Correct procedure:**
1. Scope it: `for ip in 51..56; do talosctl -n 192.168.42.$ip read /proc/mounts | grep -c emergency_ro; done`
2. Map volumes to apps: extract `pvc-<uuid>`, then
   `kubectl get pv <pv> -o jsonpath='{.spec.claimRef.namespace}/{.spec.claimRef.name}'`
3. **Scale EVERY consumer of that PVC on that node to 0 simultaneously** (shared PVCs
   need all of them, e.g. `netbox` + `netbox-worker`)
4. Wait for full pod termination so `NodeUnstageVolume` runs; confirm the node's
   `emergency_ro` count is **0**
5. Scale back up, then **verify with an actual write**, not pod status

Verified 2026-08-04: all 6 nodes at `emergency_ro=0`; agregarr/sonarr/lidarr all
`WRITE OK`. Note agregarr's data path is `/app/config`, not `/config` — testing the
wrong path produces a false "still read-only".

- [ ] P0: **Add detection.** The trigger rotates out of `dmesg` within ~2 days and Ceph
      returns to `HEALTH_OK`, so post-hoc diagnosis is impossible. Need an alert on
      `emergency_ro` present in any node's `/proc/mounts` (and ideally on
      `EXT4-fs error` in kernel logs) so the next occurrence is caught live with cause.
- [ ] P1: Root cause of the *original* I/O error is still unknown. Suspicion: RBD
      map/unmap churn from kopiur backup movers on k8s05/k8s06 (the two nodes hit).
      Unproven — needs the detection above to catch it in the act.


- [~] P0: **frigate ↔ cam03 auth failure** — ROOT-CAUSED, needs a change **on the camera**.
      Not a frigate bug: **go2rtc** cannot authenticate upstream, so frigate's ffmpeg
      gets a 404 from the local restream (`rtsp://127.0.0.1:8554/cam03`).
      Proof (from inside the frigate pod, same URL/user/password):
      `cam02 -> h264,2560,1440` · `cam03 -> 401 Unauthorized`.
      All 3 cams share one credential, so the hard reset wiped cam03's `viewer` account.
      **Action (Sean):** recreate user `viewer` on cam03 with the shared password and
      media/RTSP permission — on Dahua-style firmware the account usually must be in the
      right *group*, matching UI fields alone is not always enough.
- [ ] P0: **ROTATE `FRIGATE_RTSP_PASSWORD`** — it was leaked in plaintext into a chat
      transcript on 2026-08-03 (ffprobe echoes the full RTSP URL in its error output).
      Update AKV + the `viewer` account on cam01/02/03.
- [x] P1: **printguard iGPU** — the update had **silently failed**. Container declared
      `resources.claims[gpu]` + `defaultPodOptions.resourceClaims[gpu]`, but no
      `ResourceClaimTemplate` named `printguard` existed → pods unschedulable → Helm
      timed out → **rolled back to the CPU-only spec** while showing `2/2 Running`.
      Fixed by adding the RCT + `intel-gpu-resource-driver` dependency (`06c4038be`).
      Verified: claim `allocated,reserved`, `/dev/dri` → `card0`, `renderD128`.
- [x] P1: **printguard GPU vs CPU — measured.** printguard self-benchmarks at startup:
      | Backend | Result |
      |---|---|
      | Intel OpenVINO (iGPU) | **234.0 fps** (1 worker) |
      | LiteRT CPU + XNNPACK | **349.8 fps** (2 workers) |
      **CPU wins by ~50 %** and printguard auto-selects it. Expected: k8s01 is an
      **i5-9600T / UHD 630** (24 EU) — a weak iGPU, and small quantised models pay
      per-inference kernel-launch overhead on GPU.
      **Recommendation: leave the GPU claim attached.** Devices are shareable (every
      node advertises 1 device and `drm-exporter` already claims all 6), GPU consumers
      sit on different nodes (plex k8s03, frigate k8s06, dispatcharr k8s04,
      printguard k8s01), so there is no contention — and the startup benchmark will
      automatically switch to GPU if a future model favours it.
- [ ] P2: printguard — Sean tried publishing ports so IP cams could **push** streams;
      the Dahua-knockoff cams appear to have no RTSP-push option. The `mediamtx`
      sidecar already in the pod is the correct receiver for a push model. Confirm
      whether the cams support ONVIF/RTSP push at all; if not, pull + go2rtc restream
      is the right architecture and no port publishing is needed.


---

## C. pve01

- [ ] P0: **Zero drive redundancy.** One NVMe slot was consumed by an NVMe→10GbE SFP+
      adapter (needed to exceed 1 Gbps). Propose a redundancy plan — possibly the
      3× spare 2.5" SATA SSD.
- [ ] P1: Document pve01's current disk/NIC layout in NetBox.

---

## D. WAN / Bell (8 Gbps not delivered)

- [ ] P0: Bell is contracted for ~8 Gbps; speedtest history shows ~3 Gbps. We have
      demonstrated ≥5 Gbps is achievable, so the ceiling is not purely CPE.
- [ ] P0: **Test upstream of gw01/pve01** to isolate: run iperf/speedtest directly from
      the **MikroTik (`ext01.in.homeops.ca`)** and/or the **XPS-GPON (`192.168.11.1`)**.
- [ ] P1: Read the ONT's OLT-provisioned DBA/T-CONT profile if reachable.
- [ ] P1: Build the evidence pack Sean can take to Bell (charts, methodology, dates).

---

## E. NetBox — single source of truth + automation

Sean's months of prior work were re-imported: images, device types, module types,
expansion slots. Out of date but structurally valuable.

- [ ] P0: Clean up + update the imported data against reality
- [ ] P1: Automate the **network** side via **Diode** + **netbox-operator**
- [ ] P1: Evaluate **hardware lifecycle management** plugins
- [ ] P1: Expose NetBox through **MCP** so it is a real-time, single-pane inventory
- [ ] P2: Long-term — drive this backlog from NetBox rather than a markdown file
- [x] netbox-operator fixed (API token restored + `netboxOperatorRestorationHash`
      custom field recreated) — 2026-08-01
- [ ] P1: `API_TOKEN_PEPPERS` is unset → v2 API tokens unusable. Add JSON to secret
      key `api_token_peppers` (int keys, ≥50-char values).

---

## F. Fleet consolidation / spare build

Goal Sean stated: get **everything** online and inventoried so we can run as lean as
possible and **sell off surplus**.

- [?] P1: ASRock Rack **X570D4U-2L2T** + **128 GB ECC** idle ~2 years. Needs a CPU and
      a case. Ryzen Pro 5000-series (e.g. **5600G**, ~$120–150) suggested. Spare ATX
      PSUs available.
- [?] P1: Case — mATX rackmount options are poor. Sean is considering a **3U/4U** that
      fits a spare **360 mm AIO**, with room for more HDDs/GPUs later.
- [ ] P2: Decide whether this box becomes a second NAS, a second PVE node, or is sold.
- [ ] P2: Produce a sell/keep list once inventory is complete.

---

## G. Standing infrastructure work

- [ ] P0: Deep full-infrastructure health sweep (go wide across supporting infra AND
      deep into each app) — Sean wants issues found before he finds them
- [ ] P1: Audit/propose MCP servers (Proxmox, MikroTik, GPON, TrueNAS, Synology,
      Supermicro BMC/IPMI, NetBox, Spoolman, Klipper/Mainsail, Cloudflare, Azure,
      GitHub, Talos, memory/RAG) — reduce firefighting, enable proactive work
- [ ] P1: NFS 4.2 + optimizations — can be scoped per-PV via `spec.mountOptions`
      (does NOT have to wait for the whole nas02→nas01 migration)
- [ ] P1: Radar: 5 open issues, large warning-event volume — drive to zero
- [ ] P2: gw02 deployment strategy — clone gw01 config (interfaces/rules must match for
      CARP/pfsync) without the painful manual console bootstrap
- [ ] P2: Omada adoption end-to-end verification (VLAN99 path proven; adoption untested)
- [ ] P2: Identity: one-pane identity lifecycle (users, groups, systems, devices, SSH,
      RADIUS, MFA, OAuth). Authentik feasibility gate still undecided.

---

## H. Legacy items (pre-2026-08, triage before trusting)

Much of the section below predates the kopiur migration and the app rebuilds; several
entries are stale (e.g. `volsync-system/kopia` no longer exists). Re-verify before
acting on any of it.

## Current Priority (legacy)

- [ ] P0: Open PR for smtp-relay LOGIN fix and merge after review
- [ ] P0: Verify Flux reconciles smtp-relay with no drift after merge
- [ ] P0: Confirm test mail headers in mailbox for latest Seerr notification (SPF/DKIM/DMARC, relay path)

## User-Directed Priority Queue (2026-04-14)

- [ ] P0: Migrate beets workload and data from NAS02 (new app onboarding required)
- [ ] P0: Migrate lidarr workload and data from NAS02 (new app onboarding required)
- [ ] P0: Migrate stash workload and data from NAS02 (new app onboarding required)
- [ ] P0: Migrate whisparr workload and data from NAS02 (new app onboarding required)
- [ ] P0: Migrate unpackerr workload and data from NAS02 (manifest already present)
- [ ] P0: Restore and stabilize home-assistant workload in cluster
- [ ] P0: Restore and stabilize zigbee2mqtt workload in cluster (`zigbee` app)

### External Access Test Policy

- [ ] P0: Validate internal and external access for apps that use Plex auth.
- [ ] P1: Defer external strategy changes for non-Plex-auth apps pending architecture decision.
- [ ] P1: Capture per-app validation status (internal OK, external OK, auth flow OK).

## Cluster Optimization

- [ ] P1: Baseline cluster resource usage (CPU, memory, disk, network) and identify top 10 noisy workloads
- [ ] P1: Right-size requests/limits for default namespace media apps using 7-day metrics
- [ ] P1: Review startup/liveness/readiness probes for long-starting apps and reduce false restart loops
- [ ] P2: Revisit Talos NFS tuning after NAS migration and move `nfsvers=4.1` to `4.2` when safe

Reference:
- [talos/machineconfig.yaml.j2](talos/machineconfig.yaml.j2)

## NAS02 Dependency Migration

Apps currently referencing `nas02.in.homeops.ca` in manifests:

- [ ] P1: bazarr
- [ ] P1: plex
- [ ] P1: qbittorrent
- [ ] P1: qui
- [ ] P1: radarr
- [ ] P1: sabnzbd
- [ ] P1: seasonpackerr
- [ ] P1: slskd
- [ ] P1: sonarr
- [ ] P1: unpackerr
- [ ] P1: volsync-system (kopia + replication)

Apps requested for migration but not yet present under `kubernetes/apps/default`:

- [ ] P0: beets (create app skeleton + secret model + storage plan)
- [ ] P0: lidarr (create app skeleton + secret model + storage plan)
- [ ] P0: stash (create app skeleton + secret model + storage plan)
- [ ] P0: whisparr (create app skeleton + secret model + storage plan)

Migration checklist per app:

- [ ] Confirm destination storage class and capacity
- [ ] Snapshot and restore plan validated (VolSync/Kopia)
- [ ] Cutover window defined and rollback documented
- [ ] Post-cutover functional test completed
- [ ] Old NAS02 mount references removed from manifest

## App Health Validation Sweep

- [ ] P1: Build a scripted health sweep for all apps in `kubernetes/apps/default`
- [ ] P1: Verify each app endpoint responds and each workload is `Ready` with no crash loops
- [ ] P1: Capture and triage failing probes in a single report

### In-cluster health-sweep CronJob that files a GitHub issue (designed 2026-06-21, NOT yet built)
There is currently **no** in-cluster cronjob — only `just kubernetes health-sweep` (local,
manual, `scripts/health-sweep.sh`). To make findings surface automatically:
- CronJob (daily) in `observability` running the sweep + a resource right-sizing check
  (OOM-risk: peak >85% of limit; over-provisioned: request >2x 7d peak) via Prometheus.
- Read-only cluster RBAC (ServiceAccount: get/list pods, events, deploy/sts; no secrets).
- Opens/updates ONE deduplicated GitHub issue on `osnabrugge/home-ops` (search by a fixed
  marker label/title, PATCH if open else POST) so it doesn't spam.
- **BLOCKER (needs user decision):** a GitHub credential. Options: reuse the
  `actions-runner-system` GitHub App (needs app id + installation token minting in the job)
  OR a dedicated fine-grained PAT in AKV (`GITHUB_HEALTHSWEEP_PAT`, issues:write on the repo)
  surfaced via ExternalSecret. Pick one, then wire the CronJob + RBAC + ExternalSecret.
- [ ] P1: Add/adjust missing probes where needed

### First Sweep Findings (2026-04-14)

- [ ] P0: Fix `default/zigbee` CrashLoopBackOff (startup probe connect refused)
- [ ] P0: Fix `volsync-system/kopia` CrashLoopBackOff (readiness probe connection refused)
- [ ] P1: Fix `observability/blackbox-exporter-vpn` sandbox/network failure (`macvlan` link not found)
- [ ] P1: Investigate `network/unbound-dns` high restart count and `external-dns` back-off
- [ ] P1: Resolve missing `ClusterSecretStore onepassword` used by `network/homeops-ca-tls` push/external secret
- [ ] P2: Investigate KEDA scaler warnings for `zigbee` and `zwave` metrics retrieval

### App Recovery Focus

- [x] P0: home-assistant restored (Flux unsuspended and deployment healthy)
- [ ] P0: zigbee2mqtt not running (`zigbee` CrashLoopBackOff)
- [ ] P0: zigbee2mqtt coordinator endpoint unreachable from pod (`ETIMEDOUT 192.168.70.37:6638`)

Runbook references:
- [docs/REBUILD-RUNBOOK.md](docs/REBUILD-RUNBOOK.md)
- [docs/REMOTE-MEDIA-RUNBOOK.md](docs/REMOTE-MEDIA-RUNBOOK.md)

## Bootstrap/Infra Preconditions

- [ ] P1: Verify BGP neighbor health and LB route propagation before major maintenance
- [ ] P1: Verify AKV auth and ExternalSecrets sync before maintenance windows
- [ ] P1: Verify Cloudflare tunnel readiness before and after network changes

Reference:
- [kubernetes/apps/kube-system/cilium/README.md](kubernetes/apps/kube-system/cilium/README.md)

## Suggested Execution Order

1. Merge smtp-relay PR and confirm post-merge Flux state.
2. Run app health sweep and produce failures list.
3. Execute NAS02 migration in small batches (2-3 apps at a time).
4. Apply optimization changes after migration baseline stabilizes.
5. Flip Talos NFS version to 4.2 only after NAS migration is complete.
