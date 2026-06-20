# Ceph 3 → 6 OSD Migration Runbook

> Convert the 3 control-plane Samsung 970 EVO Plus 1TB NVMe from OpenEBS
> `local-hostpath` to **raw Ceph OSDs** (osd.3/4/5), going from 3 → 6 OSDs.
> Relieves OSD/op contention (the recurring MDS slow-IO + RBD-fence pain) and
> gives real self-healing (6 hosts > replica-3).
>
> Status: PLAN — execute staged, gated on each destructive step. Do NOT run end-to-end.

## Why / what changes
- Each node has ONE big disk (Samsung 970 1TB) + a 256 GB DOGFISH boot SSD.
- Workers k8s04/05/06: Samsung = raw Ceph OSD (osd.0/1/2) already.
- Control planes k8s01/02/03: Samsung = Talos `UserVolumeConfig local-hostpath`
  (xfs, mounted `/var/mnt/local-hostpath`) backing OpenEBS `openebs-hostpath`.
- Rook CephCluster: `useAllNodes: true` + `deviceFilter: nvme-Samsung_SSD_970_EVO_Plus_1TB_*`
  → **any raw matching disk auto-becomes an OSD.** So freeing a CP Samsung is all
  Rook needs; no Rook config change required.

## What lives on `openebs-hostpath` today (must be handled)
- **CNPG `postgres16`** (`postgres16-11/12/13`, 20Gi each). Databases: `authelia`
  (LIVE — 2FA/WebAuthn/OIDC-consent data), `netbox`/`diode`/`hydra` (empty/undeployed).
- **~27 VolSync caches** (`volsync-src-*-cache`, 5Gi each) — EPHEMERAL, recreated each backup.

## Decisions (confirmed with user 2026-06-20)
- **Authelia: rebuild fresh, NO pg_dump.** Only validated grafana+netbox OIDC, proxmox
  untested. Acceptable to re-enroll 2FA + re-validate OIDC clients. Authelia *config*
  (clients/LDAP/policies) is in git; only DB data resets.
- netbox/diode/hydra: empty → tear down freely.
- netbox-operator DR caveat: N/A (deploying fresh/empty; no operator-managed object IDs to restore).
- Postgres moves to `ceph-block` (networked) — accepted DB-latency tradeoff for a homelab.

## Preconditions (verify before starting)
- [ ] Ceph `HEALTH_OK`, all 3 OSDs up/in, no recovery in progress.
- [ ] etcd healthy on all 3 control planes (`talosctl -n <cp> etcd status`).
- [ ] Recent etcd snapshot taken (`talosctl -n k8s01 etcd snapshot db.snapshot`).
- [ ] A maintenance window — Authelia (and thus OIDC/forward-auth logins) will be DOWN
      while Postgres is rebuilt.
- [ ] Confirm OpenEBS basePath: when the Samsung UserVolume is removed, `/var/mnt/local-hostpath`
      falls back to the boot/EPHEMERAL fs (DOGFISH, 254 GB) — caches still fit. VERIFY the
      `openebs-hostpath` basePath in the openebs HelmRelease before wiping.

## Phase 1 — quiesce Postgres consumers (reversible)
1. Suspend Flux so it doesn't fight the teardown:
   `flux suspend kustomization netbox netbox-diode authelia cloudnative-pg --namespace <each>`
   (use the actual ks namespaces; flux suspend hr where applicable).
2. Scale down consumers: authelia, netbox, netbox-diode (Deployments → 0).
3. (Optional safety) `pg_dump` everything to NFS anyway — costs nothing:
   `kubectl -n database exec postgres16-1 -c postgres -- pg_dumpall > /tmp/pg_all.sql` and copy off-cluster.

## Phase 2 — tear down Postgres
4. Delete the CNPG cluster + its PVCs:
   `kubectl -n database delete cluster.postgresql.cnpg.io postgres16`
   then delete the released `postgres16-*` PVCs (openebs-hostpath).
   This frees the OpenEBS usage but NOT the Talos Samsung volume yet.

## Phase 3 — free the CP Samsungs → OSDs (ONE node at a time!)
> Repeat per node: k8s01, then k8s02, then k8s03. **Wait for Ceph HEALTH_OK +
> rebalance complete between each.** Never do two control planes at once (etcd quorum + Ceph).

For each control-plane node `<cp>`:
5. Drain non-critical workloads off it: `kubectl drain <cp> --ignore-daemonsets --delete-emptydir-data` (keep etcd/control-plane static pods — they stay).
6. Remove the `UserVolumeConfig local-hostpath` from Talos config for control planes
   (edit `talos/machineconfig.yaml.j2` — scope it worker-excluded or remove entirely since
   workers don't use it), re-render, and `talosctl apply-config` to `<cp>`.
7. Wipe the Samsung so it's raw for Rook. VERIFY exact Talos 1.13 command at execution —
   candidates: `talosctl -n <cp> wipe disk nvme0n1` (if supported) OR a targeted
   `talosctl -n <cp> reset --system-labels-to-wipe u-local-hostpath --graceful=true`
   (note: mod.just's reset also wipes STATE/EPHEMERAL — do NOT use that full form here).
8. Uncordon: `kubectl uncordon <cp>`.
9. Rook auto-detects the raw Samsung and creates the new OSD. Watch:
   `kubectl -n rook-ceph get pods -l app=rook-ceph-osd -w` and the toolbox `ceph -s`.
10. **GATE:** wait for `ceph -s` → HEALTH_OK, new osd `up/in`, backfill done. Then next node.

End state: 6 OSDs across 6 hosts (osd.0-5), ~5.4 TiB raw, self-healing.

## Phase 4 — redeploy Postgres on Ceph + restore consumers
11. Repoint CNPG `postgres16` storageClass `openebs-hostpath` → `ceph-block` (in its manifest),
    resume Flux, let CNPG recreate the cluster on Ceph.
12. Recreate the `authelia`/`netbox`/`diode`/`hydra` databases (CNPG `Database` CRs already
    declare diode/hydra; authelia/netbox created by their bootstrap/initdb).
13. Resume authelia → it recreates its schema on an empty DB. **Re-enroll your 2FA + re-test OIDC.**
14. Resume netbox / netbox-diode.

## Phase 5 — verify
- [ ] `ceph osd tree` shows 6 osds up/in, `ceph -s` HEALTH_OK.
- [ ] Postgres pods Running on ceph-block PVCs.
- [ ] Authelia login + 2FA works; Grafana/NetBox OIDC works.
- [ ] No VolSync cache breakage (caches re-provision on boot disk).

## Rollback notes
- Before Phase 3 (no disk wiped yet): everything is reversible — resume Flux, redeploy Postgres on openebs-hostpath.
- After a Samsung is wiped: that node is committed to OSD; to revert you'd re-add the UserVolume + rebuild local storage. Hence one-node-at-a-time with health gates.
- etcd snapshot from preconditions covers control-plane recovery.

## Open items to verify at execution time
- Exact Talos 1.13.4 disk-wipe command for the single Samsung (don't full-reset the node).
- `openebs-hostpath` basePath fallback behavior once the Samsung mount is gone.
- CNPG `Database` CR / initdb for the `authelia` and `netbox` databases on the rebuilt cluster.
