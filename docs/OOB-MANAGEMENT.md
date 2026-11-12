# Out-of-Band Management Guide

> **Scope:** Consolidated access and monitoring for all out-of-band infrastructure management systems.
> **Updated:** 2026-11-06

---

## Overview

This homelab has a comprehensive out-of-band (OOB) management infrastructure that enables remote access, power control, and monitoring even when the primary network or Kubernetes cluster is down.

The ConsolePi portions below describe the historical pi02/pi03 serial design,
not a currently available fallback: these boards are in pre-OS boot diagnostics
and reserved for the [isolated Pi lab](NETBOOT-PXE.md). PiKVM/TESmart console
access remains available; a replacement core-switch serial path has not been
commissioned. Do not rely on the old Pi-backed SSH serial entry points.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OOB Management Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   PiKVM      │  │     PDUs     │  │     UPS      │      │
│  │   (kvm01)    │  │  (pdu01/02)  │  │  (ups01/02)  │      │
│  │              │  │              │  │              │      │
│  │ • Video/KVM  │  │ • Power Ctrl │  │ • Battery    │      │
│  │ • Screenshot │  │ • SNMP       │  │ • Load Mon   │      │
│  │ • OCR        │  │ • Reboot     │  │ • SNMP       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │  ConsolePi   │  │   TESmart    │                         │
│  │  (pi02/03)   │  │  16-port KVM │                         │
│  │              │  │              │                         │
│  │ • Serial     │  │ • HDMI Sw    │                         │
│  │ • Core Sw    │  │ • GPIO       │                         │
│  └──────────────┘  └──────────────┘                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
    ┌─────────────┐     ┌──────────────┐    ┌──────────────┐
    │   Gatus     │     │  Prometheus  │    │   Grafana    │
    │ Status Page │     │   Metrics    │    │  Dashboards  │
    └─────────────┘     └──────────────┘    └──────────────┘
```

---

## Components

### 1. PiKVM (kvm01)

**Location:** Rack01 (U-mounted)
**IP:** kvm01.in.homeops.ca (192.168.99.51)
**Purpose:** Remote keyboard/video/mouse access to any server

#### Features

- **Remote KVM:** Full keyboard/video/mouse control over IP
- **Mass Storage:** Virtual USB drive mounting for ISO/recovery
- **GPIO Control:** Wake-on-LAN via GPIO outputs
- **TESmart Integration:** Automated HDMI port switching
- **Screenshot/OCR:** Capture and analyze screen output

#### Access Methods

##### Web UI

```bash
# Direct browser access
https://kvm01.in.homeops.ca

# Credentials in .private/pikvm.env
```

##### CLI (via scripts)

```bash
# Switch KVM to a specific node
just infra kvm-switch k8s01

# Take screenshot
just infra snapshot screenshot.jpg

# OCR text from screen
just infra ocr

# Send Wake-on-LAN
just infra wol k8s04

# Combined: switch + screenshot
just infra console k8s03
```

#### Node Mapping (TESmart Ports)

| Port | Node  | Type          |
| ---- | ----- | ------------- |
| 0    | nas01 | NAS           |
| 1    | k8s01 | Control Plane |
| 2    | k8s02 | Control Plane |
| 3    | k8s03 | Control Plane |
| 4    | k8s04 | Worker        |
| 5    | k8s05 | Worker        |
| 6    | k8s06 | Worker        |
| 7    | pi01  | Raspberry Pi  |
| 8    | pi02  | ConsolePi     |
| 9    | pi03  | ConsolePi     |
| 10   | pi04  | Raspberry Pi  |
| 11   | pve01 | Proxmox       |
| 12   | fw01  | OPNsense      |

#### Scripts

- **Main:** `/home/runner/work/home-ops/home-ops/scripts/infra-pikvm.sh`
- **Justfile:** `just infra kvm-*` recipes
- **API:** HTTPS with X-KVMD-User and X-KVMD-Passwd headers

---

### 2. PDUs (Power Distribution Units)

**Devices:**

- **pdu01:** 192.168.99.15 (CyberPower PDU41001)
- **pdu02:** 192.168.99.16 (CyberPower PDU41001)

**Purpose:** Remote power control via SNMP

#### Outlet Mapping

**PDU01 (192.168.99.15):**

| Outlet | Device    | Purpose            |
| ------ | --------- | ------------------ |
| 1      | k8s01     | Control Plane Node |
| 2      | k8s02     | Control Plane Node |
| 3      | k8s03     | Control Plane Node |
| 4      | nas01     | NAS (PSU1)         |
| 5      | core01-u1 | Core Switch U1     |
| 6      | fw01      | OPNsense Firewall  |

**PDU02 (192.168.99.16):**

| Outlet | Device     | Purpose        |
| ------ | ---------- | -------------- |
| 1      | k8s04      | Worker Node    |
| 2      | k8s05      | Worker Node    |
| 3      | k8s06      | Worker Node    |
| 4      | nas01-psu2 | NAS (PSU2)     |
| 5      | core01-u2  | Core Switch U2 |

#### Access Methods

##### CLI (Recommended)

```bash
# Power on a node
just infra pdu-on k8s05

# Power off a node (with confirmation)
just infra pdu-off k8s02

# Power cycle a node (with confirmation)
just infra pdu-reboot k8s03

# Check outlet status
just infra pdu-status k8s01

# Check all outlets
just infra pdu-status

# Hard reboot (PDU cycle + wait for boot)
just infra hard-reboot k8s04
```

##### SNMP Direct

```bash
# Load the configured community securely; do not put a literal secret in history.
: "${PDU_COMMUNITY:?Load the configured PDU community first}"

# Check outlet status
snmpget -v 2c -c "$PDU_COMMUNITY" 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1

# Power on outlet 1
snmpset -v 2c -c "$PDU_COMMUNITY" -r 0 -t 3 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1 integer 1

# Power off outlet 1
snmpset -v 2c -c "$PDU_COMMUNITY" -r 0 -t 3 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1 integer 2

# Reboot outlet 1
snmpset -v 2c -c "$PDU_COMMUNITY" -r 0 -t 3 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1 integer 3
```

**SNMP Values:**

- `1` = ON
- `2` = OFF
- `3` = REBOOT
- `4` = CANCEL

#### Scripts

- **Main:** `/home/runner/work/home-ops/home-ops/scripts/infra-pdu.sh`
- **Justfile:** `just infra pdu-*` recipes
- **SNMP OID:** `.1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.{outlet}`

#### Safety Features

- Confirmation prompts for power-off/reboot
- Visual warnings for destructive operations
- `gum` integration for better UX (falls back to read)
- No automatic retries of power writes; errors remain visible. A lost response
  can mean the command succeeded, so inspect outlet state and node boot identity
  before issuing another command.

An ON command restores outlet power; it does not press the computer's ATX power
button. Verify the actual BIOS **After Power Loss** setting and a working wake-up
path before shutting a node down. A configured WoL channel alone is insufficient:
its MAC, physical link, and firmware wake support must match the target.

With **Last State**, a gracefully powered-off machine can remain off when AC
returns. For a required cold cycle without a separate power-on path, first drain
workloads normally and enter the actual firmware setup screen through a graceful
reboot. This leaves filesystems quiescent and the machine powered on, so Last State
can restore that state after the outlet cycle. Do not change BIOS settings or
guess which outlet to switch; verify the exact cable/outlet in NetBox and leave
other outlets and banks untouched.

---

### 3. UPS (Uninterruptible Power Supply)

**Devices:**

- **ups01:** 192.168.99.11
- **ups02:** 192.168.99.12

**Purpose:** Battery backup and power quality monitoring

#### Monitoring

##### SNMP Metrics

Monitored via SNMP Exporter in Kubernetes:

```yaml
Targets:
    - ups01 (192.168.99.11)
    - ups02 (192.168.99.12)

Key Metrics:
    - upsBasicBatteryTimeOnBattery_seconds - Time running on battery
    - upsAdvBattery_needsreplacing - Battery replacement flag
    - upsAdvOutputActivePower - Current power output (watts)
    - upsAdvBatteryCapacity - Battery charge level (%)
    - upsAdvConfigRatedOutputPower - Max rated power
```

##### Alerts

- **UPSOnBattery** (critical): UPS running on battery > 60 seconds
- **UPSReplaceBattery** (critical): Battery needs replacement
- **UPSUnreachable** (warning): SNMP monitoring unavailable
- **UPSLowBattery** (warning): Battery capacity < 50%
- **UPSHighLoad** (warning): Load > 80% of rated capacity

##### Grafana Dashboard

- **Dashboard ID:** 13524 (CyberPower UPS)
- **URL:** https://grafana.com/api/dashboards/21605/revisions/2/download
- **Data:** Live metrics from Prometheus

##### Power Usage Badge

Current cluster power consumption is exposed via Kromgo:

```yaml
Metric: cluster_power_usage
Query: avg(upsAdvOutputActivePower)
Colors:
    - Green: 0-400w
    - Orange: 401-750w
    - Red: 751-9999w
```

---

### 4. ConsolePi (Serial Console)

**Devices:**

- **pi02:** 192.168.42.22 (→ Core01-U1 serial)
- **pi03:** 192.168.42.23 (→ Core01-U2 serial)

**Purpose:** Serial console access to core network switches

#### Access

```bash
# SSH to ConsolePi
ssh pi@192.168.42.22

# Connect to switch serial console
# (USB-to-serial adapters auto-detected by ConsolePi)
screen /dev/ttyUSB0 9600

# Or use ConsolePi menu
consolepi-menu
```

#### Connected Devices

- **pi02 → Core01-U1:** Primary core switch (Brocade ICX 6610-48P)
- **pi03 → Core01-U2:** Secondary core switch (Brocade ICX 6610-48P stack member)

#### Use Cases

- Initial switch configuration
- Recovery from network misconfigurations
- Firmware updates
- Stack management troubleshooting
- Emergency access when network is down

---

## Unified Monitoring

### Gatus Status Page

All OOB devices are monitored on the unified status page:

**URL:** https://status.homeops.ca

**OOB Management Group:**

- PiKVM (kvm01) - HTTPS health check
- PDU01 - TCP connect to SNMP port (161)
- PDU02 - TCP connect to SNMP port (161)
- UPS01 - TCP connect to SNMP port (161)
- UPS02 - TCP connect to SNMP port (161)
- ConsolePi (pi02) - TCP connect to SSH (22)
- ConsolePi (pi03) - TCP connect to SSH (22)

**Check Intervals:**

- PiKVM: 1 minute
- PDUs/UPS: 2 minutes
- ConsolePi: 2 minutes

### Blackbox Exporter (ICMP)

LAN connectivity probes monitor OOB devices via ICMP:

```yaml
Targets:
    - kvm01.in.homeops.ca
    - pdu01.in.homeops.ca
    - pdu02.in.homeops.ca
    - ups01.in.homeops.ca
    - ups02.in.homeops.ca
```

### Prometheus & Alertmanager

**Metrics Collection:**

- SNMP Exporter → PDU/UPS SNMP data
- Blackbox Exporter → ICMP reachability
- Gatus → HTTP/TCP endpoint health

**Alert Rules:**

- PDU/UPS unreachability
- UPS battery status
- UPS on battery power
- UPS high load

**Alertmanager URL:** https://alertmanager.homeops.ca

### Proxmox exporter lifecycle and account setup

- The existing `sh.brew.node_exporter.service` is a user service. Keep it enabled
  and enable linger for its existing owner with `sudo loginctl enable-linger
  <service-owner>`. Verify Prometheus remains up after the SSH session closes;
  testing only during login can hide a nonpersistent exporter.
- `openibd` is the legacy OFED/DOCA loader name for Mellanox Ethernet/RDMA as
  well as InfiniBand. On pve01 both ConnectX-4 LX functions are bound to
  `vfio-pci` and passed to gw01, so there is no host HCA for it to initialize.
  Keep the unused host boot loader disabled; do not run its stop/restart
  actions, unload drivers, or rebind devices on the running firewall host.
  Re-enable only as part of a reviewed change returning a NIC to the host.
- The read-only `monitoring` PVE role contains
  `Datastore.Audit,SDN.Audit,Sys.Audit,VM.Audit`. The existing account is
  `monitoring@pve`, with the `monitoring` token inheriting that bounded role.
  It does not need a Linux/PAM account or administrator privileges.

On another independent PVE host, first inspect existing users/roles/tokens to
avoid duplicates. If the role is missing, create it, then create the account
and token:

```bash
pveum role add monitoring --privs 'Datastore.Audit SDN.Audit Sys.Audit VM.Audit'
pveum user add monitoring@pve --comment 'Read-only Prometheus monitoring'
pveum acl modify / --users monitoring@pve --roles monitoring
pveum user token add monitoring@pve monitoring --privsep 0
```

The token command prints its secret once. Keep it in the existing protected
exporter configuration/secret store, never in Git or chat. In exporter YAML,
`user` is `monitoring@pve` and `token_name` is only `monitoring`, not the complete
`monitoring@pve!monitoring` identifier. A role existing by itself does not create
the user or token. `--privsep 0` inherits only the read-only user role; if using
`--privsep 1`, explicitly grant the same role to the token too.

#### One exporter, two standalone hosts

The Kubernetes exporter reads a Secret-mounted `/etc/prometheus/pve.yml` with
two named authentication modules, `pve01` and `pve02`. ExternalSecrets renders
each module from that host's own approved token in Key Vault
`pve-exporter-hosts`, using `PVE01_USER`, `PVE01_TOKEN_NAME`,
`PVE01_TOKEN_VALUE` and the corresponding `PVE02_` fields.
These dedicated exporter tokens were imported privately from each host's
`/etc/prometheus/pve.yml`, not substituted from the MCP/PDM integration.
Token values never belong in the HelmRelease.
TLS verification remains enabled for each module.

The HelmRelease's ServiceMonitor has two endpoints:

- `/pve?module=pve01&target=pve01.in.homeops.ca:8006`
- `/pve?module=pve02&target=pve02.in.homeops.ca:8006`

Each endpoint uses **target relabeling** to set `instance` to its host name.
This keeps both exported metrics and Prometheus's generated `up` series
distinct; metric relabeling alone does not affect `up`.

Do not also inject `PVE_USER` or `PVE_USER_FILE`: exporter 3.11.0 switches to
single-module environment authentication when either is present, instead of
loading the multi-module file. Secret updates trigger a stateless rollout.
Verify both real `/pve` scrapes and both Prometheus targets after changing it.

These are independent API connections. No Proxmox cluster or Corosync quorum
is involved. A future HA cluster needs a separately reviewed quorum design,
normally a third node or a supported external QDevice for two nodes; monitoring
does not create that design or change the hosts.

---

## Common Workflows

### Emergency Server Access (Complete Failure)

If the server is completely unresponsive:

```bash
# 1. Switch KVM to the server
just infra kvm-switch k8s04

# 2. Check screen output (via PiKVM web UI or screenshot)
just infra snapshot

# 3. If hung/frozen, hard reboot via PDU
just infra hard-reboot k8s04

# 4. Monitor boot via KVM
# (screen updates visible in PiKVM web UI)
```

### Network Switch Recovery

If network is down and you need switch console:

```bash
# 1. SSH to ConsolePi
ssh pi@192.168.42.22

# 2. Connect to serial console
screen /dev/ttyUSB0 9600

# 3. Access switch CLI
# (usually auto-connects, or press Enter)
```

### Power Monitoring During Outage

```bash
# Check if UPS is on battery
curl -sk https://prometheus.homeops.ca/api/v1/query?query=upsBasicBatteryTimeOnBattery_seconds | jq

# Check current power draw
curl -sk https://prometheus.homeops.ca/api/v1/query?query=upsAdvOutputActivePower | jq

# Check battery capacity
curl -sk https://prometheus.homeops.ca/api/v1/query?query=upsAdvBatteryCapacity | jq
```

### Graceful Cluster Shutdown (Extended Outage)

Do not use PDU outlet cuts as an orderly shutdown procedure, or spend a short
UPS budget repeatedly draining Ceph nodes. Talos needs its authenticated shutdown
API; a NUT process inside Kubernetes cannot halt its Talos host.

The off-cluster implementation is under [infrastructure/power](../infrastructure/power/),
with the bounded observer/sequencer in [ups_shutdown.py](../scripts/ups_shutdown.py).
NAS01 hosts a separate pinned, server-only NUT Compose project on
`127.0.0.1:3493`. It polls both existing UPS cards; it runs no `upsmon`, has no
NUT command users, and never invokes driver shutdown. Existing SNMP dashboards
remain in place. The approved SNMP credential is provisioned only into private
host configuration, not the example in Git.

Its host file is `/mnt/local/apps/homeops-power/compose.nut.yaml`, not the main
`/mnt/local/docker-compose.yml`. The separate project avoids changing Garage,
Zot and the existing exporters. Its source is version-controlled here, but the
host deployment is not Flux-reconciled; these are different guarantees.

An in-cluster NUT server and exporter are valid monitoring deployments. Their
placement does not itself provide orderly Talos shutdown. The current observer
uses an independent local server so it retains UPS state while the cluster is
unavailable. The shutdown actuator is kept outside the cluster for that
failure-domain reason, not because NUT can never run in Kubernetes. Adding
GitOps-managed NUT monitoring must preserve this independent outage path and
must not introduce USB privilege or a second shutdown authority unnecessarily.

GitOps now also declares a separate, read-only `network-ups-tools` monitoring
pod with a NUT server and `nut_exporter`. It polls the two cards through their
existing read-only SNMP identity; it does not depend on exposing NAS01's
loopback listener. Only exporter port 9199 is a Service, and Prometheus scrapes
each UPS separately. The [NUT dashboard](https://grafana.homeops.ca/d/nut-ups)
shows live UPS status, charge, runtime, load and voltage. It is not an actuator
or an armed-state dashboard. The independent NAS01 observer remains unchanged.
There is no `upsmon`, NUT command user, FSD action or power-cut hook in this
monitoring workload.

Drivers are started independently: an unreachable card must not prevent the
other UPS or `upsd` from serving telemetry. Availability probes test the server,
not the conjunction of every UPS feed. Each exporter scrape still reports its
own feed's failure; do not turn an unreachable UPS into a healthy zero reading
or silence its independent SNMP/ICMP alarms to make the dashboard green.

The unarmed `homeops-ups-watch.service` is linked from the persistent deployment
directory. A TrueNAS `POSTINIT` command re-links and starts that same observer
after boot; it does not contain `--execute`. This startup record, not a bare
custom unit under the appliance's OS filesystem, is the persistence mechanism.
No reboot has been performed to certify a real post-upgrade startup.

**A running NUT server is not armed power protection.** The observer is
read-only unless `--execute` and a separate root-owned, mode-0600 approval file
matching the exact policy hash are supplied. The example deliberately leaves
host finalizers unapproved and Talos/Kubernetes credential paths unprovisioned.
Do not enable TrueNAS's unconfigured native UPS service with its default
30-second local-shutdown timer as a shortcut.

Read-only observation on NAS01:

```bash
sudo python3 /mnt/local/apps/homeops-power/scripts/ups_shutdown.py watch \
  --config /mnt/local/apps/homeops-power/private/ups-policy.json \
  --state /mnt/local/apps/homeops-power/private/ups-state.json --once
```

The proposed actuator budgets six minutes for quiescing applications, requesting
parallel worker shutdowns, then control-plane shutdowns, and finally the NAS and
hypervisor hosts. It takes the minimum reported UPS runtime, never an average.
Network gear is not powered off by this implementation. It snapshots original
replica/suspension state and its ownership of Ceph `noout` before mutations,
records actions before sending them, and requires explicit healthy recovery
before restoring state. A timeout is unconfirmed, not successful.

Before arming, approve the actual identities and native host shutdown bounds,
UPS policy, independent credential placement and recovery procedure. In
particular, the example treats a 45-second telemetry loss as a shutdown reason;
that availability-versus-data-safety policy needs explicit review, not accidental
activation during a NUT upgrade. `OL RB` alone does not trigger an outage action.
No outage, FSD, outlet, host-shutdown or recovery actuator test is implied by the
synthetic regression suite.

Server-only rollback stops just Compose project `homeops-power`; it does not
stop Docker, alter existing containers, erase its private state, or change UPS
settings. Remove an observer startup entry separately before reversing it.
Stop `homeops-ups-watch.service`, disable only the matching
`Home-ops UPS observer (unarmed)` native startup record, and retain its journal
before removing the unit link. Never run `systemctl stop docker` as rollback.

### Firmware/BIOS Update via KVM

```bash
# 1. Switch to the target node
just infra kvm-switch k8s02

# 2. Access PiKVM web UI
# https://kvm01.in.homeops.ca

# 3. Mount ISO via Mass Storage Device
# (Upload ISO in PiKVM web UI → Drive menu)

# 4. Reboot into BIOS/UEFI
just infra pdu-reboot k8s02

# 5. Use KVM to control BIOS/boot menu
# (Full keyboard/mouse via web UI)
```

---

## Network Architecture

### Management VLAN

All OOB devices reside on VLAN 99 (Management):

**Subnet:** 192.168.99.0/24
**Gateway:** 192.168.99.4 (Brocade Core01)

**OOB Device IPs:**

| Device  | IP            | MAC              |
| ------- | ------------- | ---------------- |
| ups01   | 192.168.99.11 | (SNMP)           |
| ups02   | 192.168.99.12 | (SNMP)           |
| pdu01   | 192.168.99.15 | (SNMP)           |
| pdu02   | 192.168.99.16 | (SNMP)           |
| kvm01   | 192.168.99.51 | (HTTPS/API)      |
| tesmart | 192.168.99.92 | (GPIO via PiKVM) |

**Note:** ConsolePi devices (pi02/pi03) are on Server VLAN (192.168.42.0/24) for direct SSH access.

### DNS Resolution

```bash
# Internal DNS (Unbound on fw01)
kvm01.in.homeops.ca → 192.168.99.51
pdu01.in.homeops.ca → 192.168.99.15
pdu02.in.homeops.ca → 192.168.99.16
ups01.in.homeops.ca → 192.168.99.11
ups02.in.homeops.ca → 192.168.99.12
```

### Firewall Rules

Management VLAN (99) is accessible from:

- Server VLAN (42) - for Kubernetes SNMP monitoring
- Workstation VLAN (10) - for admin access

**fw01 (OPNsense) rules:**

- Allow Server → Management (SNMP, HTTPS, SSH)
- Allow Workstation → Management (all)
- Deny all other inbound to Management

---

## Security Considerations

### Authentication

**PiKVM:**

- Username: admin
- Password: Stored in `.private/pikvm.env` (gitignored)
- HTTPS only (self-signed cert, `insecure: true` in Gatus)

**PDUs:**

- SNMP Community: Stored in `.private/cyberpower.env` or `PDU_COMMUNITY` env var
- Default: "private" (should be changed in production)
- SNMPv2c (plaintext - network isolation is critical)

**ConsolePi:**

- SSH key-based authentication
- User: pi
- Direct serial access (no password on serial console)

### Network Isolation

- Management VLAN is firewalled from Guest and IoT VLANs
- PDU/UPS use SNMPv2c (no encryption) - trust boundary at VLAN edge
- PiKVM uses HTTPS but self-signed cert
- Serial console has no authentication (physical security critical)

### Access Control Recommendations

1. **PiKVM:** Integrate with centralized auth (LDAP/SSO) when #3064 is implemented
2. **PDUs:** Upgrade to SNMPv3 with authentication/encryption
3. **UPS:** Consider moving to NUT (Network UPS Tools) in Kubernetes for encrypted monitoring
4. **ConsolePi:** Use bastion/jump host for access, disable direct SSH from untrusted VLANs

---

## Troubleshooting

### PiKVM Unreachable

```bash
# 1. Check network connectivity
ping kvm01.in.homeops.ca

# 2. Check if PiKVM is powered
# (should be on UPS with auto-start on power restore)

# 3. Check switch port
# (Management VLAN 99 tagged on appropriate port)

# 4. Physical access to PiKVM
# (HDMI output shows local console)
```

### PDU SNMP Not Responding

```bash
# 1. Test SNMP connectivity
snmpget -v 2c -c private pdu01.in.homeops.ca .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1

# 2. Verify PDU is powered
# (check UPS dashboard for outlet status)

# 3. Check PDU management IP config
# (may need factory reset via physical button)

# 4. Verify SNMP community string
# (check .private/cyberpower.env)
```

### UPS Metrics Missing

```bash
# 1. Check SNMP Exporter pod
kubectl get pods -n observability -l app.kubernetes.io/name=snmp-exporter

# 2. Check ServiceMonitor targets
kubectl get servicemonitor -n observability snmp-exporter -o yaml

# 3. Check Prometheus targets
# https://prometheus.homeops.ca/targets
# (look for snmp-exporter jobs)

# 4. Manual SNMP test
snmpwalk -v 2c -c public_v2 ups01.in.homeops.ca .1.3.6.1.4.1.318.1.1.1
```

### ConsolePi Not Accessible

```bash
# 1. Check SSH connectivity
ssh -v pi@192.168.42.22

# 2. Check if ConsolePi is running
# (should auto-start on power, check via PiKVM if needed)

# 3. Verify USB-to-serial adapter detected
# (should appear as /dev/ttyUSB0 on ConsolePi)

# 4. Check switch serial cable
# (RJ45 to DB9 console cable properly connected)
```

---

## Future Improvements

### Planned (Dependencies)

- **#3054:** VLAN interfaces for OOB network access
    - Add bond0.99 interfaces on Talos nodes for direct Management VLAN access
    - Enable node-level access to PDU/UPS without routing through fw01

- **#3064:** Centralized authentication
    - Integrate PiKVM with SSO (Authelia/LLDAP)
    - Standardize credentials across all OOB devices
    - MFA for privileged operations (power control, console access)

### Under Consideration

**NUT (Network UPS Tools) and outage protection:**

- Keep existing SNMP monitoring; use the off-cluster NUT server for outage state.
- Keep the shutdown observer outside the cluster it must eventually shut down.
- The current NUT socket is host-loopback only. NUT does not magically encrypt
  the underlying SNMPv2 link; do not describe it as an encryption upgrade.
- Automatic shutdown remains a separately approved, tested and armed capability.

**PDU Monitoring Enhancement:**

- Per-outlet power monitoring (if PDUs support it)
- Outlet-level alerts (individual outlet failures)
- Power usage trending per device

**Serial Console Aggregation:**

- Consolidate ConsolePi functionality into single device or cluster-based solution
- Serial-over-IP for all critical infrastructure (switches, firewall, NAS)

**Automated Recovery Workflows:**

- Health check → Auto-remediation via PDU reboot
- Integration with Alertmanager for power cycling failed nodes
- Safe guards: backoff, max retries, manual approval gates

**Web Dashboard:**

- Unified web UI for all OOB operations (KVM, power, serial)
- Alternative to vendor-specific UIs (PiKVM, PDU web interfaces)
- Audit logging for all OOB actions

---

## Related Documentation

- [REBUILD-RUNBOOK.md](./REBUILD-RUNBOOK.md) - Talos cluster rebuild procedures
- [README.md](../README.md) - Overall homelab architecture
- [scripts/infra-pikvm.sh](../scripts/infra-pikvm.sh) - PiKVM control script
- [scripts/infra-pdu.sh](../scripts/infra-pdu.sh) - PDU control script
- [infra/mod.just](../infra/mod.just) - Justfile recipes for OOB operations

---

## Quick Reference Card

### Power Control

```bash
just infra pdu-status              # Check all PDU outlets
just infra pdu-on <node>           # Power on
just infra pdu-off <node>          # Power off (DANGEROUS)
just infra pdu-reboot <node>       # Power cycle
just infra hard-reboot <node>      # PDU reboot + wait
```

### KVM Access

```bash
just infra kvm-switch <node>       # Switch HDMI
just infra wol <node>              # Wake-on-LAN
just infra snapshot [file]         # Screenshot
just infra ocr                     # OCR screen text
just infra console <node>          # Switch + screenshot
```

### Serial Console

```bash
ssh pi@192.168.42.22               # ConsolePi (Core01-U1)
ssh pi@192.168.42.23               # ConsolePi (Core01-U2)
screen /dev/ttyUSB0 9600           # Serial session
```

### Monitoring

```bash
https://status.homeops.ca          # Gatus unified status
https://grafana.homeops.ca/d/apc-ups # UPS dashboard
https://prometheus.homeops.ca/targets # SNMP targets
https://alertmanager.homeops.ca    # Active alerts
```

---

**Last Updated:** 2026-04-30
**Maintainer:** @osnabrugge
**Related Issues:** #3054 (VLAN), #3064 (Auth), Current issue (Consolidation)
