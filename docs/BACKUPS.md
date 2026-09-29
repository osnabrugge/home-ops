# Backups (kopiur)

Every PVC backup in this cluster is taken by **kopiur**, which drives Kopia against a
single S3 repository. There is no tiering — every app uses the same repository, the
same hourly cadence and the same retention.

## Repository

One `ClusterRepository`, **`nas01`**, defined in
`kubernetes/apps/kopiur-system/kopiur/repository/clusterrepository.yaml`:

|                 |                                                                              |
| --------------- | ---------------------------------------------------------------------------- |
| Backend         | S3 (Garage on nas01), `192.168.42.45:3900`, TLS disabled                     |
| Bucket / prefix | `default-bucket` / `home-ops/`                                               |
| Credentials     | `kopiur-repository-secret` in `kopiur-system` (from Azure Key Vault via ESO) |
| Maintenance     | quick hourly (`0 * * * *`, 10m jitter), full daily 03:00 (1h jitter)         |

## Opting an app in

Add the `components/kopiur/backup` component to the app's `ks.yaml`. Add
`components/kopiur/secret` **once per namespace** — movers run in the app's namespace
and need the repository credentials there.

The schedule is **not** configurable per app: `components/kopiur/policy/snapshotschedule.yaml`
hardcodes `cron: H * * * *`. The `H` is a per-app hash, so the 29 schedules spread
themselves across the hour rather than all firing at :00.

`postBuild.substitute` knobs, all optional:

| Variable                      | Default              | Purpose                                                           |
| ----------------------------- | -------------------- | ----------------------------------------------------------------- |
| `KOPIUR_PVC`                  | `${APP}`             | Source PVC when it isn't named after the app                      |
| `KOPIUR_CAPACITY`             | `5Gi`                | Mover cache size                                                  |
| `KOPIUR_STORAGECLASS`         | `ceph-block`         | Storage class for the staged clone                                |
| `KOPIUR_ACCESSMODES`          | `ReadWriteOnce`      | Access mode for the staged clone                                  |
| `KOPIUR_SNAPSHOTCLASS`        | `csi-ceph-blockpool` | VolumeSnapshotClass used for staging                              |
| `KOPIUR_PUID` / `KOPIUR_PGID` | `1000`               | Mover UID/GID — must be able to READ the source                   |
| `KOPIUR_IGNORE_FILE_ERRORS`   | `false`              | Complete with errors instead of failing when a file is unreadable |

## Retention

Set once in `components/kopiur/policy/snapshotpolicy.yaml` and applied to every app:
`keepLatest: 3`, `keepHourly: 24`, `keepDaily: 7`, `keepWeekly: 4`.

Failed runs are retained separately by `failedJobsHistoryLimit: 10` per schedule, so up
to 10 `Failed` Snapshot objects per app is **expected** and is not a leak. Do not bulk
delete them; they are the forensic trail.

## Mover permissions

The mover runs as uid/gid 1000 by default and must be able to read the source data.

- If some files are unreadable but the rest matter, set `KOPIUR_IGNORE_FILE_ERRORS: "true"`.
- If the data is root-owned `0600`, that is not enough — the run would "succeed" while
  silently skipping those files. Set `KOPIUR_PUID`/`KOPIUR_PGID` to `0` **and** annotate
  the namespace `kopiur.home-operations.com/privileged-movers: "true"`, which kopiur
  requires as an explicit opt-in because it permits root movers for the whole namespace.
  `printing` is currently the only namespace that does this (printguard's `state.json`).
- Changing the mover UID orphans the existing cache PVC, which stays owned by the old
  UID. The mover drops `CAP_DAC_OVERRIDE`, so even root then gets permission denied on
  `/var/cache/kopia`. Fix by re-owning the cache, or delete it — it is regenerable.

## Restore (manual)

The kopiur `Restore` populator was removed from the shared component: a perpetually
`Pending` Restore blocks Flux `wait: true` health checks on apps whose PVC already
exists. To restore, create a `Restore` CR referencing the app's `SnapshotPolicy` and a
target PVC, then either point the app PVC's `dataSourceRef` at it (fresh provision) or
copy the restored data into the live PVC.

## History

- **2026-07-06** — migrated from VolSync to kopiur. VolSync's CSI `Snapshot` copyMethod
  on rook-ceph **1.20.1** intermittently fenced RBD volumes read-only (recoverable by a
  clean pod remount) and occasionally corrupted the ext4 filesystem, needing a manual
  `fsck`.
- **2026-09** — repository moved from the old NFS-backed Kopia repo on `nas02` to
  **Garage S3 on nas01**. The pre-migration Snapshot records still resolve to a
  `ClusterRepository nas02` that no longer exists; they are annotated
  `kopiur.home-operations.com/skip-snapshot-cleanup: "true"` so retention can release
  them without needing the dead repository. The old repo data is retained on `nas02`
  until manually reclaimed.
