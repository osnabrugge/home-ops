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

## A0-mcp. MCP coverage gaps (raised 2026-08-05)

- [ ] P2: MCP servers wanted for: **Omada**, **Proxmox**, **MikroTik** (`ext01`,
      management-only so lower value), **XGS-PON** (`xgspon01.in.homeops.ca` — the
      Bell Fibre demarc, relevant to the 8 Gbps dispute)
- [ ] P1: The 4 existing ToolHive MCP servers (kubectl, flux, brocade, opnsense) are
      **Ready and Running but only on ClusterIP** — no HTTPRoutes, and no entries in
      `.vscode/mcp.json`. They are unreachable from the editor. Expose them like radar
      (`https://radar.homeops.ca/mcp`) and register them.

---

## A0. NETWORK — VLAN1 cannot be tagged (raised 2026-08-05, HIGH PRIORITY)

### Root cause (Sean's diagnosis — correct)

On Brocade ICX (FastIron), **VLAN 1 is the DEFAULT-VLAN and cannot be tagged** while it
holds that role. Ports are untagged members of it; trunks carry it as native/untagged
only. Same historically true on Omada.

**The fix Sean used before and removed:** set the default VLAN to an unused dummy id
(e.g. **4090**), which frees VLAN 1 to behave as an ordinary taggable VLAN. OPNsense
never needs to know 4090 exists. Sean dropped this when upgrading to ICX6610-48P and
also removed it from Omada (`oc01`) — the problem likely returned then.

- [ ] P0: Verify `default-vlan-id` on **core01** (and any second ICX) and whether it is
      still 1
- [ ] P0: Plan the change to `default-vlan-id 4090` — **disruptive**: it re-homes every
      untagged port, needs a maintenance window and console/OOB access as fallback
- [ ] P0: Re-apply the same dummy-default-VLAN trick on **Omada (`oc01`)**
- [ ] P1: Verify pve01 then receives VLAN1 **tagged** cleanly to/from OPNsense
- [ ] P1: Re-test Omada device adoption afterwards (likely the same root cause)

> ❌ **Rejected as bandaids (2026-08-05):** adding `opt2` to the `High_Trust` interface
> group, or adding a targeted LAN pass rule. Both mask a layer-2 tagging fault with a
> layer-3 permit and would leave the real defect in place.

### Keep VLAN1 — decided

VLAN1 stays. It is the vendor dumping ground for factory-default devices and is worth
having **precisely so it can be monitored and restricted**. The goal is: everything real
runs on explicit tagged VLANs; VLAN1 exists, is contained, and is watched.

### Verified facts (2026-08-05)

- `core01` VLANs configured: **1 10 42 50 70 99** (VLAN 90 is NOT on the switch)
- VLAN 10 has **no untagged ports**; only tagged on the trunk/DualMode uplinks
- gw01 interface map: `opt2`=vlan0.1 LAN · `opt3`=vlan0.10 Trusted · `opt4`=vlan0.42
  Servers · `opt5`=vlan0.50 Guests · `opt6`=vlan0.70 IoT · `opt7`=vlan0.99 Mgmt
- Interface groups: `High_Trust`=opt3,opt4,opt7,opt8 · `Low_Trust`=opt2,opt5,opt6 ·
  `Untrust`=opt1,opt9
- `mgmt_hosts` alias contains **both** 192.168.0.115 and 192.168.10.115 — the
  workstation has a presence on VLAN1 *and* VLAN10
- pve01 OVS: `bond0` has `tag=1 vlan_mode=native-untagged`; `tap100i0` (gw01 net0) is an
  untagged **trunk** port
- ✅ `iperf3 testing` rule (seq=1000, opt6/opt2/opt4 wide open) — **disabled by Sean**

### A0-c. access02 unreachable / un-adoptable — ROOT CAUSED + FIXED 2026-08-05

**Symptom:** Omada showed access02 at `192.168.0.176`; that address was dead; the switch
could not be adopted and its web UI appeared unreachable. Suspicion fell on VLAN tagging
on access02. **access02 was not at fault.**

**Root cause — one DHCP lease slot, two claimants.** access02 ran DHCP on *both*
`interface vlan 1` and `interface vlan 99`, from the **same chassis MAC and the same
client-id** (`01:5c:a6:e6:b6:b4:44`). dnsmasq keys leases by client-id, so it can hold
only **one lease per switch**. The two interfaces fought over that slot, the VLAN1 client
won, and the address silently drifted `.176 → .177` while the controller kept the stale
value and kept trying to manage a dead IP.

Evidence that isolated it (all from gw01, which is L2-adjacent on `vlan0.99`):

| Probe | Result |
|---|---|
| `http 192.168.99.22` from src .99.1/.99.2/.42.1/.10.1/.0.1 | **200 from every subnet** → no management ACL |
| `http 192.168.0.176` from src .0.1 and .99.1 | **000 / no response** → address is dead |
| `arp` for chassis MAC | `.0.177` on vlan0.1 **and** `.99.22` on vlan0.99 |
| dnsmasq leases | single entry `5c:a6:e6:b6:b4:44 → 192.168.0.177` |

**Fix applied (Sean, via web UI):** VLAN1 interface → *IP Address Mode: None*. Switch is
now single-homed:

```
access02# sh ip route
C  192.168.99.0/24 is directly connected, VLAN99
```

Releasing the VLAN1 address deleted the *only* lease record for that client-id — taking
VLAN99's record with it — which confirms the shared-slot diagnosis. Reservations already
pin both switches, so `.22` survives renewal:

```
dhcp-host=5c:a6:e6:b6:b4:66,192.168.99.21,access01
dhcp-host=5c:a6:e6:b6:b4:44,192.168.99.22,access02
```

> **Do not delete VLAN 1 on JetStream switches** — it is the system default VLAN and
> `no vlan 1` is rejected. Setting the *interface* to IP Address Mode: None is the
> supported way to remove the address. Never touch the VLAN99 interface's admin status;
> that is a console-recovery event.

**Emergency access pattern (reusable).** When a device's web UI is unreachable from the
workstation but gw01 can see it, tunnel rather than factory-reset:

```sh
ssh -f -N -L 18022:<device-ip>:80 -L 18443:<device-ip>:443 sean-admin@gw01.in.homeops.ca
# then browse http://localhost:18022  (VS Code auto-forwards the remote port)
```

### A0-d. Why cross-VLAN Omada adoption has never worked

**DHCP option 138 is emitted on exactly one VLAN, and is double-gated.**

```
dhcp-option=tag:b16ad63f…,tag:vlan0.1,138,192.168.99.240   ← only vlan0.1
dhcp-range=tag:vlan0.1,set:b16ad63f…,192.168.0.100,192.168.0.199,86400
dhcp-range=tag:vlan0.99,192.168.99.100,192.168.99.199,86400 ← no set: tag, no option 138
```

The `b16ad63f` tag is set only for clients that take an address **from the VLAN1 pool**.
Devices with `dhcp-host` reservations (access01/access02) get their address outside the
pool, so they likely never receive option 138 *even on VLAN1*. This is why firewall
rules, `udpbroadcastrelay` and DHCP options all appeared to do nothing — the option was
never reaching the devices.

**Two controllers are live simultaneously** — a strong candidate for historical adoption
thrash:

| Controller | Address | omadacId | Ver | Ports verified 2026-08-05 |
|---|---|---|---|---|
| Synology (`oc01`, nas02-bond0) — **old** | 192.168.99.240 | `5ab5f216de322fbb7001176694c5c6ed` | 6.3.0.36 | 8043, 29814 OPEN |
| Kubernetes (multus) — **new** | 192.168.99.30 | `4963024d89365c3635a5069d5fcc84fe` | 6.3.0.32 | 8043, 8088, 29811-29814 OPEN, https 200 |

The k8s controller pod carries **three** interfaces — `eth0` cilium, `net1` 192.168.0.30
(VLAN1), `net2` 192.168.99.30 (VLAN99) — and binds discovery on `udp6 :::29810`.
So it can talk to factory-default gear on VLAN1 *and* provisioned gear on VLAN99.

> ⚠️ **Correction (2026-08-05): the multus interfaces are NOT missing routes.**
> `cat /proc/net/route` inside the pod shows only `eth0` entries, which looks like the
> VLAN legs have no connected route. They do. Both NADs chain the **`sbr`
> (source-based routing)** plugin after `macvlan`, which by design moves each
> interface's routes into its own policy-routing table with matching `ip rule`
> entries — `/proc/net/route` only ever shows the *main* table. Verified working:
> `wget` from the pod reaches both 192.168.99.21 and 192.168.99.22.
> **Do not "fix" this** by adding connected routes; it is correct as-is.

**Correct inform URL for the new controller:**

```
omada://192.168.99.30?dPort=29810&mPort=29814&omadacId=4963024d89365c3635a5069d5fcc84fe
```

> ⚠️ `6a019344fa47ff44e14dc383` was tried first and is **wrong** — 24 hex chars is a
> MongoDB ObjectId, not an omadacId (32 hex). A device informing an unknown omadacId
> never appears in the controller at all. Always read the real value from
> `curl -sk https://<controller>:8043/api/info`.

> ⚠️ **Migration blocker:** the new controller (6.3.0.32) is *older* than the Synology
> one (6.3.0.36). Omada refuses to restore a backup into an older controller. Bump the
> k8s image to ≥ 6.3.0.36 before attempting a site migration, or rebuild config by hand.

### A0-e. NET-NEW adoption on VLAN99 only — COMPLETE ROOT CAUSE (2026-08-09)

Sean is **cutting over, not migrating** (clean DB — the beta-test junk stays behind).
So the gate is *"can a factory-default device be adopted with VLAN1 gone?"*, not
*"can existing devices be moved?"*. Verified state on 2026-08-09:

- New controller is now **6.3.0.42** (image bumped), `device` collection = **0**,
  no management VLAN configured, no discovery/pending records ever written.
- Both access switches respond on VLAN99 but **tcp/29812 (adopt) is CLOSED** — they
  are held by the old controller, not in an adoptable state.

**A factory-default Omada device tags nothing. All its traffic is untagged.** So it
lands on whatever the switch port's PVID is. Two independent faults both force that
onto VLAN1:

**Fault 1 — every AP/switch port has PVID 1.** `show interfaces brief`:

```
1/3/3  access01-1/0/9  Tag Yes  Pvid 1     <- tagged 10,42,70,99 / UNTAGGED vlan1
1/3/4  access02-1/0/9  Tag Yes  Pvid 1
1/3/5  ap01            Tag Yes  Pvid 1
```

VLAN1 is `by port` with no explicit member list, so on FastIron every port not
untagged elsewhere is implicitly untagged in VLAN1. Ports that *are* moved read
`Pvid 99` (kvm01, hdmi01, pdu02, ups02, pve02, ext01 on 1/1/8…1/1/26) — proving the
pattern already works on this switch.

**Fault 2 — option 138 is still only on the VLAN1 scope**, and now points at the new
controller, so it is right value / wrong VLAN:

```
dhcp-option=tag:b16ad63f…,tag:vlan0.1,138,192.168.99.30   <- vlan0.1 ONLY
dhcp-range=tag:vlan0.99,192.168.99.100,192.168.99.199,86400  <- no option 138
```

A device landing on VLAN99 therefore gets an address but is never told where the
controller is.

**Fault 3 (access02 only) — the uplink is a dynamic LACP LAG.** A factory-default
TL-SG3210XHP-M2 does not speak LACP, so resetting it collapses the bundle:

```
lag access02 dynamic id 4
 ports ethernet 1/3/4 ethernet 2/3/4
```

Reset access02 as-is and it comes back with no working uplink. The LAG must be
undeployed to a single port *before* the reset.

**Fix — no VLAN 4090 native-VLAN migration is required.**

1. **gw01** — add option 138 to the Management scope
   *Services → Dnsmasq DNS & DHCP → DHCP options → `+`*
   Interface `Management (opt7)` · Option `138` · Value `192.168.99.30`
   (Rollback: delete the row. Additive only; existing devices are unaffected because
   they hold static/reserved addresses and are already adopted.)
2. **core01** — give the device an untagged-99 port.
3. Factory-reset the device. It boots untagged → VLAN99 → pool `.100-.199` →
   option 138 → informs `192.168.99.30` → appears in the new controller.
4. **Leave "Management VLAN" unset in the new controller.** Devices then stay
   untagged on VLAN99 permanently, which is what makes VLAN1 deletable and what
   makes every *future* device (new switch, new EAP, RMA swap) adopt with zero
   manual steps.

**Zero-risk proof first — spare EAP650-Wall, no live device touched.**
`1/1/44`–`1/1/48` are free, unnamed, link-down, PoE-capable. Use `1/1/48`:

```
conf t
vlan 99
 untagged ethernet 1/1/48
exit
interface ethernet 1/1/48
 port-name eap-adopt-test
 inline power
exit
write memory
```

Rollback: `vlan 1 / untagged ethernet 1/1/48`.
Plug the EAP650-Wall into 1/1/48 (factory-reset it first — hold Reset ~10 s).
Pass = it appears under *Devices → Pending* in the k8s controller within ~2 min.

**Then access02**, in this order (step 1 drops access02 and everything behind it):

```
conf t
no lag access02          # or: lag access02 dynamic id 4 / no ports ethernet 2/3/4
vlan 99
 untagged ethernet 1/3/4
exit
write memory
```

then factory-reset access02, adopt it, re-create the LAG from the Omada side first
and the Brocade side second.

Why the earlier adopt attempt failed (controller log, 2026-08-05 05:30):

```
errorCode=-39002  "Device adoption failed because the device does not respond to adopt commands."
AdoptOneDeviceStatusResultVO(mac=5C-A6-E6-B6-B4-44, status=22)
```

The controller was sending adopt commands to the stale `192.168.0.176`. Fixed by A0-c.

- [ ] P1: Add **option 138 → 192.168.99.30** on the VLAN99 scope, **ungated by any tag**
- [ ] P1: Re-point the existing VLAN1 option 138 from `.240` → `.30`
- [ ] P1: Stop the Omada package on nas02 once `.30` has adopted everything
- [ ] P1: Upgrade k8s omada-controller to ≥ 6.3.0.36 if the site config is to be migrated
      rather than rebuilt
- [ ] P2: Set the inform URL on remaining devices (APs — method unproven; switches OK)
- [ ] P2: Decide the standing provisioning procedure for factory-default gear
      (land on VLAN1 → set VLAN99 IP + inform URL → move off VLAN1)

### Environment facts corrected 2026-08-05

- **dnsmasq is the DHCP server** on gw01 — *not* Kea (`kea enabled=0`) and *not* ISC
  (`no <dhcpd> section`). Config: `/usr/local/etc/dnsmasq.conf`;
  leases: `/var/db/dnsmasq.leases`. `pgrep` misses it; confirm with
  `sockstat -4 -l | grep -w 67` (runs as `nobody`).
- dnsmasq listens on `vlan0.1,vlan0.10,vlan0.42,vlan0.50,vlan0.70,vlan0.99,wg0` and has
  a `dhcp-range` on **every** VLAN — so "no DHCP on VLAN42" is *not* a thing.

#### Default-gateway design (deliberate — do not "fix")

| VLAN | DHCP router (opt 3) | Via |
|---|---|---|
| 10 Trusted | 192.168.10.4 | **core01** |
| 42 Servers | 192.168.42.4 | **core01** |
| 99 Mgmt | 192.168.99.4 | **core01** |
| 1 LAN | 192.168.0.1 | gw01 |
| 70 IoT | 192.168.70.1 | gw01 |

Trusted VLANs route via core01 so inter-VLAN traffic bypasses the firewall; core01's own
default is `ip route 0.0.0.0/0 192.168.99.1` (gw01), and core01 runs BGP with the k8s
nodes so it holds the `192.168.69.0/24` LoadBalancer routes. gw01 reaches VLAN69 only
*through* core01 (`192.168.69.0/24 via 192.168.42.4`) — so pointing a management device
at gw01 instead of core01 causes a hairpin for anything in the LB range.

> A device that changes interfaces keeps its old lease until it re-leases, and will be
> missing option 3 until then. Prefer adding `ip route 0.0.0.0/0 192.168.99.4` over
> toggling the VLAN99 interface — losing VLAN99 on a single-homed switch is a serial
> console recovery.

> `192.168.69.x` LoadBalancer VIPs do **not** answer ICMP (not even from gw01). Test
> them on their service port, never with ping.

- ⚠️ **Unknown / not yet verified:** the OPNsense firewall rules could not be read —
  parsing `filter/rule` out of `/conf/config.xml` returned empty, so the rule set is
  *not* where expected. The `High_Trust`/`Low_Trust` analysis in A0 above is therefore
  still **unconfirmed**. Do not act on it until the rules are actually read.

### ⚠️ Correction: VLAN 90 is NOT dead config

Previously flagged for removal from `talos/nodes/*.yaml.j2`. **Wrong.** VLAN 90 is
intended for **WireGuard remote-access**; it is simply not implemented yet. **Do not
remove it.**

- [ ] P2: Implement VLAN 90 / WireGuard remote access properly

---

## A0b. Infrastructure-as-Code via device APIs (raised 2026-08-05) — THE BIG ONE

> Sean: *"if this truly was implemented correctly, my entire infrastructure could become
> exactly what the purpose of this repository is for. A single source of truth and
> preventing a lot of the fuck ups between me needing to manually configure things."*

The cluster already self-provisions Service IPs, HTTPRoutes, DNS and certs. Extend that
model **outward to the physical estate** so infrastructure is declared in git, not typed
into web UIs.

- [ ] P1: **OPNsense API** integration — provision/deprovision firewall rules, internal
      IPs, DNS entries, ACME public certs from cluster state
- [ ] P2: Extend to the **Omada API** (network/device config)
- [ ] P2: Extend to the **TrueNAS API** (datasets, shares, snapshot tasks)
- [ ] P2: Design note — needs an operator/controller pattern with reconciliation and
      drift detection, not one-shot scripts, or it rots like any manual config
- ⚠️ Blocker found: the current OPNsense API key returns **403 on `firewall/filter`** —
      it is scoped for diagnostics/read only. Any automation needs a properly scoped key.

---

## A1. STORAGE CAPACITY — cost-effective expansion (raised 2026-08-05)


**Correction to `NAS01-DESIGN-OPTIONS.md`:** it treated 5× 12 TB as available. There
are **5 in total**, but only **ONE is free today** (new, unused RMA replacement). The
other **4× 12 TB and 4× 20 TB are IN USE in nas02** and only free *after* migration —
which is circular, since migration is what needs the space.

### Real disk economics (Sean's eBay research)

| Size | Used price | $/TB | Notes |
|---|---|---|---|
| 4 TB SATA/SAS | ~$40 | **$10/TB** | cheapest per TB |
| 8 TB | $100–200 | $12–25/TB | |
| 12 TB Ironwolf | **>$400 new (US)** | $33/TB | + shipping + duties — poor value |

- [ ] P0: **Data reduction first — it is cheaper than any disk.** Sean is confident
      there are large duplicates, obsolete app data, old installs, logs.
      Measure `crossseed-data` with `du --count-links=no` (hardlinks inflate `du`).
- [ ] P0: Produce a duplicate/waste report for nas02 before buying anything
- [ ] P1: Costed expansion options. Key insight: **mirrors do not require matched
      sizes across vdevs** — a 2× 4 TB mirror vdev can join a pool of 8/10 TB mirrors.
      So cheap 4 TB pairs at ~$10/TB may beat one 12 TB at $33/TB.
- [ ] P2: Other media on hand — 2.5" SSD (1× 1 TB, 2× 250 GB), older NVMe (128–250 GB).
      Low capacity; likely only useful for pve01 boot redundancy, not bulk.

### Desktop 990 Pro question (needs a decision, not a rush)

4× 2 TB Samsung 990 Pro sit in the desktop. Cannibalising leaves a single 1 TB 980 Pro
with **no redundancy**. Also: enabling the extra M.2 slots drops the RTX 3090 from
x16 to x8. Sean's workloads are inference, streaming w/ AI, video/photo editing.

- [ ] P2: Quantify before touching it — x8 vs x16 impact is small for inference and
      video work, but this trades *certain* desktop redundancy for *uncertain* NAS gain
- [ ] P2: Related plan: drop Windows → Ubuntu Studio with ZFS boot

---

## A2. SELL / LIQUIDATE (raised 2026-08-05) — funds the purchases

No budget left this month. Everything below is a candidate.

- [?] P1: **ASRock Rack X570D4U-2L2T + 4× 32 GB DDR4 ECC** (brand new, idle ~2 yrs).
      Needs a Ryzen Pro (~$120–150) **and** a rack case Sean does not have.
      **Decision: complete it, or cut losses and sell board+RAM?**
- [?] P1: **Supermicro X9 dual Xeon + 128 GB DDR3 ECC** (the original nas01) — sell?
      DDR3 era; power-hungry; likely low resale but zero ongoing value idle.
- [ ] P1: List old memory + NVMe on eBay/Reddit/Facebook
- [ ] P2: Rank everything by $/effort so the highest-value listings go first

### Purchases needed (priority order)

1. **Second SATADOM** — `boot-pool` is a single device; the only live SPOF
2. Storage capacity — but **only after** the data-reduction exercise
3. 3D printing consumables/parts (see H)
4. *Not yet:* ConnectX NIC, GPU (T4 ~$800). Neither fixes anything currently broken.

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

### ⚠️ ROLL-BACK OWED: homeops-runner GitHub App scope creep (2026-08-08)

While Azure Key Vault was disabled by the spend cap, Renovate and `tag.yaml` could
no longer fetch the `github-bot` App credentials from Key Vault. The **only** App
credential still recoverable was the one in the cluster — `home-ops-runner-secret`,
client id `Iv23liAXhB7wOa7IDFhY` — which exists to register **ARC runners**, not to
push code. It was reused as an expedient, and then granted extra permissions to
make Renovate work.

**This is scope creep that must be undone.** `homeops-runner` now holds
`contents: write` on the repo, so a compromised runner can push to `main`.
Registering runners and pushing dependency updates should not share an identity.

- [ ] P1: Restore Key Vault access (or migrate ESO), retrieve the original
      `github-bot` App credentials, and point `BOT_APP_CLIENT_ID` /
      `BOT_APP_PRIVATE_KEY` back at that App
- [ ] P1: Revoke the added permissions from `homeops-runner` — at minimum
      `contents: write`, `pull-requests: write`, `issues: write` — leaving only what
      ARC actually needs
- [ ] P2: If the original App is unrecoverable, register a dedicated Renovate App
      rather than leaving the runner App dual-purpose

> Repo secrets are write-only in the GitHub UI, so the current values cannot be read
> back. They are held at `~/secrets-escrow/github-app-repo-secrets.txt` (perms 600).

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

## I. Apps / identity / home-automation (raised 2026-08-05)

### I1. Omada — still cannot adopt devices
- [ ] P0: Migration from nas02 (`oc01`) blocked: **no device adoption**.
      Strongly suspected to be the **VLAN1 tagging fault (§A0)**, not an Omada bug —
      controller has `net1` on VLAN1 (192.168.0.30) which is exactly the broken VLAN.
- [ ] P1: Options: (a) fix VLAN1, (b) add a VLAN99 interface on the local switch,
      (c) **abandon VLAN1** and adopt over an explicitly-tagged VLAN.

### I2. Identity — nothing centralised
- [ ] P0: Everything is scattered (users, groups, systems, devices, SSH, RADIUS, MFA,
      OAuth). Goal is one pane of glass with real lifecycle management.
- [ ] P0: **Authentik was gated on one item Sean had to do — neither of us can recall
      what it was. Re-derive it from the current state before proposing more work.**
- [ ] P1: Authentik is a lot of manual learning/config for Sean. Evaluate honestly
      whether it is the right cost/benefit vs alternatives, given lldap already exists.
- Motivating pain: the IP cameras have no copy/paste, so any password rotation is
  manual and error-prone (§I3). Centralised identity directly reduces that pain.

### I3. Camera credentials + frigate/cam03
- [ ] P0: **Rotate `FRIGATE_RTSP_PASSWORD`** — leaked in a chat transcript 2026-08-03
      by ffprobe echoing the RTSP URL on error. **Identify the exact AKV secret name**
      (ExternalSecret `frigate` → key used for `FRIGATE_RTSP_PASSWORD`).
- [ ] P0: **cam03 still fails even after Sean set a matching password on all 3 accounts.**
      Earlier proof: cam02 `h264,2560,1440` vs cam03 `401 Unauthorized`, same URL/user.
      Next checks: is `viewer` in the right *group/role* on cam03; does the Dahua-clone
      firmware use separate "ONVIF user" vs "system user" tables; is there a leading/
      trailing space or a char the camera silently truncates (no copy/paste = high risk).

### I4. Matter / Thread
- [ ] P1: `matter-server` not set up and not connected to **OTBR01**.

---

## J. 3D printing + AI/MCP integration (raised 2026-08-05)

Real, blocking pain — Sean cannot print anything beyond PLA (HT-PLA-GF works well).

### J1. ABS/ASA first-layer adhesion failure — ROOT CAUSED 2026-08-09

**The BTT Eddy's thermal drift compensation was never calibrated.** Read live from
fdm02 (the SV08) — `printer/objects/query?temperature_probe btt_eddy`:

```json
{"temperature": 37.8, "calibration_temp": 39.686469,
 "max_validation_temp": 60.0, "drift_calibration_min_temp": 0.0,
 "estimated_expansion": 0, "compensation_enabled": false}
```

`compensation_enabled: false` and no `drift_calibration` polynomial in
`[temperature_probe btt_eddy]`. `PROBE_EDDY_CURRENT_CALIBRATE` was run (the
`calibrate:` table is populated) but `TEMPERATURE_PROBE_CALIBRATE` never was.

**Why this is exactly the observed symptom.** An LDC1612 eddy coil's inductance
drifts with its own temperature. The probe was calibrated at **39.7 °C**:

| Filament | Bed | Probe soak | Drift | Result |
|---|---|---|---|---|
| PLA | 60 °C | ~45 °C | small | sticks |
| ABS | **105 °C** | 70–90 °C | 0.1–0.3 mm | **nozzle parks too high** |

It is a *first-layer gap* fault, not a heat/chemistry fault. That is why bed
105 °C, heat-soaking, a big brim, a very slow first layer, hairspray, the stock
PEI, and the BIQU Glacier all changed nothing — and, decisively, why **the hottest
band of a temp tower also failed**: nozzle temperature cannot fix a gap.

**Fix (~20 min, on the printer console):**

```gcode
G28
TEMPERATURE_PROBE_CALIBRATE PROBE=btt_eddy TARGET=80 STEP=3
; let it run - it soaks the probe and samples as it climbs, then:
SAVE_CONFIG
```

Then re-verify: `compensation_enabled` must read `true` and
`estimated_expansion` must be non-zero once warm. Also raise
`max_validation_temp` in `[temperature_probe btt_eddy]` from `60.0` — the probe
will exceed that during an ABS print and Klipper will complain.

Afterwards, **re-run the bed mesh hot** (bed at 105 °C, soaked 15 min). The
current `default` mesh spans **0.304 mm** (dished: centre ~0.14, corners
0.36–0.44) and was probed cold, so it bakes the uncompensated error in:

```
min +0.131  max +0.435  range 0.304 mm   (15x15, bicubic, mesh 15,18 -> 335,335)
```

Only after that is it worth revisiting plate prep, enclosure or ASA-vs-ABS.

- [ ] P0: run `TEMPERATURE_PROBE_CALIBRATE`, `SAVE_CONFIG`, re-mesh hot, test print.
- [ ] P1: plate prep is still worth doing once (hot water + dish soap, not IPA —
      IPA smears mould release rather than removing it).
- [ ] P1: ASA over ABS for less warp; PETG covers many use cases and is far easier.
- [ ] P2: Ram3n graphite bed, chamber thermistor, insulation, exhaust into the
      AC Infinity 6". These help *later*; they were never the blocker.
- ⚠️ Safety: ABS/ASA emit styrene + UFPs. Enclosing concentrates them — vent
  outside or run activated carbon before sealing the chamber.

### J2. CAD / modelling capability gap
- [ ] P1: Sean cannot do meaningful 3D editing (customising others' models, or designing
      new). Fusion is too expensive. TinkerCAD is easy but limited. Currently learning
      Onshape (free tier is public-documents-only — flag that).
- [ ] P1: Live project with a deadline: **digital picture frame for his grandmother's
      birthday** — needs a different frame + touchscreen than the source model. He
      printed a modified version but it is "not close" to what is needed.
- [ ] P2: Evaluate free/cheap options honestly: Onshape (free = public), FreeCAD
      (capable, steep), Plasticity (cheap, not parametric), OpenSCAD (code-driven).

### J3. Print ecosystem / MCP
- [ ] P2: MCP integration for the print stack — Klipper/Moonraker, Mainsail/Fluidd,
      Spoolman, printguard. Would let filament, print state and failures surface
      alongside the rest of the estate.
- [ ] P2: Anycubic Kobra 2 (lightly modified) is offline. Deliberately deferred until
      ABS/ASA prints reliably on the SV08.

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
