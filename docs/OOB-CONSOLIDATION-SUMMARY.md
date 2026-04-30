# OOB Management Consolidation Summary

**Issue:** osnabrugge/home-ops#[ISSUE_NUMBER]
**Date:** 2026-04-30
**Status:** Initial implementation complete

---

## Changes Made

### 1. Unified Monitoring Dashboard (Gatus)

Added comprehensive OOB management monitoring to Gatus status page at `https://status.homeops.ca`:

**New "oob-management" Group Endpoints:**
- PiKVM (kvm01) - HTTPS health check @ 1min interval
- PDU01 - TCP connect to SNMP (port 161) @ 2min interval
- PDU02 - TCP connect to SNMP (port 161) @ 2min interval
- UPS01 - TCP connect to SNMP (port 161) @ 2min interval
- UPS02 - TCP connect to SNMP (port 161) @ 2min interval
- ConsolePi (pi02) - TCP connect to SSH (port 22) @ 2min interval
- ConsolePi (pi03) - TCP connect to SSH (port 22) @ 2min interval

**File:** `kubernetes/apps/observability/gatus/app/resources/config.yaml`

### 2. Enhanced Prometheus Alerting

Added new alert rules for comprehensive OOB infrastructure monitoring:

**New Alerts:**
- `PDUUnreachable` - PDU SNMP monitoring down (warning, 5min)
- `UPSUnreachable` - UPS SNMP monitoring down (warning, 5min)
- `UPSLowBattery` - Battery capacity < 50% (warning, 10min)
- `UPSHighLoad` - UPS load > 80% capacity (warning, 15min)

**Existing Alerts (preserved):**
- `UPSOnBattery` - UPS on battery > 60 seconds (critical, 5min)
- `UPSReplaceBattery` - Battery replacement needed (critical, 5min)

**File:** `kubernetes/apps/observability/snmp-exporter/app/prometheusrule.yaml`

### 3. Comprehensive Documentation

Created detailed OOB management guide with:

- Complete architecture overview and component diagrams
- Detailed documentation for each OOB system:
  - PiKVM + TESmart KVM switch
  - PDU (power control)
  - UPS (battery monitoring)
  - ConsolePi (serial console)
- Access methods (CLI scripts, API, web UI)
- Network architecture and IP mappings
- Common operational workflows
- Troubleshooting guides
- Security considerations
- Future improvement roadmap

**File:** `docs/OOB-MANAGEMENT.md`

### 4. README Updates

Enhanced README.md with:
- Added UPS monitoring to OOB management table
- Link to comprehensive OOB management guide
- Better description of OOB capabilities

**File:** `README.md`

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OOB Management Stack                      │
├─────────────────────────────────────────────────────────────┤
│  PiKVM (kvm01)    │    PDUs (pdu01/02)   │   UPS (ups01/02) │
│  • Remote KVM     │    • Power Control   │   • Battery Mon  │
│  • Screenshots    │    • SNMP Management │   • Load Monitor │
│                   │                      │                  │
│  ConsolePi (pi02/03)  │  TESmart 16-port KVM Switch        │
│  • Serial Console     │  • HDMI Switching via GPIO         │
└─────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
    ┌─────────────┐     ┌──────────────┐    ┌──────────────┐
    │   Gatus     │     │  Prometheus  │    │   Grafana    │
    │ Status Page │     │   Metrics    │    │  Dashboards  │
    └─────────────┘     └──────────────┘    └──────────────┘
```

### Monitoring Coverage

| Device | Gatus Health | Blackbox ICMP | SNMP Metrics | Prometheus Alerts |
|--------|--------------|---------------|--------------|-------------------|
| PiKVM (kvm01) | ✅ HTTPS | ✅ | ❌ | ❌ |
| PDU01 | ✅ TCP:161 | ✅ | ✅ | ✅ |
| PDU02 | ✅ TCP:161 | ✅ | ✅ | ✅ |
| UPS01 | ✅ TCP:161 | ✅ | ✅ | ✅ |
| UPS02 | ✅ TCP:161 | ✅ | ✅ | ✅ |
| ConsolePi (pi02) | ✅ TCP:22 | ❌ | ❌ | ❌ |
| ConsolePi (pi03) | ✅ TCP:22 | ❌ | ❌ | ❌ |

---

## Access Methods

### Quick Reference

```bash
# Power Control
just infra pdu-status              # Check all PDU outlets
just infra pdu-on <node>           # Power on node
just infra pdu-reboot <node>       # Power cycle node

# KVM Access
just infra kvm-switch <node>       # Switch HDMI to node
just infra console <node>          # Switch + take screenshot

# Serial Console
ssh pi@192.168.42.22               # ConsolePi (Core01-U1)
ssh pi@192.168.42.23               # ConsolePi (Core01-U2)

# Monitoring
https://status.homeops.ca          # Unified status (Gatus)
https://grafana.homeops.ca/d/apc-ups # UPS metrics dashboard
https://alertmanager.homeops.ca    # Active alerts
```

---

## Validation Results

✅ **Gatus Config:** Valid YAML syntax
✅ **PrometheusRule:** Valid YAML syntax
✅ **OOB Endpoints:** 7 devices added to Gatus
✅ **Alert Rules:** 4 new rules added to Prometheus
✅ **Documentation:** Comprehensive guide created

---

## What's NOT Changed

**Intentionally Preserved:**
- Existing scripts (`infra-pikvm.sh`, `infra-pdu.sh`) - no modifications
- SNMP Exporter configuration - no target changes
- Blackbox Exporter probes - already monitoring OOB devices
- Grafana UPS dashboard - already configured
- Existing Prometheus alert rules - preserved and enhanced

**Physical Hardware:**
- PiKVM remains standalone
- ConsolePi devices remain dedicated (pi02/pi03)
- PDUs remain SNMP-managed
- UPS remains SNMP-monitored

This is a **monitoring consolidation**, not a hardware consolidation.

---

## Dependencies

### Blocking (mentioned in original issue)

- **#3054 - VLAN interfaces for OOB network access**
  - Status: Not implemented
  - Impact: Kubernetes nodes cannot directly access Management VLAN (99)
  - Current workaround: Access via fw01 routing
  - Future: Add bond0.99 interfaces to Talos nodes for direct SNMP access

- **#3064 - Centralized authentication**
  - Status: Not implemented
  - Impact: Each OOB device has separate auth (PiKVM, PDU SNMP, ConsolePi SSH)
  - Future: Integrate with SSO (Authelia/LLDAP), add MFA

### Unblocked Work

This consolidation can proceed without the above dependencies. The monitoring and documentation improvements are standalone.

---

## Future Improvements (Discussion Needed)

### Short-term (Can Implement Now)

1. **Enhanced UPS Monitoring**
   - Per-outlet power monitoring (if PDUs support it)
   - Runtime estimation alerts (e.g., "< 10min on battery")
   - Historical power usage trending

2. **ConsolePi Monitoring**
   - Add to Blackbox Exporter ICMP probes
   - Monitor USB-serial adapter presence
   - Alert on ConsolePi unavailability

3. **Automated Recovery**
   - Alertmanager → PDU power cycle integration
   - Safe guards: backoff, max retries, approval gates
   - Health check → auto-remediation workflows

### Long-term (Needs Architecture Decision)

1. **NUT (Network UPS Tools) Migration**
   - Move from SNMP Exporter to dedicated NUT server in Kubernetes
   - Encrypted UPS protocol instead of SNMP
   - Automatic shutdown orchestration on critical battery
   - **Question:** DaemonSet vs. dedicated pod? Which nodes?

2. **Serial Console Consolidation**
   - Single serial server vs. multiple ConsolePi devices?
   - Serial-over-IP for all critical infrastructure?
   - Alternative: [ser2net](https://github.com/cminyard/ser2net) in Kubernetes?

3. **Unified Web Dashboard**
   - Single pane of glass for all OOB operations (KVM, power, serial)?
   - Replace vendor UIs (PiKVM, PDU web interfaces)?
   - Audit logging for all OOB actions?

4. **Hardware Lifecycle**
   - What happens to ConsolePi hardware if serial is consolidated?
   - Can PiKVM be extended to handle serial console too?
   - PDU replacement candidates (SNMPv3, per-outlet monitoring)?

---

## Questions for Review

1. **NUT Migration:** Should we migrate UPS monitoring from SNMP to NUT?
   - Pros: Encrypted, better shutdown integration, native UPS protocol
   - Cons: Additional complexity, new daemon to manage

2. **Serial Consolidation:** Keep ConsolePi dedicated or consolidate?
   - Current: 2 dedicated RPi4 for switch serial console
   - Alternative: ser2net pod? Extend PiKVM? Keep as-is?

3. **Authentication Strategy:** Wait for #3064 or implement partial auth now?
   - PiKVM can integrate with LDAP today
   - PDU/UPS could move to SNMPv3 (auth+encryption)

4. **Monitoring Gaps:** What else should be monitored?
   - TESmart KVM switch itself?
   - Individual PDU outlets (not just whole PDU)?
   - PiKVM system metrics (temp, disk, etc.)?

---

## Testing Plan

### Post-Merge Validation

Once changes are merged and Flux reconciles:

1. **Gatus Status Page**
   ```bash
   curl -sk https://status.homeops.ca/api/v1/endpoints/statuses | \
     jq '.[] | select(.group=="oob-management") | {name: .name, status: .results[-1].success}'
   ```
   Expected: 7 endpoints, all with `success: true`

2. **Prometheus Alerts**
   ```bash
   curl -sk https://prometheus.homeops.ca/api/v1/rules | \
     jq '.data.groups[].rules[] | select(.name | startswith("PDU") or startswith("UPS")) | .name'
   ```
   Expected: 6 alert rules (2 existing + 4 new)

3. **SNMP Exporter Targets**
   ```bash
   curl -sk https://prometheus.homeops.ca/api/v1/targets | \
     jq '.data.activeTargets[] | select(.labels.job=="snmp-exporter") | {instance: .labels.instance, health: .health}'
   ```
   Expected: 4 targets (pdu01, pdu02, ups01, ups02), all `health: "up"`

4. **Manual Endpoint Tests**
   ```bash
   # PiKVM reachable
   curl -sk -o /dev/null -w "%{http_code}\n" https://kvm01.in.homeops.ca
   # Expected: 200

   # PDU SNMP responsive
   timeout 3 bash -c "echo >/dev/tcp/pdu01.in.homeops.ca/161" && echo "OK"
   # Expected: OK

   # ConsolePi SSH reachable
   timeout 3 bash -c "echo >/dev/tcp/192.168.42.22/22" && echo "OK"
   # Expected: OK
   ```

---

## Roll-back Plan

If issues arise after merge:

1. **Gatus issues:** Revert `kubernetes/apps/observability/gatus/app/resources/config.yaml`
2. **Alert spam:** Temporarily silence new alerts via Alertmanager
3. **Full rollback:** `git revert <commit-sha>`

All changes are additive and non-breaking. Existing monitoring continues to work.

---

## Metrics

**Files Changed:** 4
- `kubernetes/apps/observability/gatus/app/resources/config.yaml` (enhanced)
- `kubernetes/apps/observability/snmp-exporter/app/prometheusrule.yaml` (enhanced)
- `docs/OOB-MANAGEMENT.md` (new, 776 lines)
- `README.md` (enhanced)

**New Monitoring:**
- 7 Gatus endpoints
- 4 Prometheus alert rules
- 1 comprehensive documentation guide

**Existing Systems Enhanced:**
- Gatus status page (new OOB group)
- Prometheus alerting (better coverage)
- Documentation (unified reference)

---

## Related Issues

- **Current Issue:** OOB management consolidation
- **#3054:** VLAN interfaces for OOB network access (dependency)
- **#3064:** Centralized auth for device access (dependency)

---

## Next Steps

1. ✅ **Code review** - Review this PR
2. ⏳ **Merge** - Merge to main branch
3. ⏳ **Flux reconcile** - Wait for Flux to apply changes (~2-5 minutes)
4. ⏳ **Validation** - Run testing plan above
5. ⏳ **Discussion** - Address "Questions for Review" section
6. ⏳ **Future work** - Create issues for long-term improvements

---

**Author:** Claude Code Agent
**Reviewer:** @osnabrugge
**Last Updated:** 2026-04-30
