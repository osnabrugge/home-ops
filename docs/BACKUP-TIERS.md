# Backup Tiers (kopiur)

Backups use **kopiur** (Kopia repo on `nas02:/volume1/data/kopiur`, ClusterRepository
`nas`). Each app opts in with the `components/kopiur/backup` component and sets
`KOPIUR_SCHEDULE` (active) or `KOPIUR_SUSPEND: "true"` (off) in its `ks.yaml`. Credentials
come from the `components/kopiur/secret` component (added once per namespace — kopiur
movers run in the app namespace and load `kopiur-nas-secret` via `envFrom`).

> **copyMethod: Clone** (component default) is used instead of `Snapshot` to avoid the
> rook-1.20.1 CSI-VolumeSnapshot RBD read-only fencing cascade. The staggered schedules
> below are kept as defence-in-depth so no two backups overlap.

## Daily (high priority) — staggered 01:00–03:30

| App | Schedule | Namespace |
| --- | --- | --- |
| prowlarr | `0 1 * * *` | default |
| sonarr | `15 1 * * *` | default |
| radarr | `30 1 * * *` | default |
| sabnzbd | `45 1 * * *` | default |
| home-assistant | `0 2 * * *` | default |
| seerr | `15 2 * * *` | default |
| qbittorrent | `30 2 * * *` | default |
| lldap | `45 2 * * *` | auth |
| plex | `0 3 * * *` | default |
| spoolman | `15 3 * * *` | printing |
| dispatcharr | `0 3 * * *` | default |
| zigbee | `30 3 * * *` | default |

## Weekly (medium priority) — Sundays, staggered 05:00–06:20

| App | Schedule | Namespace |
| --- | --- | --- |
| atuin | `0 5 * * 0` | default |
| autobrr | `20 5 * * 0` | default |
| qui | `40 5 * * 0` | default |
| bazarr | `0 6 * * 0` | default |
| thelounge | `20 6 * * 0` | default |

## Off (`KOPIUR_SUSPEND: "true"`) — no data yet, or redo-able

`omada-controller`, `netbox` (no data yet), `printguard` (until actively printing),
`frigate` (not configured), `lidarr` + `beets` (music-library rework pending),
`agregarr`, `recyclarr`, `dashbrr`, `tautulli`, `brrpolice` (redo-able supporting svcs).
These keep their PVC (adopted in place, held in the Flux inventory by the component's
plain PVC claim) but run no backups.

`matter-server` has no kopiur backup configured at all (stateless until OTBR is set up).

## Restore (manual)

The kopiur `Restore` populator was removed from the shared component because a
perpetually-`Pending` Restore blocks Flux `wait: true` health checks on apps with an
already-existing (adopted) PVC. To restore, create a `Restore` CR referencing the app's
`SnapshotPolicy` and a target PVC, then point the app PVC's `dataSourceRef` at it (fresh
provision) or copy the restored data into the live PVC.

## History

Migrated from VolSync (Kopia repo `nas02:/volume1/data/kopia`) to kopiur on 2026-07-06.
The old VolSync repo data is retained on `nas02` until manually reclaimed. VolSync CSI
`Snapshot` copyMethod on rook-ceph **1.20.1** intermittently fenced RBD volumes read-only
(recoverable by a clean pod remount) and occasionally corrupted the ext4 FS (manual
`fsck`); kopiur's `copyMethod: Clone` avoids that failure mode.
