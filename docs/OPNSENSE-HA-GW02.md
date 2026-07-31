# OPNsense HA pair — gw01 + gw02 (pfsync / CARP)

Answers the question: *"shouldn't it be as easy as exporting the config from gw01
and then going through it to change the names... or do I need to manually setup
gw02 by hand and then use the config export/import to make sure the interface
names match for pfsync/carp to match?"*

## Short answer

**Neither.** Do **not** import gw01's config XML into gw02.

Do this instead:
1. Install OPNsense on gw02 **by hand** (minimal — just enough to reach the GUI).
2. **Assign interfaces by hand** so the *interface names* match gw01
   (`vtnet0`→WAN, `vtnet1`→LAN, etc. — names must match, IPs must NOT).
3. Give gw02 its own IPs on every VLAN.
4. Configure pfsync + CARP on gw01, then let **OPNsense's built-in
   High Availability sync (XMLRPC)** push everything else to gw02 automatically.

The built-in HA sync is *designed* for this. It replicates firewall rules, NAT,
aliases, DHCP, Unbound, certificates, users — but deliberately **skips** the
per-node bits (interface IPs, hostname, CARP VHIDs). That is exactly the
"go through it and change the names" work you were trying to do manually.

## Why NOT to import the config XML

Importing gw01's `config.xml` into gw02 gives you a **byte-identical twin**, which
in a CARP pair is actively harmful:

| Problem | Consequence |
|---|---|
| Identical CARP VHIDs *and* identical advskew | Both nodes claim MASTER → split brain, MAC conflicts, intermittent LAN outage |
| Identical interface IPs | Duplicate IP on every VLAN; the LAN will flap and you may lose access to both boxes at once |
| Identical hostname | Sync logs, certs and RRD data become ambiguous |
| Duplicate PPPoE session | **Bell will only honour one PPPoE session.** Two nodes dialling with the same credentials = WAN drops. This is the one that will bite you hardest. |
| Copied SSH host keys / GUI cert | Both nodes present the same identity — you can't tell which one you're on |

You would then have to hand-edit ~everything the sync would have handled for you,
and hand-edit it *again* on every future change.

## The interface-name concern — this is the real trap

You were right to worry about interface names. Here is the precise rule:

> pfsync and CARP do **not** care about interface *names*.
> The **HA config sync (XMLRPC)** absolutely does.

When gw01 syncs a firewall rule that references interface `opt3`, gw02 applies it
to *its* `opt3`. If gw02's assignment order differs, that rule lands on the wrong
VLAN — silently. **This is how you end up with a rule you think is on VLAN 70
actually sitting on VLAN 99.**

### The complication specific to your setup

`gw01` is a **VM on pve01 with virtio NICs** (`vtnet0`, `vtnet1`, `vtnet2` +
`lagg0` + VLANs 1/10/42/50/70/99).

- If **gw02 is also a VM on pve02 with virtio NICs** → names will be `vtnet0..2`
  as well. Easy. Just attach the vNICs to the bridges in the same order.
- If **gw02 is bare metal** → names will be `igc0`, `ix0`, `em0`, etc. The
  *device* names will never match, and that is fine — what must match is the
  **OPNsense logical assignment**: whatever becomes `WAN`, `LAN`, `OPT1`, `OPT2`…
  must map to the same physical network on both nodes, **in the same order**.

**Recommendation: make gw02 a VM on pve02, mirroring gw01.** It keeps the
interface naming identical, makes the lagg/VLAN stack a copy-paste, and lets you
snapshot/rollback the node during setup.

## Build order (do it in this sequence)

### Phase 0 — record gw01's assignment map first
On gw01: **Interfaces → Assignments**. Write down the exact table, e.g.

```
WAN   -> pppoe0  (parent vtnet0)
LAN   -> vlan42  (parent lagg0)
OPT1  -> vlan10
OPT2  -> vlan50
OPT3  -> vlan70
OPT4  -> vlan99
```
You will reproduce this **in the same order** on gw02. Order matters more than names.

### Phase 1 — build gw02, standalone
1. Install OPNsense on gw02. Same major version as gw01 (check
   **Firmware → Status**). Version skew breaks XMLRPC sync.
2. Create `lagg0` and the VLAN interfaces exactly as on gw01.
3. Assign interfaces to match the Phase 0 table.
4. Give gw02 **its own** IP on each VLAN (e.g. gw01 `.2`, gw02 `.3`, CARP VIP `.1`).
5. Set hostname `gw02`. **Do not configure PPPoE on gw02 yet.**
6. Confirm you can reach gw02's GUI on the management VLAN.

### Phase 2 — dedicated pfsync link
Give the pair a **direct, dedicated** interface for state sync (a back-to-back
vNIC on a private pve bridge, or a real crossover if bare metal). Do **not** run
pfsync over a production VLAN — state traffic is chatty and unauthenticated.

- gw01: `172.16.250.1/30`, gw02: `172.16.250.2/30`
- Interface name must match on both nodes (e.g. both `OPT5` / `SYNC`)
- Add a firewall rule on the SYNC interface: allow all from the SYNC subnet

### Phase 3 — CARP VIPs on gw01
**Interfaces → Virtual IPs**. For each VLAN create a CARP VIP:
- Unique **VHID per VLAN** (do not reuse a VHID across interfaces on the same L2)
- Same password per VIP on both nodes
- `advskew`: **gw01 = 0** (master), **gw02 = 100** (backup)

Then repoint the LAN clients' default gateway to the **VIP**, not gw01's real IP.

### Phase 4 — enable HA sync
**System → High Availability → Settings**, on **gw01 only**:
- *Synchronize States* = on, sync interface = SYNC
- *Synchronize Config to IP* = `172.16.250.2` (gw02's SYNC IP)
- Username/password = gw02's admin
- Tick the services to replicate (rules, NAT, aliases, Unbound, DHCP, certs…)
- **Leave "Interfaces" and "Virtual IPs" unticked** if you want to keep advskew
  divergent — otherwise re-set advskew on gw02 after each sync.

On **gw02**: enable *Synchronize States* + the same sync interface. **Do not** set
a "Synchronize Config to IP" on gw02 — config sync must be one-way (gw01 → gw02)
or you will get a sync loop.

Hit **Synchronize and reconfigure**. Verify on gw02 that rules/aliases appeared.

### Phase 5 — the PPPoE problem (read this before you fail over)
Bell's PPPoE session is **single-session**. A classic CARP WAN failover assumes
both nodes can hold a WAN address. With PPPoE they cannot both dial.

Options, in order of preference:
1. **Bridge the ONU to a CARP'd WAN segment** — put the ONU on a small L2 segment
   both nodes reach, CARP the WAN side, and only the MASTER runs the PPPoE
   client. Failover = gw02 becomes MASTER and dials. Expect **30–90s of WAN
   downtime** while the session re-establishes (Bell must time out the old one).
2. **Accept LAN-only HA** — HA covers gw01 dying as a *router/firewall*, and you
   manually move WAN on a real failure. Simplest, and honestly fine for a home
   lab, but it is not true HA.

> There is no configuration that makes PPPoE failover instant. This is a Bell
> constraint, not an OPNsense one. Worth knowing **before** you build the pair.

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

If SSH sessions *drop* on failover, pfsync is not actually syncing states —
check the SYNC interface firewall rule.

## Common failure modes

| Symptom | Cause |
|---|---|
| gw02 shows MASTER on some VLANs, BACKUP on others | advskew not set consistently, or VHID collision |
| Both nodes MASTER | CARP traffic blocked between nodes, or mismatched VIP password |
| Sync says success, rules missing on gw02 | Version skew between nodes |
| Rules land on the wrong VLAN | Interface **assignment order** differs (Phase 0 not followed) |
| WAN dies after failover test | PPPoE — see Phase 5 |

## TL;DR

- Do **not** import gw01's config XML.
- **Do** hand-assign gw02's interfaces to match gw01's *assignment order*.
- Let **HA sync (XMLRPC)** replicate the rest — that is its job.
- Make gw02 a **VM on pve02** so the virtio interface names match gw01.
- **PPPoE is the gotcha:** WAN failover will not be seamless. Decide now whether
  you want true WAN HA or LAN-only HA.
