# VolSync Backup Tiers

Backups use VolSync (Kopia repo on `nas02:/volume1/data/kopia`). Schedules are set
per app via `VOLSYNC_SCHEDULE` in each app's `ks.yaml`. Apps with backups **off** keep
their PVC but pause the `ReplicationSource` via a Flux patch.

> Why tiered + staggered: on rook 1.20.1, concurrent VolSync CSI snapshots can fence/
> corrupt RBD volumes. Staggering (no two snapshots overlap) and reducing frequency
> minimizes that risk until the root cause is fixed (see "Root cause" below).

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
| zigbee | `30 3 * * *` | default |

## Weekly (medium priority) — Sundays, staggered 05:00–06:20

| App | Schedule | Namespace |
| --- | --- | --- |
| atuin | `0 5 * * 0` | default |
| autobrr | `20 5 * * 0` | default |
| qui | `40 5 * * 0` | default |
| bazarr | `0 6 * * 0` | default |
| thelounge | `20 6 * * 0` | default |

## Off (paused) — no data yet, or redo-able

`omada-controller`, `netbox` (no data yet), `printguard` (until actively printing),
`frigate` (not configured), `lidarr` + `beets` (music-library rework pending),
`agregarr`, `recyclarr`, `dashbrr`, `tautulli`, `brrpolice` (redo-able supporting svcs).

`matter-server` has no VolSync configured at all (stateless until OTBR is set up).

## Root cause (open)

VolSync CSI snapshots on rook-ceph **1.20.1** intermittently fence RBD volumes
read-only (recoverable by a clean pod remount) and, in a few cases, corrupt the ext4
FS (needs manual `fsck`). Permanent fix is an infra decision (rook/ceph-csi version,
or `copyMethod: Snapshot → Clone`); under evaluation.
