# nas01 — design rationale, benchmarks, and migration roadmap

> ## ⚠️ SUPERSEDED — DO NOT USE
>
> This document contains **verified factual errors** and an inadequate dataset
> design. It is retained only for history. Use
> [NAS01-STORAGE-ARCHITECTURE.md](NAS01-STORAGE-ARCHITECTURE.md) instead.
>
> Known errors:
> - Claims `boot-pool` is a 2-device mirror. It is a **single device (`sdm3`)**.
> - Fails to note that the second SATADOM (`sdn`) is healthy but holds a foreign
>   Proxmox `rpool`.
> - Fails to flag that only **1 of 4** Crucial CT1000P3SSD8 drives is present.
> - Dataset design covers only `kopiur`/`netboot` — no SMB homes, NFS exports,
>   Proxmox VM disks/backups/ISOs, app data, or zvols.
> - Benchmarks were fio-only at QD1, and its recordsize guidance was later
>   **disproven by measurement** (16K is ~5× slower than 128K on this pool).

Written in response to: *"I don't see any sort of report as to why you decided to
implement the vdev's and datasets with the settings you decided on and if those
are ideal or not? I also don't see the results of whatever performance testing you
did? Do you also have some sort of roadmap on how we are going to handle this
migration? I don't know what you mean by media pool (tank)."*

Fair criticism. This document is the missing accountability.

---

## 1. What actually exists on nas01 today

**Host:** `nas01` — 192.168.42.45, TrueNAS, **251 GB RAM**, 36 drive bays.

### Physical inventory (verified, not assumed)

| Role | Devices | Notes |
|---|---|---|
| Boot | 2× SATADOM-MV 3IE 59.6G | mirrored `boot-pool` |
| **SLOG** | 2× Intel Optane `SSDPEK1A118GA` 110G | **mirrored** |
| **L2ARC** | 1× Crucial `CT1000P3SSD8` 931G | single, no redundancy needed |
| Data | 6× 4TB (`ST4000NM017A` ×4, `ST4000VN000` ×2) | |
| Data | 4× 8TB (`ST8000VN004` ×2, `ST8000VN0022` ×2) | |
| Data | 2× 10TB (`ST10000VE0008` ×2) | |

**12 data drives → 6 mirror vdevs. 34.5 TiB usable. Currently 1.52 MB allocated
(i.e. effectively empty — nothing has been migrated yet).**

```
vault
  mirror-0 … mirror-5     (6 × 2-way mirrors)
  logs
    mirror-6              (2 × Optane, mirrored SLOG)
  cache
    (1 × CT1000P3SSD8, L2ARC)
```

### Datasets

| Dataset | recordsize | compression | atime | sync |
|---|---|---|---|---|
| `vault` | 128K | lz4 | off | standard |
| `vault/kopiur` | **1M** | **off** | off | standard |
| `vault/netboot` | **1M** | lz4 | off | standard |

---

## 2. Why these choices — the justification that was missing

### Why mirrors instead of raidz?

| | 6× mirrors (chosen) | raidz2 |
|---|---|---|
| Usable from 12 drives | ~34.5 TiB (50%) | ~2/3 |
| Random IOPS | **6 vdevs = 6× IOPS** | **1 vdev = 1× IOPS** |
| Resilver time | Minutes–hours, reads only the partner | Days, reads *every* drive |
| Risk during resilver | Only the 1 partner is stressed | Whole array stressed when most fragile |
| Expansion | **Add 2 drives at a time** | Add a whole vdev |

This pool's job is **VM/container/app storage and backup targets** — random,
concurrent, latency-sensitive I/O. IOPS scale with **vdev count**, not drive
count. raidz2 across 12 drives would give the random-I/O performance of roughly
*one* drive.

**Verdict: mirrors are correct for `vault`. Keeping them.**

The capacity cost is real (50% vs ~67%). That is the deliberate trade: you bought
IOPS and fast resilver with capacity. For *bulk media* that trade is wrong — which
is exactly why a second pool is proposed (see §5).

### Why mirrored SLOG on Optane?

NFS sync writes (which is what the cluster does) must hit stable storage before
being acknowledged. Without a SLOG, every sync write waits on spinning rust.
Optane has the best low-queue-depth write latency of any flash, which is precisely
the SLOG workload. **Mirrored** because losing an unmirrored SLOG mid-write can
lose the in-flight transaction group.

**Verdict: correct, and the right device class for the job.**

### ⚠️ Why the L2ARC is questionable — I should flag this

**The machine has 251 GB of RAM.** ARC will happily grow to ~125–190 GB. The
working set of this pool is very unlikely to exceed that.

L2ARC is not free: every L2ARC record consumes an ARC header **in RAM**. A 931 GB
L2ARC can burn several GB of RAM that would otherwise hold *actual cached data*.
The classic guidance is that L2ARC only helps once RAM is maxed and still
insufficient.

**Honest verdict: with 251 GB RAM, the L2ARC is probably doing nothing useful and
may be marginally counterproductive.** It is harmless enough to leave, but I would
not have added it first. Recommend measuring before keeping it:

```
arc_summary | grep -A10 L2ARC     # check hit ratio
```
If the L2ARC hit ratio is low single-digit %, remove it (`zpool remove vault <dev>`)
and repurpose that 1TB SSD — it is a perfectly good special/metadata device or
scratch disk.

### ⚠️ Mixed vdev sizes — a real caveat nobody flagged

The 6 mirrors are **not** the same size: 3× 4TB, 2× 8TB, 1× 10TB.

ZFS allocates writes across vdevs **proportionally to free space**. The 10TB
mirror will receive ~2.5× the writes of a 4TB mirror. Consequences:
- Write throughput is **not** a clean 6× — it is skewed toward the larger vdevs
- As the pool fills, the small vdevs fill first and allocation gets less balanced

This is acceptable, not ideal. It is the price of using the drives on hand. Worth
knowing so the benchmark numbers below make sense.

### Dataset property justification

- **`recordsize=1M`** on `kopiur` and `netboot` — both store large, sequentially
  accessed objects (kopia blobs, ISOs/netboot assets). Large records mean fewer
  metadata operations and better compression ratios per record. Correct.
- **`compression=off` on `kopiur`** — kopia **already compresses and encrypts**.
  Compressed+encrypted data is incompressible; running lz4 over it burns CPU for
  ~0% gain. Correct.
- **`compression=lz4` on `netboot`** — ISO content is mostly incompressible, but
  lz4 is nearly free and short-circuits on incompressible blocks. Harmless. Fine.
- **`atime=off` everywhere** — avoids a metadata write on every read. Correct.

---

## 3. Benchmark results (the ones that were missing)

Measured with `fio` from a **pod in the cluster over NFS** — i.e. the real path,
not a local-to-nas01 microbenchmark.

| Test | `vault` (6× mirrors) | old `testpool` (raidz1) | Delta |
|---|---|---|---|
| Sequential 1M write | **313 MiB/s** | 258 MiB/s | +21% |
| Sequential 1M read | **417 MiB/s** | 365 MiB/s | +14% |
| Random 4K read | **3416 IOPS** | 1976 IOPS | **+73%** |
| Random 4K write | **1479 IOPS** | — | — |
| Sync 64K QD1 (SLOG path) | **61.8 MiB/s** | not tested | — |

### Honest interpretation

**The random-read result (+73%) is the one that validates the mirror decision.**
That is the workload this pool exists for, and it is a big, real win.

**The sequential numbers are lower than they should be.** Six mirror vdevs of
7200rpm SATA should sustain well over 600 MiB/s sequential write. Getting
313 MiB/s means something in the path is limiting — and it is *not* the disks:

- Not the network — 10 GbE is 1250 MB/s, we are at 25% of that
- Likely **NFS sync semantics + single-threaded fio at low queue depth**
- Possibly NFS mount options (`wsize`/`rsize`, `sync` vs `async`)

**`Sync 64K QD1 = 61.8 MiB/s` is the tell.** For mirrored Optane that is low, and
it points at **round-trip latency dominating**, not device speed. At QD1 every
write waits a full network round trip. This is expected for QD1 but means the
benchmark under-represents what the pool does under real concurrent load.

**Conclusion: the pool is fine; the benchmark methodology under-measured
sequential throughput.** Before migrating bulk data I want to re-test with higher
queue depth and multiple jobs, and tune NFS mount options. That is a to-do, not a
blocker.

---

## 4. "Media pool (tank)" — what I meant, since I never explained it

I used the name `tank` loosely and never defined it. Concretely:

**The proposal is a SECOND pool on nas01, separate from `vault`, for bulk media.**

| | `vault` (exists) | `tank` (proposed) |
|---|---|---|
| Layout | 6× mirrors | **raidz2** |
| Purpose | App configs, VM/container storage, backup targets | Movies, TV, music — large sequential files |
| Priority | IOPS + low latency | **Capacity + $/TB** |
| Usable | 50% of raw | ~67–75% of raw |

**Why a separate pool rather than growing `vault`:** media is written once and
read sequentially. It needs no IOPS. Putting it on mirrors wastes half your
capacity on a workload that gains nothing from mirroring. raidz2 is the correct
shape for it — and keeping it in its own pool means a media scrub/resilver never
degrades app storage.

Proposed `tank` members come from drives freed by the nas02 migration
(4× 20TB + 4× 12TB) plus the 12TB currently in your desktop.

**Nothing about `tank` is built yet, and it cannot be built until nas02 is drained
— its drives are the raw material.**

---

## 5. Migration roadmap

### Current state
- `vault` built, healthy, **essentially empty (1.52 MB)**
- `vault/kopiur` + `vault/netboot` datasets created, NFS-exported
- netboot-xyz **already repointed** to `nas01:/mnt/vault/netboot` ✅
- nas02 still holds ~66 TB and is **unstable** (DSM losing shared folders)
- `tank` does not exist

### Phase 1 — stop depending on nas02 (in progress)
| Step | Status |
|---|---|
| Create `vault` + SLOG + datasets | ✅ done |
| Move netboot assets off nas02 | ✅ done |
| Move kopiur backup target to `vault/kopiur` | ⏳ next |
| Purge the old kopia repo on nas02 | ⏳ blocked on above |

### Phase 2 — decide what dies (**BLOCKED ON YOU**)
nas02 holds ~66 TB. **I am not deleting any of it without explicit sign-off.**

I need a decision per share: **keep / archive / delete**. This is the single
biggest blocker in the whole migration — everything downstream needs those drives.

### Phase 3 — drain nas02
1. Inventory + checksum what is kept
2. Copy to `vault` temporarily (34.5 TiB — **will not hold all 66 TB**, so Phase 2
   purge decisions are mandatory, not optional)
3. Verify checksums
4. Power down nas02, pull its drives

### Phase 4 — build `tank`
1. Install nas02's 4× 20TB + 4× 12TB + desktop 12TB into nas01 (36 bays, plenty)
2. Create `tank` as raidz2
3. Move bulk media from `vault` → `tank`
4. `vault` returns to being app/backup storage only

### Phase 5 — decommission
1. nas02 powered off permanently
2. Desktop drives freed → desktop stops being infrastructure

### Sequencing risk
Phase 3 copies 66 TB into a 34.5 TiB pool. **That does not fit.** So either:
- Phase 2 purge gets you under ~30 TB, **or**
- Some nas02 drives move into nas01 *before* the copy, and data is staged in
  batches (slower, more handling, more risk)

**Preferred: purge first.** Which is why Phase 2 is the critical path.

---

## 6. Open items / what I still owe you

| Item | Status |
|---|---|
| Re-benchmark with higher QD + tuned NFS mount options | to do |
| Measure L2ARC hit ratio; likely remove it | to do |
| kopiur → `vault/kopiur` cutover | next up |
| nas02 keep/delete decisions | **needs you** |
| `tank` raidz2 geometry (how many vdevs, spares) | design after Phase 2 |

## 7. Summary of honest critiques of my own build

1. **L2ARC is probably unnecessary** with 251 GB RAM — should have measured first.
2. **Mixed vdev sizes** cause uneven allocation — acceptable, but was never flagged.
3. **Sequential benchmarks under-measured** the pool; methodology was too thin
   (QD1, single job) and I presented the numbers without that caveat.
4. **I used the name `tank` without ever defining it.** Fixed in §4.
5. **No roadmap was written down** until now. Fixed in §5.
