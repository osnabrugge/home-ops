# nas01 — post-migration design

**Status:** proposed, 2026-09-17. Supersedes the flash/purchase sections of
[NAS01-STORAGE-ARCHITECTURE.md](NAS01-STORAGE-ARCHITECTURE.md). Every number below
was measured on the day, not estimated — commands are given so they can be re-run.

The four pools that exist today (`local`, `backups`, `nfs`, `smb`) were chosen to
maximise landing capacity for the migration. They are **not** a finished design and
this document does not treat them as one.

---

## 0. Two measurements that change the previous plan

### 0.1 nas01 has 24 free SAS bays, not zero

The earlier plan assumed every bay was populated, which is what forced the
"buy 5× 20 TB and absorb nas02 in one cut" conclusion. That assumption was wrong.

```
$ for e in /sys/class/enclosure/*/; do echo "$e $(cat $e/components)"; done
0:0:12:0  24 components   expander 0x50030480008035bf   12 occupied, 12 empty
0:0:13:0  12 components   expander 0x500304800083f1bf    0 occupied, 12 empty
16:0:0:0   8 components   SATA backplane                 4 occupied (SSDs)
7:0:0:0    6 components   SATA backplane                 1 occupied (boot SATADOM)
```

Both SAS expanders are live and enumerated by the kernel on `host0`. That is
**36 SAS bays with 12 in use**. Bays are not the scarce resource; money, power and
drive age are.

### 0.2 nas02's drives are older than most of nas01's

This is the single most important input to the purchase decision, and it confirms
Sean's instinct to rank by hours rather than capacity.

| Rank | Drives                           |           Hours |     Years | Currently in    |
| ---: | -------------------------------- | --------------: | --------: | --------------- |
|    1 | 2× ST4000VN000-1H4168 (sdc, sdg) |          61,7xx |       7.0 | nas01 `smb`     |
|    2 | 2× ST8000VN0022 (sdb, sde)       |          44,9xx |       5.1 | nas01 `nfs`     |
|    3 | 4× ST12000VN0008                 |      41,3–41,5k |       4.7 | **nas02**       |
|    4 | 4× ST20000NE000                  |          37,665 |       4.3 | **nas02**       |
|    5 | 4× ST4000NM017A (SAS)            |          24,47x |       2.8 | nas01 `smb`     |
|    6 | ST8000VN004 sdl / sdh            | 21,490 / 16,827 | 2.5 / 1.9 | nas01 `nfs`     |
|    7 | 2× ST10000VE0008                 |           5,698 |       0.7 | nas01 `backups` |

Every one of the 20 drives reports **0 reallocated sectors / 0 grown defects**.
Age is the only differentiator, so it is the only sane ranking.

**Consequence:** the 4× 20 TB drives the old plan was going to build the new vault
around are rank 4 — older than eight of the twelve drives already in nas01. The
irreplaceable-data pool therefore **must** be raidz2. At 20 TB a raidz1 resilver
runs for days and a second failure inside that window is a real probability, not a
tail risk.

### 0.3 The migration payload is smaller than 74 TiB

```
$ du -sh …                          $ df -h
/volume1/data                 51T   volume1  75T size, 67T used
/volume1/homes                16T   volume2  9.4T size, 5.3T used
/volume2/ActiveBackupforBusiness  40T   volume3  4.7T size, 1.8T used
/volume3/frigate             1.5T
/volume3/pve                 301G
```

`ActiveBackupforBusiness` reads 40 TiB by `du` but the volume holding it is only
5.3 TiB used — Synology ABB deduplicates internally. **It also cannot be migrated:**
the store is only readable by ActiveBackup running on DSM. Do not budget capacity
for it; re-establish those backups natively on nas01 and retire the Synology store.

| Share                              | Migrate? | Lands as         |
| ---------------------------------- | -------- | ---------------- |
| `/volume1/data` 51 TiB             | yes      | `media`          |
| `/volume1/homes` 16 TiB            | yes      | `vault`          |
| `/volume3/frigate` 1.5 TiB         | yes      | `nvr`            |
| `/volume3/pve` 301 GiB             | yes      | `vault`          |
| `/volume2/ActiveBackupforBusiness` | **no**   | re-seed natively |

**Real payload ≈ 69 TiB.**

> ⚠️ **Resolve this before spending money.** `data` measured 39.7 TiB on 2026-08-17
> and 51 TiB on 2026-09-17. If +11 TiB/month is genuine, no purchase survives contact
> with it and the fix is retention/churn, not disks. If the earlier figure was simply
> wrong, the sizing below stands. Re-measure before Phase 2.

---

## 1. (a) Pool → workload

| Pool                    | Topology                                        |       Usable | Workload                                               |
| ----------------------- | ----------------------------------------------- | -----------: | ------------------------------------------------------ |
| `apps` (today `local`)  | mirror 2× 512 GB SATA SSD                       |     0.45 TiB | Garage S3 for kopiur, docker/compose state, app config |
| `nvr` (today `backups`) | mirror 2× 10 TB Skyhawk AI                      |     9.09 TiB | **Frigate only**                                       |
| `vault`                 | raidz2 4× 20 TB (ex-nas02)                      |     36.4 TiB | homes, documents, photos, pve, backups-of-record       |
| `media`                 | raidz2 6× 8 TB **+** raidz2 4× 12 TB (ex-nas02) |     50.9 TiB | bulk media, cluster NFS exports                        |
|                         |                                                 | **96.8 TiB** | 69 TiB payload → **71 % full**                         |

**Garage / kopiur stays on `apps`.** The repo is 28.5 GiB against 457 GiB of SSD
mirror, and kopia's access pattern is many small objects with frequent fsync — the
worst possible fit for a 2-spindle mirror and the best fit for flash. (This is where
it already lives; it was briefly moved to `backups` on the strength of a pool _name_
and a _provisioned_ 758 GiB figure instead of the STORED 123 GiB. Both were wrong.)

**Frigate gets `nvr` (the Skyhawks) for three independent reasons:** those drives are
literally NVR-rated, they are the newest in the box at 0.7 years, and giving the 24/7
sequential write stream its own spindles stops it interleaving with media reads on
`media`. 1.5 TiB into 9.09 TiB leaves ample retention headroom.

**Retire the 6× 4 TB.** The two at 61.7 k hours come out first. The four SAS
ST4000NM017A at 24.5 k hours are healthy — keep them as cold spares rather than
burning four bays and ~28 W on 3.64 TiB each.

---

## 2. (b) SLOG — 2× Optane P1600X, mirrored, on `media`

A SLOG only ever accelerates **sync** writes. Ranking the four pools by sync
pressure, which is the only question that matters:

| Pool    | Sync profile                                                | SLOG value                                                                                             |
| ------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `nvr`   | Frigate writes large sequential segments asynchronously     | **none** — ZFS would not route them through it                                                         |
| `vault` | SMB; Windows/macOS clients write async unless `strict sync` | low, bursty                                                                                            |
| `apps`  | Garage/kopia fsync a lot — but the pool is already flash    | real, but small. Optane in front of SATA SSD is a ~5× QD1 win, not the ~1000× you get in front of rust |
| `media` | **NFS exports to Kubernetes, sync by default**              | **highest**                                                                                            |

`media` wins because it is the only workload in the machine that is simultaneously
sync-heavy, latency-sensitive, small-block **and** HDD-backed. Every `*arr` import,
rename, hardlink and `.nfsXXXX` unlink is a synchronous metadata write; on raidz2
spinning rust each costs a read-modify-write plus a ZIL commit (~10 ms) and they
serialise behind one another. That is precisely the stall a SLOG removes.

The P1600X is the right _device_ for the job because SLOG is a QD1, small-block,
write-only, high-endurance workload — 3D XPoint's strongest axis and consumer NAND's
weakest. Do not use a Crucial P3 here.

- **Mirror it.** Losing the SLOG during an unclean shutdown loses the in-flight sync
  transaction groups.
- **This one is reversible.** `zpool remove <log>` works online. If Postgres/CNPG or
  iSCSI ever lands on nas01, that pool outranks `media` and the SLOG should move.

---

## 3. (c) special / metadata vdevs

Two constraints to internalise **before** creating the pools, because neither can be
walked back:

1. **A special vdev is a pool-killer.** It holds all metadata; lose it, lose the pool.
2. **It can never be removed from a pool that contains a raidz vdev.** `zpool remove`
   only evacuates mirror/stripe vdevs, and only in pools with no raidz. On a raidz2
   pool this choice is permanent for the life of the pool.

And the mismatch that usually goes unnoticed: **a 2-way mirror special vdev on a
raidz2 pool silently downgrades the whole pool to single-failure tolerance.** The
special vdev must be **3-way** to match raidz2.

| Pool    | special vdev                                             |  Usable |
| ------- | -------------------------------------------------------- | ------: |
| `media` | **3-way mirror, 3× Crucial P3 1 TB**                     | 931 GiB |
| `vault` | **3-way mirror, 1× Crucial P3 1 TB + 2× Samsung 256 GB** | 232 GiB |
| `nvr`   | none                                                     |       — |
| `apps`  | none (already flash)                                     |       — |

That consumes all eight free NVMe (3+1 P3, 2 Samsung, 2 Optane).

`nvr` deliberately gets nothing: Frigate is a handful of very large sequential files,
its metadata volume is trivial, ARC covers it, and adding a special vdev to a 2-way
mirror pool would only add a failure domain.

Set **`special_small_blocks=0`** on both (metadata only, no small-file offload) until
actual usage is measured. You can raise it later; you cannot shrink the vdev.

Capacity sanity check — metadata runs ~0.3 % of pool data for large files, up to ~2 %
for many small ones:

- `media`, 51 TiB of large files → ~150–300 GiB. 931 GiB is ample.
- `vault`, 16 TiB of homes with many small files → ~160–330 GiB. **232 GiB is tight.**
  If it fills, ZFS spills metadata back to the pool — degraded, not fatal. If it passes
  ~70 %, replace the two 256 GB Samsungs with 1 TB drives; a _mirror_ can be grown by
  replace-and-expand, unlike the vdev itself.

**L2ARC stays ruled out.** 251 GB of ECC RAM means ARC already holds the hot set, and
every one of these devices earns more as a special vdev. Settled; not reopening it.

---

## 4. (d) Can this be migrated in place?

**Yes — with no single-copy moment at any point — and only because there are 24 free
SAS bays.**

But the existing pools cannot be _converted_. You cannot reshape raidz1 into raidz2,
cannot remove a raidz vdev, and cannot change vdev width. `nfs` and `smb` must be
**destroyed and rebuilt** — but that happens at the _end_, when they are already
empty, so no data is ever at risk.

The hard constraint is unchanged: nas02's `md2` spans all 8 spindles, so **not one
nas02 drive can be pulled until all ~69 TiB is off it.** nas02 is all-or-nothing.

Landing capacity available today, before buying anything:
`local 0.45 + backups 9.09 + nfs 21.0 + smb 17.3 = 47.85 TiB` against a 67 TiB
data+homes payload. **Short by ~20 TiB.**

### Ordering

**Phase 0 — free, no purchase, do it now**

1. Repoint Frigate from nas02 `/volume3/frigate` to nas01 `backups`/`nvr`. Frees
   1.5 TiB on nas02 and moves the NVR onto NVR-rated drives.
2. Repoint netboot-xyz to `nfs/netboot` (already created) — also closes the open
   "netboot NFS mount fails, exit 32" backlog item.
3. Move `/volume3/pve` (301 GiB).
4. Leave Garage/kopiur on `apps`. Already done.

**Phase 1 — measure, then decide**
Re-measure `data` growth (§0.3). If it really is +11 TiB/month, stop and fix
retention/churn before buying anything.

**Phase 2 — buy ~20 TiB of landing space** (§5) and build it into the free bays.
Nothing existing is disturbed.

**Phase 3 — evacuate nas02 over 10 GbE.** `data` → new pool, `homes` → the empty
`smb`/`nfs` pools temporarily.

**Phase 4 — pull nas02's 8 drives, install into free bays.** Build `vault` =
raidz2 4× 20 TB + its special vdev. Move `homes` + `pve` onto it.

**Phase 5 — destroy the now-empty `nfs` and `smb`.** Rebuild the 4× 8 TB into the
`media` raidz2 alongside the purchased drives; add the 4× 12 TB as `media`'s second
vdev. Retire the two 61.7 k-hour 4 TB drives.

At no point does a dataset exist in only one place.

---

## 5. (e) Buy / don't buy

The gap is ~20 TiB usable. All of these fit in the free bays, so this is decided on
risk and longevity, not on bay count.

### $/TB is the wrong metric

$45 for a 4 TB is $11.25/TB against $15.00/TB for a $120 8 TB, which makes the 4 TB
look like the buy. That comparison ignores how much life is left. Using ~45,000 h as
a working service life for this class:

| Option       | Price | Typical used hours | Remaining |      $ per TB per 1000 h |
| ------------ | ----: | -----------------: | --------: | -----------------------: |
| 4 TB @ $45   |   $45 |            ~50,000 |        ~0 | **effectively infinite** |
| 8 TB @ $120  |  $120 |            ~20,000 |   ~25,000 |                **$0.60** |
| 12 TB @ $140 |  $140 |            ~30,000 |   ~15,000 |                    $0.78 |

### Recommendation

- **Buy 6× 8 TB, ~$720.** Builds `media`'s first vdev as raidz2 6× 8 TB = 29.1 TiB,
  covering the 20 TiB gap with headroom, and matching the 4× 8 TB already on hand so
  the second vdev can be symmetric later.
- **Do not buy 4 TB at any price.** Used 4 TB stock today is overwhelmingly 2016–2018
  — the exact vintage of the two drives being retired at 61.7 k hours. It is buying
  the failure you are escaping. It also costs 8 W and a bay each for 3.64 TiB.
- **Do not buy 5× new 20 TB** (the previous plan). That pays new-drive prices to put
  new drives in the same failure domain as 4.3-year-old ones. If 20 TB is bought at
  all, buy to _pair_ with the ex-nas02 drives so no raidz2 vdev is uniformly aged.
- **Condition of sale: the seller must state SMART power-on hours.** The entire
  ranking above rests on that number. Walk away from any listing that omits it —
  reputable refurb-enterprise resellers publish it.

### Mixed ages within a vdev are a feature

`media`'s 8 TB vdev would mix 44.9 k, 21.5 k, 16.8 k and two fresh drives. That is
**good**: it de-correlates failures. A vdev of six identical drives from one batch
tends to fail together, which is the scenario raidz2 is least able to absorb.

---

## 6. What this design fixes about today's layout

| Today                     | Problem                                                                                                                                                 | Fixed by                                                               |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `smb` raidz1 6× 4 TB      | two 7.0-year drives striped with four 2.8-year drives, single parity — the highest-probability pool loss in the box, and it was earmarked for **homes** | homes moves to `vault` raidz2; the 61.7 k-hour drives are retired      |
| `nfs` raidz1 4× 8 TB      | single parity on 8 TB members; earmarked for 51 TiB of media                                                                                            | rebuilt into `media` raidz2                                            |
| `backups` mirror 2× 10 TB | labelled for backups, but a 2-spindle mirror is a poor target for kopia's many small objects                                                            | renamed `nvr`, given Frigate, which is what those drives are built for |
| all four pools            | no SLOG, no special vdev, 8 NVMe sitting idle                                                                                                           | §2, §3                                                                 |
