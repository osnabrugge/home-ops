# OOB Hardware Consolidation - Technical Feasibility Analysis

**Date:** 2026-04-30
**Context:** Evaluating consolidation of ConsolePi (serial console) and PDU control into PiKVM

---

## Current State

### Hardware Inventory
- **PiKVM V4 Plus** (kvm01) - Arch Linux based, currently handling:
  - Video/keyboard/mouse via HDMI KVM
  - TESmart 16-port HDMI switch control via GPIO
  - Wake-on-LAN via GPIO
  - Virtual USB drive mounting

- **Raspberry Pi 4B x4** (pi01-04) - Raspbian based:
  - **pi02** - ConsolePi providing serial console to Core01-U1 (Brocade switch)
  - **pi03** - ConsolePi providing serial console to Core01-U2 (Brocade switch)
  - **pi01, pi04** - Available for other projects

- **PDU Control** - Currently via SNMP from scripts/cluster:
  - CyberPower PDU01/02 controlled via `snmpset`
  - No integration with PiKVM WebUI

### Target Architecture

Consolidate into PiKVM with unified WebUI showing per-host:
- ✅ Video/keyboard/mouse (already working)
- ✅ HDMI switching (already working via GPIO)
- ⏳ Serial/UART console access (new)
- ⏳ Power control (PDU integration) (new)
- ⏳ Power status display (new)
- 🔮 BMC integration via Redfish/IPMI (future)

**Goal:** Free up all 4 Raspberry Pi devices for other projects.

---

## Technical Approaches

### Option 1: Extend PiKVM (Recommended)

**Strategy:** Add serial console and PDU control as custom services on existing PiKVM

#### Serial Console Integration

**PiKVM V4 Plus Hardware Capabilities:**
- CM4-based (same as RPi4 compute module)
- Has USB ports that can accept USB-to-serial adapters
- Can run additional services on Arch Linux
- Already uses `/etc/kvmd/override.yaml` for GPIO customization

**Implementation Path:**

1. **Install ser2net on PiKVM:**
   ```bash
   # PiKVM uses pacman (Arch Linux)
   ssh root@kvm01.in.homeops.ca
   rw  # Make filesystem writable
   pacman -S ser2net
   ro  # Make filesystem read-only again
   ```

2. **Connect USB-to-serial adapters:**
   - Move serial cables from pi02/pi03 to kvm01
   - Use 2x USB-to-serial adapters plugged into PiKVM USB ports
   - Map to Core01-U1 and Core01-U2

3. **Configure ser2net:**
   ```yaml
   # /etc/ser2net.yaml
   connection: &console-u1
     accepter: telnet(rfc2217),tcp,3001
     connector: serialdev,/dev/ttyUSB0,115200n81,local
     options:
       kickolduser: true

   connection: &console-u2
     accepter: telnet(rfc2217),tcp,3002
     connector: serialdev,/dev/ttyUSB1,115200n81,local
     options:
       kickolduser: true
   ```

4. **Add WebUI buttons via custom HTML/JS:**
   - PiKVM supports custom web interface plugins
   - Add buttons that open terminal windows to `tcp://kvm01:3001` (Core01-U1)
   - Use libraries like xterm.js for in-browser serial terminal

**Pros:**
- ✅ Uses existing PiKVM hardware
- ✅ Minimal additional hardware (2x USB-serial adapters, ~$20)
- ✅ Arch Linux package ecosystem available
- ✅ Can persist across PiKVM updates with proper configuration
- ✅ Frees up 2 Raspberry Pi devices immediately

**Cons:**
- ⚠️ Requires filesystem to be writable (security consideration)
- ⚠️ Custom modifications may need maintenance after PiKVM updates
- ⚠️ USB-serial adapters add potential failure points

#### PDU Control Integration

**Implementation Path:**

1. **Install Python dependencies on PiKVM:**
   ```bash
   rw
   pacman -S python-pysnmp
   ro
   ```

2. **Create PDU control script:**
   ```python
   # /usr/local/bin/pdu-control.py
   # (Similar to existing infra-pdu.sh but Python-based for easier WebUI integration)
   ```

3. **Expose via PiKVM API or custom endpoint:**
   - Option A: Custom FastAPI service on kvm01:8000
   - Option B: Integrate into KVMD's existing API (requires more work)
   - Option C: Simple CGI scripts accessible via nginx

4. **Add WebUI controls:**
   - Custom JavaScript to call PDU API
   - Show power status per outlet
   - Add power on/off/reboot buttons per host
   - Could integrate with existing TESmart switch UI

**Pros:**
- ✅ Centralized power control in same interface as KVM
- ✅ Can display real-time power status
- ✅ No additional hardware needed
- ✅ Network access to PDUs already working

**Cons:**
- ⚠️ SNMP credentials need to be stored on PiKVM
- ⚠️ Requires custom web development
- ⚠️ PDU control is destructive - needs good auth/safeguards

---

### Option 2: PDUDaemon Integration

**Strategy:** Use existing pdudaemon project for standardized PDU control

**About PDUDaemon:**
- Open-source project: https://github.com/pdudaemon/pdudaemon
- Supports many PDU types including CyberPower via SNMP
- REST API for power control
- Already used in some homelab/testing environments

**Implementation:**
```bash
# Install on PiKVM or separate container
pip install pdudaemon

# Configure PDUs
cat > /etc/pdudaemon/pdudaemon.conf <<EOF
[pdu01]
driver = cyberpower
hostname = 192.168.99.15
community = private

[pdu02]
driver = cyberpower
hostname = 192.168.99.16
community = private
EOF

# Start daemon
pdudaemon --conf /etc/pdudaemon/pdudaemon.conf
```

**API Usage:**
```bash
# Power on k8s01 (pdu01 outlet 1)
curl http://kvm01:16421/power/control/on?hostname=pdu01&port=1

# Check status
curl http://kvm01:16421/power/status?hostname=pdu01&port=1
```

**Pros:**
- ✅ Well-tested, maintained project
- ✅ Supports many PDU types (future-proof)
- ✅ Clean REST API
- ✅ Could run in Kubernetes (alternative deployment)

**Cons:**
- ⚠️ CyberPower support may need validation/testing
- ⚠️ Additional service to maintain

---

### Option 3: Rebuild Everything on Raspberry Pi OS

**Strategy:** Port PiKVM components to Raspberry Pi OS base

**What Would Need Porting:**
- **ustreamer** - Low-latency video capture/streaming (C, should compile on Raspbian)
- **kvmd** - PiKVM daemon (Python, dependencies may differ)
- **Web UI** - HTML/JS/CSS (should work anywhere)
- **GPIO control** - Already Python-based, should port easily
- **janus-gateway** - WebRTC server (available in Raspbian repos)

**Implementation Effort:**
- **High complexity** - PiKVM is tightly integrated with Arch
- Many dependencies expect Arch package names/paths
- HDMI capture hardware drivers may differ
- Ongoing maintenance burden to track PiKVM upstream

**Pros:**
- ✅ Full control over base OS
- ✅ Easier to add arbitrary services (no read-only filesystem by default)
- ✅ Familiar Debian/Raspbian ecosystem

**Cons:**
- ❌ **High effort** - essentially forking PiKVM
- ❌ **Maintenance burden** - need to track upstream changes
- ❌ Loses official PiKVM updates/support
- ❌ May break with hardware differences (V4 Plus specific features)
- ❌ Not recommended unless significant community demand justifies it

---

### Option 4: Separate Consolidation Appliance

**Strategy:** Run everything on a single Raspberry Pi 4 with Raspberry Pi OS

**Components:**
- ser2net for serial console (easy)
- Custom web UI combining:
  - Serial console access (xterm.js)
  - PDU control (custom or pdudaemon)
  - Links/iframes to PiKVM for video
  - TESmart control via PiKVM API

**Pros:**
- ✅ Keeps PiKVM untouched (no modification risk)
- ✅ Frees up 3 of 4 Raspberry Pis
- ✅ Easy to rebuild/replace
- ✅ Full Raspbian compatibility

**Cons:**
- ⚠️ Not truly unified (still 2 devices)
- ⚠️ Requires custom web development
- ⚠️ Doesn't free up all 4 Raspberry Pis (only 3)

---

## Recommended Approach

### Phase 1: Serial Console Consolidation (Low Risk, High Value)

**Immediate actions:**

1. **Prepare PiKVM:**
   ```bash
   ssh root@kvm01.in.homeops.ca
   rw
   pacman -S ser2net
   ```

2. **Configure ser2net:**
   - Create `/etc/ser2net.yaml`
   - Enable and start service: `systemctl enable --now ser2net`

3. **Hardware migration:**
   - Order 2x USB-to-serial adapters (FTDI FT232RL recommended, ~$10 each)
   - Cable run from Core01 serial ports to kvm01 rack location
   - Move serial connections from pi02/pi03 to kvm01

4. **Test access:**
   ```bash
   # From any machine
   telnet kvm01.in.homeops.ca 3001  # Core01-U1
   telnet kvm01.in.homeops.ca 3002  # Core01-U2
   ```

5. **Update documentation:**
   - Update OOB-MANAGEMENT.md with new serial access method
   - Create helper scripts: `just infra serial core01-u1`

**Outcome:** Frees pi02 and pi03 for other projects.

### Phase 2: PDU Control Integration (Medium Effort)

**Implementation:**

1. **Install pdudaemon on PiKVM:**
   - Could run as systemd service
   - Or deploy as lightweight container if PiKVM supports it

2. **Create simple REST API wrapper:**
   - Expose at `http://kvm01:8000/pdu/`
   - Map friendly names (k8s01) to PDU/outlet

3. **WebUI enhancements:**
   - Add power status indicators to existing TESmart host list
   - Add power control buttons (on/off/reboot)
   - Implement confirmation dialogs for destructive actions

**Outcome:** Unified interface for KVM + power control.

### Phase 3: Custom WebUI (Optional, Higher Effort)

**Create consolidated dashboard:**

```
┌─────────────────────────────────────────────────────┐
│  PiKVM Unified Management - k8s01                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  [Video] [Serial] [Power] [BMC*]                   │
│                                                      │
│  Video Feed: [PiKVM native interface]               │
│                                                      │
│  Serial Console (Core01-U1):                        │
│  ┌────────────────────────────────────────────────┐ │
│  │ xterm.js terminal connected to ser2net         │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  Power Control:                                     │
│  Status: ● ON  [Reboot] [Power Off]                │
│                                                      │
│  All Hosts: [k8s01] [k8s02] [k8s03] [k8s04] ...    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Technology stack:**
- HTML/JS/CSS custom page
- WebSockets for serial console (xterm.js)
- REST API calls to PiKVM and pdudaemon
- Could be served from PiKVM's nginx or separate lightweight server

---

## Cost & Effort Estimates

| Phase | Hardware Cost | Time Estimate | Complexity |
|-------|---------------|---------------|------------|
| Phase 1: Serial Console | $20 (USB-serial adapters) | 2-4 hours | Low |
| Phase 2: PDU Integration | $0 | 4-8 hours | Medium |
| Phase 3: Custom WebUI | $0 | 8-16 hours | Medium-High |
| **Total** | **$20** | **14-28 hours** | **Medium** |

**Alternative (Option 3 - Full Rebuild):**
- Hardware: $0 (reuse existing)
- Time: 40-80 hours
- Complexity: High
- Maintenance: Ongoing burden

---

## Risks & Mitigation

### Risk 1: PiKVM Filesystem Modifications
- **Risk:** Changes may not survive PiKVM updates
- **Mitigation:**
  - Document all modifications in `/root/CUSTOMIZATIONS.md`
  - Store configuration in `/etc/kvmd/override.d/` where supported
  - Use PiKVM's read-write toggle (`rw`/`ro`) pattern
  - Test updates on staging before production

### Risk 2: USB-Serial Adapter Reliability
- **Risk:** USB adapters may lose enumeration or fail
- **Mitigation:**
  - Use FTDI chipsets (most reliable)
  - Use udev rules to create stable device names by serial number
  - Monitor adapter presence in monitoring stack
  - Keep spare adapters on hand

### Risk 3: Power Control Security
- **Risk:** Unauthorized power control could disrupt services
- **Mitigation:**
  - Require authentication for PDU API
  - Implement confirmation prompts in WebUI
  - Log all power control actions
  - Consider integration with #3064 (centralized auth)

### Risk 4: Serial Console Conflicts
- **Risk:** Multiple simultaneous connections to same serial port
- **Mitigation:**
  - ser2net `kickolduser: true` option
  - Document that connections are exclusive
  - Consider connection queue/notification system

---

## Community Contribution Opportunity

If PiKVM ↔ Raspberry Pi OS port is pursued:

### Potential Project: "PiKVM Lite" or "PiKVM-Debian"

**Value proposition:**
- Lower barrier to entry (more familiar OS)
- Easier to customize for homelab use
- Could attract Debian/Ubuntu users
- Enables tighter integration with other homelab tools

**Challenges:**
- Significant effort to maintain fork
- PiKVM team may not want to support multiple OS bases
- Could fragment community

**Alternative: Upstream Contributions**
- Rather than fork, contribute serial console and PDU plugins to upstream PiKVM
- Propose `/etc/kvmd/plugins.d/` architecture for community extensions
- Share ser2net integration as documented community plugin
- This benefits everyone and shares maintenance burden

---

## Recommendation

**Phase 1 (Serial Console) is highly recommended and low-risk:**
- Proven technology (ser2net)
- Minimal hardware cost ($20)
- Frees 2 Raspberry Pi devices immediately
- Can be completed in a weekend
- Reversible if issues arise

**Phase 2 (PDU Integration) is worthwhile if Phase 1 succeeds:**
- No hardware cost
- Significantly improves operator experience
- Centralizes OOB management
- Medium effort but high value

**Phase 3 (Custom WebUI) is optional:**
- Nice to have but not essential
- Can be incremental improvements
- Good opportunity for automation/scripting practice

**Option 3 (Full Rebuild) is NOT recommended:**
- Very high effort (40-80 hours)
- Ongoing maintenance burden
- Loses PiKVM official updates
- Unless there's a large community ready to maintain it, not worth the investment

---

## Next Steps

1. **Validate hardware compatibility:**
   - Order USB-to-serial adapters (FTDI FT232RL or similar)
   - Test ser2net on PiKVM in lab environment

2. **Proof of concept:**
   - Connect one serial adapter to PiKVM
   - Configure ser2net for single port
   - Verify access from remote machine
   - Test with actual switch serial console

3. **If successful, proceed to full migration:**
   - Migrate both serial connections
   - Decommission pi02/pi03 from console duty
   - Repurpose for other projects

4. **Document and share:**
   - Update OOB-MANAGEMENT.md
   - Create helper scripts/justfile recipes
   - Consider contributing guide to PiKVM community

5. **Then evaluate Phase 2 (PDU):**
   - Based on Phase 1 experience
   - Decide on pdudaemon vs. custom approach
   - Design WebUI integration

---

## Questions for Discussion

1. **Budget confirmation:** Is $20 for USB-serial adapters acceptable?
2. **Downtime tolerance:** What's acceptable downtime for serial console migration?
3. **Scope:** Should we do Phase 1 only, or plan for Phase 2 immediately?
4. **Testing:** Is there a test environment or do we test in production?
5. **Community contribution:** Interest in documenting this as a PiKVM community guide?

---

**Conclusion:** Consolidating serial console to PiKVM is feasible, low-cost, and recommended. Full OS rebuild is not recommended due to high effort and maintenance burden. PDU integration is a good Phase 2 project after serial console success.
