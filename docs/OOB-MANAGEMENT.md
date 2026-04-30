# Out-of-Band Management Guide

> **Scope:** Consolidated access and monitoring for all out-of-band infrastructure management systems.
> **Updated:** 2026-04-30

---

## Overview

This homelab has a comprehensive out-of-band (OOB) management infrastructure that enables remote access, power control, and monitoring even when the primary network or Kubernetes cluster is down.

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

| Port | Node | Type |
|------|------|------|
| 0 | nas01 | NAS |
| 1 | k8s01 | Control Plane |
| 2 | k8s02 | Control Plane |
| 3 | k8s03 | Control Plane |
| 4 | k8s04 | Worker |
| 5 | k8s05 | Worker |
| 6 | k8s06 | Worker |
| 7 | pi01 | Raspberry Pi |
| 8 | pi02 | ConsolePi |
| 9 | pi03 | ConsolePi |
| 10 | pi04 | Raspberry Pi |
| 11 | pve01 | Proxmox |
| 12 | fw01 | OPNsense |

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
| Outlet | Device | Purpose |
|--------|--------|---------|
| 1 | k8s01 | Control Plane Node |
| 2 | k8s02 | Control Plane Node |
| 3 | k8s03 | Control Plane Node |
| 4 | nas01 | NAS (PSU1) |
| 5 | core01-u1 | Core Switch U1 |
| 6 | fw01 | OPNsense Firewall |

**PDU02 (192.168.99.16):**
| Outlet | Device | Purpose |
|--------|--------|---------|
| 1 | k8s04 | Worker Node |
| 2 | k8s05 | Worker Node |
| 3 | k8s06 | Worker Node |
| 4 | nas01-psu2 | NAS (PSU2) |
| 5 | core01-u2 | Core Switch U2 |

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
# Check outlet status
snmpget -v 2c -c private 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1

# Power on outlet 1
snmpset -v 2c -c private 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1 integer 1

# Power off outlet 1
snmpset -v 2c -c private 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1 integer 2

# Reboot outlet 1
snmpset -v 2c -c private 192.168.99.15 .1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.1 integer 3
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
- **Dashboard ID:** 13524 (APC UPS)
- **URL:** https://grafana.homeops.ca/d/apc-ups
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

If UPS is on battery and runtime is limited:

```bash
# 1. Check estimated runtime
# (via Grafana UPS dashboard or SNMP)

# 2. If < 10 minutes, initiate graceful shutdown
kubectl drain k8s04 k8s05 k8s06 --ignore-daemonsets --delete-emptydir-data

# 3. Wait for workloads to drain (2-3 minutes)

# 4. Power off workers first
just infra pdu-off k8s04
just infra pdu-off k8s05
just infra pdu-off k8s06

# 5. Power off control plane (last)
just infra pdu-off k8s01
just infra pdu-off k8s02
just infra pdu-off k8s03
```

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
| Device | IP | MAC |
|--------|----|----|
| ups01 | 192.168.99.11 | (SNMP) |
| ups02 | 192.168.99.12 | (SNMP) |
| pdu01 | 192.168.99.15 | (SNMP) |
| pdu02 | 192.168.99.16 | (SNMP) |
| kvm01 | 192.168.99.51 | (HTTPS/API) |
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

**NUT (Network UPS Tools) Migration:**
- Move UPS monitoring from SNMP Exporter to dedicated NUT server
- Run `nut-server` in Kubernetes (DaemonSet or Deployment)
- Encrypted UPS protocol instead of SNMP
- Automatic shutdown orchestration on critical battery

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
