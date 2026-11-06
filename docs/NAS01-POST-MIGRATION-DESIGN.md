# nas01 — loaner-assisted migration and final layout

**Inventory updated 2026-11-06; source measurements remain 2026-11-02.
Proposal, not permission to change storage.** Native,
read-only TrueNAS 25.10.7 and DSM checks supersede the September inventory and
purchase/purge plan. No pool, dataset, share, ACL, user, service, or source data
was changed while preparing this plan. No migration copy has run.

The detected 4 TB SATA loaners solve **temporary landing space**, not
permanent expansion. They must be a **separate disposable pool**, never data
vdevs added to a production pool. RAIDZ data vdevs cannot be removed individually;
RAIDZ cannot shrink or become a different parity level. Returning these disks
does not mean detaching them from a populated pool.

### Current eleven-drive gate and the owner's alternatives

The November 6 read-only kernel and TrueNAS middleware inventories both see
**eleven new 4 TB WD drives**: ten WD4000FYYZ and one WD4002FYYZ. TrueNAS lists
all eleven as unused; their logical/physical sectors are 512/512 bytes. This
does not prove an old filesystem is disposable or that SMART/extended tests
have passed. The twelfth drive's broken connector is an owner-reported physical
gate. The five additional desktop drives are absent from both inventories,
not merely hidden from the pool-creation UI.

Desktop SATA is supported by this installation: existing IronWolf drives and
the new WD SATA drives already operate behind the SAS HBA. Desktop does not
mean SMR, and CMR/SMR recording does not determine whether a disk enumerates.
Identify the five exact models and test each in a known-good bay/cable/power
path before blaming recording technology. Power-disable behavior, seating,
power supply, link negotiation or a failed disk remain possibilities, not
diagnosed causes. SMART/kernel-journal reads were unavailable to the current
SSH identity; no permission or appliance configuration was changed to obtain
them. Do not use the damaged drive as a required member before it is qualified.

Assuming eleven **4 TB** loaners, these are nominal upper bounds, not actual
ZFS available space:

| Comparison                                         | Nominal data TB |   TiB | 80% target TB |
| -------------------------------------------------- | --------------: | ----: | ------------: |
| Separate 11-wide RAIDZ1                            |              40 | 36.38 |          32.0 |
| Separate 11-wide RAIDZ2                            |              36 | 32.74 |          28.8 |
| Expand current 6-wide SMB RAIDZ1 to 17-wide RAIDZ1 |              64 | 58.21 |          51.2 |
| Evacuate/recreate all 17 as RAIDZ2                 |              60 | 54.57 |          48.0 |

These are **TB/TiB, not GB**. RAIDZ expansion is enabled on the existing SMB
pool and can widen its current RAIDZ1 vdev; it cannot change that vdev to
RAIDZ2 or later remove the eleven loaners. Existing blocks also retain their
old data/parity ratio until rewritten. Recreating as RAIDZ2 requires verified
evacuation, share/home recovery and separate destruction approval. Adding a
second RAIDZ2 vdev instead would leave the original RAIDZ1 vdev's protection
unchanged; it would not convert the whole pool to RAIDZ2.

Prefer a separate disposable staging pool over a very wide production SMB
expansion: it preserves the live homes/failure domain and makes the loaners'
eventual removal explicit. RAIDZ1 buys 4 TB more staging capacity here but
tolerates only one failed member; eleven old disks and a long migration make
that a real risk decision, not a free capacity upgrade. Even its 40 TB nominal
capacity cannot hold the measured 44.942 TB data tree alone, before homes.
RAIDZ2 with eleven drives loses 4 TB nominal and 3.2 TB of the 80% allowance
versus the twelve-drive example below. That example is **not a verified
eleven-drive allocation**. Repair/qualify the twelfth drive, recover additional
independent staging capacity, or recalculate every hardlink-closed shard from
fresh logical bytes and actual destination budgets before approving a copy.

The owner's later preferred final candidate is homogeneous 4×20 TB RAIDZ1
plus 4×12 TB RAIDZ1: 60 + 36 = **96 TB nominal**, with a 76.8 TB 80% target.
The older RAIDZ2 alternatives below remain comparisons, not a decision to
override that preference or execute pool creation. If both vdevs share a pool,
two failures in either lose the pool; downloads/media must still share one
dataset for hardlinks.

## 1. Verified starting point

| Existing pool | Current geometry                                                    | Used / dataset available | Treatment                                                       |
| ------------- | ------------------------------------------------------------------- | ------------------------ | --------------------------------------------------------------- |
| `nfs`         | 4×8 TB RAIDZ1; mirrored 1 TB P3 special; mirrored 118 GB Optane log | ~14 MB / 23.105 TB       | Production `media` **and** `netboot` NFS exports; preserve      |
| `smb`         | 6×4 TB RAIDZ1                                                       | 86.755 GB / 18.934 TB    | Production private homes; preserve                              |
| `backups`     | 2×10 TB mirror                                                      | 2.902 TB / 6.942 TB      | Existing Frigate, photos and PVE backups; **not staging space** |
| `local`       | 2×512 GB SATA SSD mirror                                            | 99.132 GB / 391.971 GB   | Production Garage, Zot and apps; **not staging space**          |
| `boot-pool`   | 2×64 GB mirror, plus 64 GB spare                                    | ONLINE                   | Preserve                                                        |

All five pools were ONLINE without known data errors. The last displayed data
pool scrubs were October 4; that is **not** a fresh migration scrub.

There are eight NVMe devices, **not eight free NVMe devices**:

- Two P3 1 TB devices and both Optanes are already in `nfs`'s special/log mirrors.
  Removing a special mirror member blindly can lose the whole pool.
- Two other P3 1 TB devices are not in the live pools. One still has a GPT and
  partition, although no filesystem signature was reported; it is **not proven
  safe to erase**. The other reported no partition/signature.
- Both Samsung PM981 256 GB devices reported no partitions/signatures and no
  live-pool reference. Ownership, by-id/serial and any unimported pool must still
  be checked before approved reuse.

Kernel names are observations, not disk-selection instructions. Use serial/by-id
inventory and explicit owner approval for every future destructive operation.
Do not add L2ARC, cap ARC, move Garage, or rebuild boot as part of this migration.

### Source scope and capacity

One hardlink-aware `du -sxk` invocation across the three volume1 roots measured:

| NAS02 source      |                  Bytes | Decimal TB |        TiB |
| ----------------- | ---------------------: | ---------: | ---------: |
| `/volume1/data`   |     44,942,121,472,000 |     44.942 |     40.875 |
| `/volume1/homes`  |     16,641,964,244,992 |     16.642 |     15.136 |
| `/volume1/docker` |         42,891,108,352 |      0.043 |      0.039 |
| **Subtotal**      | **61,626,976,825,344** | **61.627** | **56.049** |

`df`'s 70.858 TB used on volume1 is **not** the copy payload. Conversely, `du`
allocated bytes are not a complete logical-byte inventory: compression, sparse
files and reflinks can change destination demand. Scan a frozen source before
approving capacity; do not assume ZFS deduplication or compression savings.

**This is not yet a complete NAS02 evacuation inventory.** Volume2 is mounted
and holds `ActiveBackupforBusiness`; its filesystem reports ~5.513 TB used.
The deduplicated ABB store needs a separately tested DSM-compatible recovery
plan or explicit retention decision, not an ordinary `rsync` capacity estimate.
The old `/volume3` figures are historical; the current check did not show a
separate mounted filesystem there. Inventory all current shares, snapshots,
packages and backup obligations before releasing any NAS02 disk.

**Docker bind mounts are not a complete application-state inventory.** The
current Auditorr SQLite database is `/app/data/auditorr.db` in the container's
writable layer; only `/config` binds `/volume1/docker/appdata/auditorr`. The
November 1 restart did not deploy the proposed persistence fix. Copying the
Docker share alone therefore misses the live database. Before any recreation,
obtain an SQLite-consistent backup using the online backup API or a fully
quiesced database/WAL snapshot, verify it without exposing personal payloads,
and approve an explicit persistent mount and restore test. Do not copy just an
active `.db`, rely on a container export, or overwrite history with the proposed
backport's state. Inspect only whitelisted mount/storage metadata, never dump
environment variables or credentials into migration records.

## 2. Capacity and the final design tradeoff

TB below means 10^12 bytes; TiB means 2^40 bytes. These are **nominal upper
bounds**, before ZFS slop, padding, metadata, quotas and snapshots.

| Phase / geometry                                      | Raw TB | Parity TB | Stranded TB | Nominal data TB / TiB | 80% target TB |
| ----------------------------------------------------- | -----: | --------: | ----------: | --------------------: | ------------: |
| Detected loaners: 11×4 TB RAIDZ1                      |     44 |         4 |           0 |           40 / 36.380 |          32.0 |
| Detected loaners: 11×4 TB RAIDZ2                      |     44 |         8 |           0 |           36 / 32.742 |          28.8 |
| Conditional twelve-drive example: 12×4 TB RAIDZ2      |     48 |         8 |           0 |           40 / 36.380 |          32.0 |
| Owner-preferred donor candidate: two 4-wide RAIDZ1    |    128 |        32 |           0 |           96 / 87.311 |          76.8 |
| Initial final pool: one 8-wide RAIDZ2, 4×12 + 4×20 TB |    128 |        24 |          32 |           72 / 65.484 |          57.6 |
| Final: above + 4×8 TB RAIDZ2                          |    160 |        40 |          32 |       **88 / 80.036** |      **70.4** |
| Alternative: three homogeneous 4-wide RAIDZ2 vdevs    |    160 |        80 |           0 |           80 / 72.760 |          64.0 |

**Older all-RAIDZ2 comparison, not the owner-preferred default:** one new bulk pool with the two RAIDZ2 data
vdevs above, separate `data`, per-user `home`, and small infrastructure datasets.
Keep `downloads` and `media` **directories within the same `data` dataset**.
Never turn either into a child dataset or separate NFS filesystem.

This deliberately trades the September proposal's separate media/vault failure
domains for sufficient permanent capacity without retaining loaners. It does
**not** convert an existing pool. The mixed 8-wide vdev strands 32 TB, but has
less parity overhead than two 4-wide vdevs and yields 8 TB more usable space.
Homes remain independently backed up; sharing a pool is not backup isolation.

The mixed eight-disk group uses only 12 TB per disk: 96 TB participates,
24 TB is parity, and 32 TB of the larger drives is stranded. It is not a
space-efficient default. The alternative homogeneous groups avoid that
stranding but have different parity overhead. Select the final layout only
after a consistent logical-byte inventory and explicit capacity, failure-domain
and outage tradeoffs; the table alone does not choose the design.

The old separate-pool design does not fit the measured payload at 80%:
4×12 RAIDZ2 + 4×8 RAIDZ2 + 6×4 RAIDZ2 gives media only 56 TB nominal,
44.8 TB at 80%, **less than 44.942 TB before overhead**. Retiring the six 4 TB
disks makes that gap larger. Separate pools require additional permanent
capacity or an explicitly approved smaller payload; neither is assumed here.

The 3% planning allowance makes the subtotal **63.476 TB**, not a guaranteed
ZFS requirement. Even the homogeneous 80 TB option is too tight once real ZFS
space deductions are included. Measure actual available capacity before each
phase; stop rather than relax headroom silently.

Under the owner-preferred 96 TB donor candidate, production `nfs`, `backups`,
`local` and boot stay unchanged. The older 88 TB all-RAIDZ2 alternative below
would additionally require an approved NFS evacuation/rebuild.
The six owned 4 TB
disks can become cold spares **only after** the existing NAS01 homes and any
staging data have been separately verified, cut over and approved for evacuation.
Until then, the current SMB pool remains production.

### Free NVMe use

Subject to identification and approval, use the two free P3s as a **standalone
mirrored flash pool**, and the two PM981s as a second standalone mirror.
These can hold bounded offline staging shards and Docker/configuration state,
then become fast application storage after application-specific restore tests.
No application is moved merely because its source directory was copied.

Do not use consumer P3/PM981 devices as a replacement SLOG. Keep the existing
Optane log and P3 special mirror attached to `nfs` until that pool is evacuated.
Afterward, reusing the mirrored Optanes for measured bulk NFS sync traffic is a
separate approved change. A future special vdev requires a separate design:
RAIDZ2 needs three-way special redundancy to retain two-failure tolerance;
adding it is not a reversible cache change. Default here is **no new special**.

## 3. Staging without rebuilding production first

Keep all current pools, exports and home shares. After approval, create **new,
unshared staging datasets**, not directories inside someone's private home:

- Entire NAS02 homes tree → a new staging dataset on `nfs`.
- Data → the loaner pool, a new sibling staging dataset on `smb`, and bounded
  shards on the new flash mirrors if measured capacity requires them.
- Docker → bounded flash staging, with package/database consistency handled
  separately. Never consume `local` or `backups` free space.

The loaner pool alone cannot hold the data tree: 40 TB nominal versus 44.942 TB.
The old suggestion to copy everything into one existing empty pool was wrong.

**These are offline, hardlink-closed shards, not a live split media layout.**
Every `(filesystem, inode)` hardlink group is assigned intact to exactly one
staging filesystem. Downloads and all media names linked to them travel in the
same `rsync -H` list. All shards later reassemble into one final `data` dataset.
There is no merger filesystem, cross-filesystem hardlink claim, reflink fallback,
or relocation of stopped torrents/tracker holds.

Twelve-drive RAIDZ2 illustrative allocation, **not executable budgets or a
current eleven-drive fit**:

| Stage                        | Logical data TB | 3% data allowance TB | Other occupancy                                |
| ---------------------------- | --------------: | -------------------: | ---------------------------------------------- |
| Loaner RAIDZ2                |          29.700 |               30.591 | measured filesystem overhead                   |
| Existing SMB sibling dataset |          14.492 |               14.927 | existing 86.755 GB + production growth reserve |
| Free P3 mirror               |           0.650 |                0.670 | no existing production data                    |
| Free PM981 mirror            |           0.100 |                0.103 | Docker ~0.044 TB including allowance           |
| Existing NFS staging dataset |    homes 16.642 |               17.141 | live exports retained                          |

This is a tight temporary fit, not a promise. Current SMB root measurements with
20% headroom and 100 GB reserved for production growth give only
**15,029,992,479,340 additional bytes**. Refresh that number and increase the
growth reserve if needed. The scanner uses **logical unique-inode bytes**,
charges each hardlink group once, includes directory allowance, and refuses
groups that do not fit. If actual datasets or source logical bytes fail the
budgets, obtain more independent staging capacity; do not overfill production.

**Physical gate:** 12 existing HDDs + 11 detected loaners = 23 HDDs during staging,
then **31 simultaneously connected HDDs** while the eight NAS02 donors form
the new pool. A qualified twelfth loaner restores the original 24/32 HDD
connection requirement. SATA SSD/boot connections are additional. Old documents disagree
about enclosure bays. Verify trays, SATA compatibility, HBA/expander addressing,
cables, cooling, PSU spin-up margin and UPS runtime for this peak. No bay or
power capacity has been established by this plan.
This is the connection peak of this staging plan, not a proof that every
alternative requires 31 or 32 bays. A 24-bay installation needs at least seven
additional temporary positions with eleven loaners, or eight with twelve,
or a separately capacity-verified
replacement/staging design before starting.

## 4. Ordered migration and outages

Every mutating step below is a **future approval gate**, not an instruction to
execute now. The helper contains no pool-creation, cleanup or copy executor.

1. **Preflight:** verify physical capacity, loaner SMART/serials, fresh scrubs,
   native config backup, UID/GID and Windows identity map, source ACL semantics,
   ABB recovery, logical payload and measured destination budgets. Prove an
   independent, restorable backup of irreplaceable homes/configuration.
   RAIDZ and a second dataset on NAS01 are not independent backups.
2. **Freeze a consistent source view:** use an approved read-only DSM snapshot,
   or quiesce its writers. Capture the metadata/hardlink/content reference from
   that exact view. Btrfs cannot `zfs send` to ZFS. Do not use a normal walk of
   a live application tree as a consistency guarantee.
3. **Seed new staging datasets:** review dry-runs and a small authorized sample
   first; then use native rsync with hardlink-closed lists. POSIX ACL/xattr
   transport must be tested separately; Synology ACLs do **not** automatically
   become correct TrueNAS NFSv4 ACLs. Verify the merged staging roots against the
   frozen source, including hardlink topology and SHA-256 contents.
4. **Final source gate:** stop writers, retain torrent resume state and the
   original 99-torrent baseline, account for every later change, and verify
   the final frozen reference again. The helper does not implement incremental
   shard reconciliation. Moving/deleted names or changed hardlink groups require
   an approved destination-only reconciliation; never blanket `--delete` and
   never source cleanup. With no tested delta protocol, keep writers frozen
   throughout the authoritative copy and verification instead of promising a
   short outage.
5. **Release NAS02 disks only after explicit approval:** all source shares and
   ABB obligations accounted for, critical-data backup restore tested, staging
   checks complete. Reusing the eight disks ends NAS02 as a disk-based rollback
   option. Do not describe the remaining staging RAIDZ as a second source copy.
6. **Create the owner-preferred donor pool only after separate approval:**
   homogeneous 4×20 TB RAIDZ1 plus 4×12 TB RAIDZ1, not a mixed-width 8-disk
   RAIDZ2 vdev. Its nominal 96 TB/76.8 TB headroom target exceeds the current
   63.476 TB planning allowance, but actual available space and frozen logical
   bytes still decide. Reassemble data into one final `data` dataset, with
   separate reviewed private-home/infrastructure datasets. Never delete from
   another staging shard while merging.
7. **Preserve the current NFS pool:** this 96 TB candidate does not require
   retiring its four 8 TB disks or moving its mandatory special/log mirrors.
   Existing `media`/`netboot` exports and clients remain live. Its temporary
   staging datasets are not disposable until verified final copies,
   independent backups and approved rollback retention exist. Any later
   export/client cutover or pool retirement needs its own explicit approval.
8. **Finish reassembly:** copy the remaining data into the same final dataset;
   verify against the saved frozen source reference. Apply only the reviewed
   identity/ACL translation to user homes and test with ordinary user accounts.
   Cut over each client and retain verified staging for the agreed rollback
   period. Source SHA equivalence alone is not an application restore test.
9. **Return all twelve loaners together:** clean final scrub, full reference
   verification, approved ACL differences, no hardlink inflation, all clients
   using final paths, torrent state/holds unchanged, independent backups and
   restore checks passing, and rollback retention satisfied. Only then approve
   disposal of the staging pool. Do not detach individual RAIDZ disks or erase
   loaners as an automatic cleanup step.

If the owner instead selects the older **mixed 8-wide RAIDZ2** alternative,
its initial 72 TB nominal/57.6 TB target cannot hold the current allowance.
That alternative needs a bounded first batch (for example 35 TB data plus
homes/Docker, ~53.236 TB with 3%), followed by separately approved evacuation
of current NFS and addition of its four 8 TB disks as RAIDZ2, reaching 88 TB.
It is not the default sequence above and does not authorize destroying NFS.

**Copy floor:** every retained byte travels NAS02 → staging → final, about
123.254 TB for the current subtotal, plus deltas and verification reads.
The preferred 96 TB candidate avoids a third full copy without recycling the
current NFS pool or postponing part of the final dataset for capacity growth.
It also avoids
repeated full-array resilvers just to replace loaners.

At **measured sustained** 300–600 MB/s, one 61.627 TB pass alone is ~57–29 hours;
these rates are examples, not current benchmarks. SHA passes and scrub time are
additional. With the delivered frozen-source helper and no incremental
reconciliation protocol, budget both authoritative copy passes: roughly
57–114 hours of copying, plus verification, while writers remain frozen.
Keeping the source live during a preliminary snapshot seed does not eliminate
the later tested delta/reconciliation gate. Do not book a short cutover until
that protocol or additional staging capacity has been proved. Homes may cut
over earlier after their independent security tests.
Current NAS01 Garage/backups/SMB remain online; the existing NFS clients need
an explicitly scheduled final remount/export cutover.

The earlier twelve-loaner in-place alternative is not the recommended shortcut
or a current eleven-drive fit: a 12-wide
loaner vdev has twelve slots but only eight large donor replacements; the last
four do not disappear. For example, adding that vdev to current NFS gives
24 + 40 = 64 TB nominal. Replacing eight members with donors and four with
owned 4 TB disks leaves the RAIDZ minimum member size at 4 TB: **still 64 TB**.
The 63.476 TB allowance would be ~99.2% full even before ZFS deductions, versus
an 80% target of 51.2 TB. Evacuating SMB to free those four owned disks therefore
hits a concrete **12.276 TB headroom deficit**; the old NFS RAIDZ1 vdev also
cannot later be removed to improve parity.

The explicit second copy is measured at **61,626,976,825,344 additional logical
bytes**, rather than hiding I/O under the word “resilver.” For replacements,
measure the actual allocated fragment bytes `A` of each candidate member first:
each replacement writes approximately `A`, and reconstructing a RAIDZ stripe
reads multiple surviving columns. A fully occupied 4 TB member in 12-wide
RAIDZ2 illustrates the scale: roughly 4 TB replacement writes and order
40 TB reconstruction reads, per member; eight such replacements would be order
32 TB writes / 320 TB reads. These are geometry illustrations, **not measured
loaner allocations or promises about OpenZFS scan I/O**. Replacing all twelve
would add more I/O and twelve degraded-vdev intervals without fixing the
capacity deadlock. A genuinely viable replacement option needs extra permanent
capacity and its own measured allocation/backup plan. Do not sell it as a
zero-copy final RAIDZ2 migration.

## 5. Safe helper commands and limits

[`scripts/nas01_migration.py`](../scripts/nas01_migration.py) uses Python's
standard library. Default invocation only prints capacity estimates.
`preflight` only prints its fixed inventory commands unless `--run` is supplied;
even then it runs read-only inventory/version queries, never a transfer.
`rsync-plan` **always** renders `--dry-run`; it never executes rsync transfers,
creates mounts/datasets, stops applications, changes ACLs or deletes files.

```bash
python3 -B scripts/nas01_migration.py
python3 -B scripts/nas01_migration.py preflight --host nas01 --ssh ADMIN@192.168.42.45
python3 -B scripts/nas01_migration.py preflight --host nas02 --ssh nas02.in.homeops.ca
python3 -B scripts/nas01_migration.py budget \
  --used-bytes 86754527840 --available-bytes 18934179231136 \
  --growth-reserve-bytes 100000000000
python3 -B scripts/nas01_migration.py rsync-plan \
  --source READER@nas02.in.homeops.ca:/volume1/data/ \
  --destination /mnt/loaner/nas02-stage-data/ --sharded
```

`ADMIN`/`READER` are placeholders for the already documented authorized
identities, not requests to create accounts. Use only separately tested POSIX
ACL paths with `--posix-acls-tested`. Native versions are DSM rsync **3.1.2** and
TrueNAS **3.2.7**; do not assume newer source options such as nanosecond mtime
comparison. The fingerprint compares POSIX mode/UID/GID, whole-second mtime,
symlink targets, hardlink groups and optional contents; **not ACLs, xattrs,
birth times, DOS attributes or application semantics**.

The direct DSM SSH command `rsync --version` was denied, while the existing
authorized `sudo -n /usr/bin/rsync --version` succeeded. Preflight uses the latter.
If the approved migration operator needs that same established sudo path,
`rsync-plan --source-sudo` renders the fixed
`--rsync-path='sudo -n /usr/bin/rsync'` option; it still cannot execute a copy.
Do not grant new sudo rights, weaken the SSH command policy, or guess passwords
to make a transfer work.

Run the following on an approved read-only view with the helper available;
replace every budget with freshly calculated **additional** bytes after
headroom and production growth reservations:

```text
nas01_migration.py shards --root /READ_ONLY_VIEW/data \
  --budget loaner=MEASURED_BYTES --budget smb=MEASURED_BYTES \
  --budget flash=MEASURED_BYTES --budget smallflash=MEASURED_BYTES
```

The summary contains no personal filenames. `--files-for SHARD` emits a
NUL-delimited list only with the matching `--expect-signature` from that frozen
scan. Stream that list to the rendered NAS01-side rsync command's stdin.
`--no-recursive --dirs` is intentional: listing directories must **not**
recursively pull unassigned files into a shard. Keep all lists, logs, identity
maps and reference JSON private and outside Git; never publish file inventories.

`fingerprint --root ROOT --checksum` prints a reference JSON without filenames.
`verify --root STAGE1 --root STAGE2 ... --baseline REFERENCE.json --checksum`
merges offline shards by relative path, rejects conflicting names and checks
the reference. Metadata-only fingerprints cannot pass `verify`. Roots must
not cross filesystems or contain links outside their scope. Ordinary source
changes detected during validation cause a stop, not an automatic copy fallback.
Full checksumming reads
every unique file and must be scheduled, not run as a casual health probe.

Tests, using generated fixtures only:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s scripts -p 'test_nas01_migration.py'
```

## 6. `\\nas01\home`: per-authenticated-user access

**Username substitution works, but it currently stops one level above the
account's real home.** Native API, active SMB session metadata and `testparm -s`
on 2026-11-02 confirmed:

```text
name = home
purpose = PRIVATE_DATASETS_SHARE
configured dataset path = /mnt/smb/home
generated Samba path = /mnt/smb/home/%U
account home = /mnt/smb/home/USERNAME/USERNAME
access based share enum = Yes
read only = No
```

TrueNAS 25.10's supported
[Private Dataset Share](https://www.truenas.com/docs/scale/25.10/scaletutorials/shares/smb/smbprivatedatasetshare/)
substitutes the authenticated username. The configured dataset path intentionally
does not contain `%U`; middleware adds it. The outer user path is a ZFS dataset;
the inner, user-owned directory is the account's actual home. Opening the share
therefore shows the extra username directory even under the correct SMB identity.
This is not evidence that the client used the wrong account.

Two supported corrections have different tradeoffs:

1. **Share-only compatibility correction:** keep the existing share name `home`
   and base dataset, use `LEGACY_SHARE` options with `path_suffix = %U/%U` and
   `home = false`. This targets the existing inner home without moving data or
   changing ACLs. The compatibility preset is not SMB1 and does not create the
   special `[homes]` share, but it no longer automatically creates private
   datasets for new users.
2. **Normalize the account/dataset layout:** retain `PRIVATE_DATASETS_SHARE`,
   take a recoverable backup, and deliberately make the account home and share
   root agree. This needs a reviewed data/ACL migration and verification of SSH
   authorized-key paths and other home-directory consumers.

Choose and approve one correction before applying it. Do not change the private
dataset naming schema to create a dataset over an existing populated directory,
edit generated Samba files, or broadly rewrite ACLs. `browsable=true` advertises
the share name; access-based share enumeration is not folder ACLs.

Start with read-only checks on the actual affected Windows client:

```powershell
Get-SmbConnection |
  Where-Object ServerName -in @('nas01', 'nas01.in.homeops.ca', '192.168.42.45') |
  Select-Object ServerName, ShareName, UserName, Dialect
net use \\nas01\home
```

The desired entry point remains **`\\nas01\home`**, not a manually appended
username. Compare the displayed identity during acceptance testing, but do not
repeat a cached-administrator diagnosis when current session metadata proves the
intended user is already authenticated.

If the identity is wrong, first obtain approval to disconnect only the affected
NAS01 mappings and reconnect as the intended NAS01 SMB account, prompting for
the password locally. Do not issue global `net use * /delete`, clear unrelated
credentials, disable authentication, or give normal users admin privileges.
If identity and nesting are correct but isolation fails, capture the specific
share/path/identity evidence and review only that user's dataset/share ACL in
TrueNAS before proposing a narrowly scoped, backed-up change.

Acceptance requires two ordinary users: each opens the same UNC and reaches
their own root, an intentionally tested other-user path is denied, and existing
application clients remain working. No user/ACL/share change or client-session
reset has been performed or claimed by this plan.
