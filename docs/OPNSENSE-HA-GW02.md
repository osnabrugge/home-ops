# OPNsense HA pair — gw01 + gw02 (pfsync / CARP)

Answers the question: _"shouldn't it be as easy as exporting the config from gw01
and then going through it to change the names... or do I need to manually setup
gw02 by hand and then use the config export/import to make sure the interface
names match for pfsync/carp to match?"_

## Short answer

**Neither.** Do **not** import gw01's config XML into gw02 blindly.

Inspect the existing **gw02 VM 200 on pve02** before creating or starting
anything. A stopped VM does not prove that its guest is installed, its NICs are
isolated or its addresses are unique. Record its disks, boot media, bridges,
VLANs and passthrough assignments, the current gw01 logical interfaces and a
checked configuration/VM rollback first. Apply only missing steps below; do not
recreate existing VMs or CARP VIPs.

The read-only baseline is not symmetric: gw01's LAN uses passed-through
`mce0/mce1` in `lagg0`, while VM 200 has two virtio NICs on pve02's `vmbr0`
(LAN bond) and `vmbr1` (the `enp1s0` uplink, observed without carrier).
The existing `vmbr2` sync bridge is not attached to VM 200. Its boot order points
at a 2521 MB secondary disk excluded from backup; the main disk is 100 GB.
No saved VM checkpoint was present. Do not infer guest installation or safe
startup from the VM name.

Do this instead:

1. If its inspected guest is not already installed, install OPNsense on gw02
   with the approved disk/rollback scope and isolated networking.
2. **Match logical assignment identifiers and roles**, mapping them to gw02's
   actual devices. Physical names may differ; per-node addresses must be unique.
3. Give gw02 its own IPs on every VLAN.
4. Configure pfsync + CARP on gw01, then let **OPNsense's built-in
   High Availability sync (XMLRPC)** push everything else to gw02 automatically.

The built-in HA sync is _designed_ for selected shared settings. Check the
running version's actual sync selections and CARP-priority behavior rather than
assuming every node-specific field is automatically omitted. Host identity,
per-node addresses, device mapping and the intended master/backup priority must
remain correct after every sync.

## Why NOT to import the config XML

Importing gw01's `config.xml` into gw02 gives you a **byte-identical twin**, which
in a CARP pair is actively harmful:

| Problem                                      | Consequence                                                                                                                                                          |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identical CARP VHIDs _and_ identical advskew | Both nodes claim MASTER → split brain, MAC conflicts, intermittent LAN outage                                                                                        |
| Identical interface IPs                      | Duplicate IP on every VLAN; the LAN will flap and you may lose access to both boxes at once                                                                          |
| Identical hostname                           | Sync logs, certs and RRD data become ambiguous                                                                                                                       |
| Uncontrolled WAN dialling                    | A copied WAN configuration can contend with the existing connection. Verify the actual handoff and provider/account session limits before allowing a second dialler. |
| Copied SSH host keys / GUI cert              | Both nodes present the same identity — you can't tell which one you're on                                                                                            |

You would then have to hand-edit ~everything the sync would have handled for you,
and hand-edit it _again_ on every future change.

## The interface-name concern — this is the real trap

You were right to worry about interface names. Here is the precise rule:

> pfsync and CARP do **not** care about interface _names_.
> The **HA config sync (XMLRPC)** absolutely does.

When gw01 syncs a firewall rule that references interface `opt3`, gw02 applies it
to _its_ `opt3`. If gw02's assignment order differs, that rule lands on the wrong
VLAN — silently. **This is how you end up with a rule you think is on VLAN 70
actually sitting on VLAN 99.**

### The complication specific to your setup

`gw01` is a **VM on pve01**, but virtualization alone does not establish its
current device names or whether a link uses virtio, PCI passthrough or a LAG.
The names and VLANs below are examples, not a verified current assignment map.

- If **gw02 uses virtio NICs**, map each vNIC/bridge/VLAN to the recorded logical
  role. Matching a device-name string is not proof that it reaches the same network.
- If **gw02 is bare metal** → names will be `igc0`, `ix0`, `em0`, etc. The
  _device_ names will never match, and that is fine — what must match is the
  **OPNsense logical assignment**: whatever becomes `WAN`, `LAN`, `OPT1`, `OPT2`…
  must map to the same physical network on both nodes, **in the same order**.

**Use the existing gw02 VM on pve02.** Match logical network roles to the actual
hardware rather than copying an assumed NIC layout. Keep the two hypervisors
independent unless a separate Proxmox quorum design is approved; firewall
CARP/pfsync does not require making them a two-node Corosync cluster.

## Build order (do it in this sequence)

### Phase 0 — record gw01's assignment map first

On gw01: **Interfaces → Assignments**. Confirm the current table before making
changes. The read-only baseline uses these logical identifiers, not an assumed
`WAN`/`LAN` assignment order:

```
opt1  -> pppoe0   ISP, parent vtnet0
opt2  -> vlan0.1  LAN, parent lagg0
opt3  -> vlan0.10 Trusted, parent lagg0
opt4  -> vlan0.42 Servers, parent lagg0
opt5  -> vlan0.50 Guests, parent lagg0
opt6  -> vlan0.70 IoT, parent lagg0
opt7  -> vlan0.99 Management, parent lagg0
opt10 -> vtnet1   pfsync
opt11 -> vtnet0   WAN transport
```

You will reproduce this **in the same order** on gw02. Order matters more than names.

### Phase 1 — build gw02, standalone

1. Install OPNsense on gw02. Same major version as gw01 (check
   **Firmware → Status**). Version skew breaks XMLRPC sync.
2. Build VLANs on the verified LAN parent. pve02 already has a host-side LAN
   bond; do not copy gw01's guest `mce0/mce1` LAG onto unrelated virtio NICs.
3. Assign interfaces to match the Phase 0 table.
4. Give gw02 **its own** IP on each VLAN (e.g. gw01 `.2`, gw02 `.3`, CARP VIP `.1`).
5. Set hostname `gw02`. **Do not configure PPPoE on gw02 yet.**
6. Confirm you can reach gw02's GUI on the management VLAN.

### Phase 2 — dedicated pfsync link

Give the pair a **direct, dedicated** interface for state sync (a verified isolated
VLAN or physical link between the two hosts). A private bridge on one hypervisor
does not connect to a private bridge on another by itself. Do **not** run
pfsync over a production VLAN — state traffic is chatty and unauthenticated.

- gw01 already declares `opt10`/`vtnet1` as `10.99.0.0/31`; sync is not enabled
  and peer/config-sync addresses are empty. Preserve that existing context and
  verify the intended isolated link and free peer address before configuration.
- Match the logical interface role on both nodes; do not substitute a new
  example subnet or `OPT` identifier blindly.
- Add a firewall rule on the SYNC interface: allow all from the SYNC subnet

### Phase 3 — CARP VIPs on gw01

**Interfaces → Virtual IPs**. Verify the existing VIPs and add only missing ones:

- Preserve existing VHIDs. They must be unique within a shared L2 domain;
  reuse across isolated VLANs is not itself a split-brain fault.
- Same password per VIP on both nodes
- `advskew`: **gw01 = 0** (master), **gw02 = 100** (backup)

Then repoint the LAN clients' default gateway to the **VIP**, not gw01's real IP.

### Phase 4 — enable HA sync

**System → High Availability → Settings**, on **gw01 only**:

- _Synchronize States_ = on, sync interface = SYNC
- _Synchronize Config to IP_ = `172.16.250.2` (gw02's SYNC IP)
- Username/password = gw02's admin
- Tick the services to replicate (rules, NAT, aliases, Unbound, DHCP, certs…)
- Verify the version's supported selections with a small, isolated test before
  broad replication. Preserve node-specific addresses, assignments and backup
  priority; do not depend on unverified checkbox names or manually repairing
  identity after each unattended sync.

On **gw02**: enable _Synchronize States_ + the same sync interface. **Do not** set
a "Synchronize Config to IP" on gw02 — config sync must be one-way (gw01 → gw02)
or you will get a sync loop.

Hit **Synchronize and reconfigure**. Verify on gw02 that rules/aliases appeared.

### Phase 5 — verify the actual WAN handoff

LAN CARP/pfsync does not prove WAN failover. Record the deployed WAN protocol,
addressing, ONU handoff and actual provider/account session limits before
configuring gw02's WAN. Do not infer a single-session policy from the ISP name.

If the handoff supports the addressing required by a CARP pair, verify that
design against the real service. If only one active PPPoE session is available,
the backup must not dial blindly: ownership transfer and session re-establishment
need an explicit, tested mechanism. CARP does not copy PPPoE session state.
Measure any outage rather than promising a generic failover time.

Until that contract is verified, label the result **LAN-only HA**, not complete
WAN HA. Do not change the working WAN or test failover without the approved
protected-network change and rollback.

## Verification checklist

```
# on both nodes
pfctl -s state | wc -l          # state counts should track each other
ifconfig pfsync0                # should show syncpeer + syncdev=SYNC iface
ifconfig | grep -A2 carp        # gw01 MASTER, gw02 BACKUP on every VLAN
```

Failover test (do this on purpose, during a maintenance window):

1. On gw01: **Interfaces → Virtual IPs → Status → Enter persistent CARP
   maintenance mode**
2. gw02 should flip to MASTER within ~3s; LAN traffic should continue
3. Long-lived SSH sessions should survive (proves pfsync is working)
4. Exit maintenance mode; gw01 reclaims MASTER

If SSH sessions _drop_ on failover, pfsync is not actually syncing states —
check the SYNC interface firewall rule.

## Common failure modes

| Symptom                                           | Cause                                                          |
| ------------------------------------------------- | -------------------------------------------------------------- |
| gw02 shows MASTER on some VLANs, BACKUP on others | advskew not set consistently, or VHID collision                |
| Both nodes MASTER                                 | CARP traffic blocked between nodes, or mismatched VIP password |
| Sync says success, rules missing on gw02          | Version skew between nodes                                     |
| Rules land on the wrong VLAN                      | Interface **assignment order** differs (Phase 0 not followed)  |
| WAN dies after failover test                      | PPPoE — see Phase 5                                            |

## TL;DR

- Do **not** import gw01's config XML.
- **Do** hand-assign gw02's interfaces to match gw01's _assignment order_.
- Let **HA sync (XMLRPC)** replicate the rest — that is its job.
- Make gw02 a **VM on pve02** so the virtio interface names match gw01.
- **WAN is a separate acceptance:** verify the actual handoff/session behavior
  before claiming complete HA; LAN state sync alone is not that proof.
