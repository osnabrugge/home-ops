# nas01 — Design Options, Measured

> Written 2026-08-05. Every performance claim here is measured on this machine, with
> the method stated. Where a measurement contradicts an earlier document, both numbers
> are shown. Where something is **not** proven, it says so.

## 1. Hardware actually present (verified)

| Qty | Device | Notes |
|---|---|---|
| 12 | HDD: 6×4TB, 4×8TB, 2×10TB (Seagate, SAS/SATA behind LSI SAS2308) | current `vault` data |
| 4 | Crucial CT1000P3SSD8 931G NVMe | **all 4 now present** — bifurcation fixed |
| 2 | Intel Optane P1600X 118G | SLOG mirror |
| 1 | SATADOM-MV 3IE 59.6G (`sdl`) | `boot-pool` — **single device, NO redundancy** |
| 2 | USB 0-byte phantoms (`sdm` BR25, `sdo` **PiKVM** `CAFEBABE`) | **not real disks** |
| 72 | CPU threads | |
| 251 GB | RAM (≈240 GB free) | drives every ARC conclusion below |

Chassis: **36 front bays (12 used) + 24 rear bays** (rear needs printed trays).

Available soon: 4× 12TB Ironwolf (in nas02, free after migration), 1× 12TB spare on desk,
4× 20TB Ironwolf (location to confirm).

---

## 2. Benchmark methodology — and why the first two attempts were wrong

This matters, because three runs gave three different answers.

| Run | Setting | What it actually measured | Verdict |
|---|---|---|---|
| 1 | `primarycache=none`, buffered | disks, but L2ARC was removed between runs | **confounded** |
| 2 | `primarycache=all`, buffered | **RAM** — 544k IOPS, 8.8 GB/s | **invalid** |
| 3 | `primarycache=metadata`, `--direct=1`, `--refill_buffers` | disks, metadata cached | **valid** |

Run 2's 4 GiB working set fit entirely inside 251 GB of ARC. Run 3 matches the
methodology of the original `NAS01-STORAGE-ARCHITECTURE.md` §5, so the numbers are
directly comparable to it.

**Rule for future benchmarking on this box: `primarycache=metadata` + `--direct=1` +
`--refill_buffers`, working set ≥ 8 GiB.** Anything else measures RAM.

---

## 3. Measured baseline (run 3, current pool: 6×2-way mirror + special + SLOG)

| recordsize | rand 16K read | rand 16K write | seq 1M read | seq 1M write |
|---|---|---|---|---|
| 16K | 533 IOPS / 8.3 MB/s | **6,670 IOPS / 104.2 MB/s** | 367.0 MB/s | 317.5 MB/s |
| 128K | **985 IOPS / 15.4 MB/s** | 3,087 IOPS / 48.2 MB/s | **461.9 MB/s** | 276.7 MB/s |
| 1M | 313 IOPS / 4.9 MB/s | 634 IOPS / 9.9 MB/s | 443.8 MB/s | **375.1 MB/s** |

Buffered sequential write (realistic for NFS/SMB, run 1+2 agreeing): **~680–694 MB/s**
at 16K/128K, **~610 MB/s** at 1M.

### 3.1 Corrections to the previous document

| §5.4 claim | Measured | Status |
|---|---|---|
| 128K is **5.0×** faster than 16K for small random **read** | **1.9×** (985 vs 533 IOPS) | direction ✅, magnitude ❌ |
| 128K is **4.8×** faster than 16K for small random **write** | **16K is 2.2× faster** (104.2 vs 48.2 MB/s) | **refuted** |
| 1M is **2.19×** faster than 16K for sequential write | **1.18×** direct; ~flat buffered | **not reproduced** |
| SLOG gives **5.2 µs** sync p99 | **27.1 ms** measured `sync=always` | **refuted** (5.2 µs is faster than the Optane itself) |

The §5.4 16K random-read figure (8.9 MB/s) reproduced almost exactly (8.3 MB/s), so
both runs are sound — the divergence is in the write path, where a COW filesystem
turning random writes into sequential transactions makes 4.0 MB/s implausible.

### 3.2 What is NOT proven

- **The SLOG's value.** Measuring `sync=always` (126.6 MB/s) vs `sync=disabled`
  (628.3 MB/s) shows the *cost of sync* (5×), not the *benefit of the SLOG*. Proving
  the latter needs the pool without a log vdev, which cannot be done live.
- **The special vdev's real benefit.** fio measures blocks, not metadata operations.
  Directory traversal / `stat` / large-folder listing is where it pays, and none of
  these tests exercise that. Random *data* reads are unchanged because data still
  lives on spinning disks.
- **NFS/SMB protocol throughput.** Needs shares, which need a chosen layout.

---

## 4. Design options

Assume 12 existing HDD + 4 NVMe + 2 Optane. Usable capacity uses the **80 % ZFS
ceiling**, past which performance degrades.

### Option A — Status quo: 6× 2-way mirror (CURRENT)

```
data:    6 × mirror(2)        34.5 TiB raw → ~27.4 TiB usable
special: 2 × mirror(2) NVMe   ~1.86 TiB
log:     mirror(2) Optane
```

| | |
|---|---|
| **Usable** | ~27.4 TiB |
| **Redundancy** | 1 disk per vdev; survives 6 failures if perfectly distributed, **1 if unlucky** |
| **Rebuild** | Fast — mirror resilver reads one disk, hours not days |
| **Random IOPS** | Best of all options — 6 independent vdevs |
| **Risk** | Losing both halves of one mirror loses the pool |
| **Verdict** | Best performance, worst capacity efficiency (50 %) |

### Option B — 2× RAIDZ2 (6-wide)

```
data:    2 × raidz2(6)        ~4 disks' parity → ~21 TiB usable at 80%
```

| | |
|---|---|
| **Usable** | Slightly *less* than A with mixed disk sizes (RAIDZ pads to smallest) |
| **Redundancy** | **Any 2 disks per vdev** — far safer than A |
| **Rebuild** | Slow; reads all surviving disks. Days on 10 TB members |
| **Random IOPS** | ~2 vdevs' worth — **3× worse than A** |
| **Verdict** | ⚠️ **Not recommended with your mixed 4/8/10 TB disks** — RAIDZ pads every member to the smallest, wasting the 8 and 10 TB drives |

### Option C — 6× 2-way mirror + special, disks rebalanced by size (RECOMMENDED NOW)

Same as A, but pair disks **like-with-like** (4+4, 8+8, 10+10) — which the current pool
already does — and add the 12 TB drives as new mirror vdevs after migration.

| | |
|---|---|
| **Usable** | ~27.4 TiB now → **~48 TiB** after adding 5× 12 TB as 2 more mirrors |
| **Verdict** | Incremental, no rebuild, no downtime. Capacity grows by adding vdevs |

### Option D — Mirrors now, RAIDZ2 later on the 20 TB drives

Keep `vault` as mirrors for hot data; build a **second pool** (`archive`) from
4× 20 TB in RAIDZ2 for cold bulk (media, backups).

| | |
|---|---|
| **Usable** | vault ~27 TiB (fast) + archive ~32 TiB (safe/cheap) |
| **Redundancy** | archive survives any 2 of 4 |
| **Verdict** | ⭐ **Best long-term fit.** Matches storage class to workload: mirrors for random I/O, RAIDZ2 for streaming bulk. Also isolates blast radius |

### Option E — Single big RAIDZ3

Not recommended: one vdev = worst random I/O, and rebuild time on 20 TB members is
measured in days during which you are exposed.

### 4.1 Special vdev sizing

| Layout | Usable | Fault tolerance | Note |
|---|---|---|---|
| **2 × mirror(2)** ← current | ~1.86 TiB | 1 per mirror | matches data-vdev redundancy |
| 1 × mirror(3) + 1 spare | 931 GiB | 2 | safer than the data vdevs — moves the weak link without removing it |
| 1 × mirror(4) | 931 GiB | 3 | over-insured |

⚠️ **A `special` vdev is part of the pool: if it dies, the pool dies.** Never single.
`feature@device_removal` is enabled and all vdevs are mirrors, so it **is** removable
later — a genuine safety net that RAIDZ would not give you.

**Timing:** a special vdev only captures **new** writes. `vault` is empty today, so it
gets 100 % metadata coverage for free. After migration you would have to rewrite
everything to achieve the same.

---

## 5. Recordsize policy (measured, §3)

| Dataset class | recordsize | Evidence |
|---|---|---|
| media / ISO / backup (streaming) | **1M** | best seq read+write; 25× worse random write is irrelevant here |
| documents / home / general | **128K** | best seq read (461.9), best random read (985 IOPS) |
| `k8s/config`, SQLite apps | **128K** | reads favour it 1.9×; writes favour 16K 2.2× — read-dominant workload wins |
| write-heavy small-random (if any appears) | **16K** | 2.2× write advantage (104.2 MB/s) |
| VM zvols | **untested** | `volblocksize` is create-time-only — **must be measured, not assumed** |

`special_small_blocks`: **leave at 0 by default.** Measured `64K` cost **28 %**
sequential write (679 → 486 MB/s) for no random-I/O gain. Enable per-dataset only for
genuinely small-file workloads.

---

## 6. Stabilise (before any migration)

- [ ] Scrub `vault` and confirm clean
- [ ] Enable SMART short (daily) + long (weekly) tests on all 12 HDD
- [ ] Scrub schedule (monthly) + snapshot tasks
- [ ] Alerting to a real destination — the reinstall proved config is lost, not data
- [ ] **Off-box TrueNAS config backup**, automated. `boot-pool` is a single SATADOM;
      the 2026-08-04 reinstall lost shares/users/tasks while `vault` imported cleanly
- [ ] Buy a **second SATADOM** — the only purchase that fixes a live SPOF

---

## 7. Migration plan

### 7.1 The blocker

**nas02 holds ≈66 TB. vault's safe ceiling is ≈27.4 TiB.** The data does not fit.
Options, in order of preference:

1. **Purge first** — dedupe/delete before moving. `crossseed-data` (~4.2 TB) uses
   hardlinks, so `du` overstates it; measure with `du --count-links=no` first
2. **Add the 5× 12 TB** as 2 more mirror vdevs → ~48 TiB, which does fit
3. **Split cold data** to a separate `archive` pool (Option D)

### 7.2 Order of operations

1. Fix `boot-pool` redundancy (needs the SATADOM)
2. Stabilise (§6) — scrub clean, SMART passing, alerting live
3. Create datasets per §5 (**recordsize is immutable — get it right first**)
4. Create shares, verify NFS/SMB throughput (still unmeasured)
5. Migrate **one non-critical dataset**, verify, then batch the rest
6. Move kopiur's `ClusterRepository` from nas02 → nas01 **last**, once nas01 has proven
   stable under real load

### 7.3 Rollback

nas02 stays authoritative until step 6. Until then, rollback is "stop and keep using
nas02" — no data at risk.

---

## 8. Open questions

1. Location of the 4× 20 TB Ironwolf — changes whether Option D is available now
2. Read/write ratio of the *arr workloads — would settle 128K vs 16K definitively
3. VM zvol `volblocksize` — needs its own test before any zvol is created
