# Operations Backlog

This file is the persistent task tracker for post-rebuild and reliability work.

## Current Priority

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
