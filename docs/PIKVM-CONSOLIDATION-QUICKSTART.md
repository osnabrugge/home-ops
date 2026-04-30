# PiKVM Serial Console Consolidation - Quick Start Guide

**Related:** PIKVM-CONSOLIDATION-RESEARCH.md (full technical analysis)

---

## TL;DR

**Goal:** Move serial console access from pi02/pi03 (ConsolePi) to PiKVM V4 Plus.

**Method:** Install `ser2net` on PiKVM, connect USB-to-serial adapters.

**Result:** Reduce hardware count (5 → 3 devices), unified console access.

**Effort:** 2-4 hours (low complexity)

**Risk:** Low (easy rollback, serial console rarely used)

---

## Quick Implementation

### 1. Install Ser2Net on PiKVM

```bash
# SSH to PiKVM
ssh root@kvm01.in.homeops.ca

# Make filesystem writable
rw

# Install ser2net
pacman -Sy ser2net

# Check installation
which ser2net
```

### 2. Move USB-to-Serial Adapters

- Unplug adapters from pi02 (Core01-U1) and pi03 (Core01-U2)
- Plug both into PiKVM USB ports
- Identify devices:

```bash
ls -l /dev/serial/by-id/
# Example output:
# usb-FTDI_FT232R_USB_UART_A1B2C3D4-if00-port0 -> ../../ttyUSB0
# usb-FTDI_FT232R_USB_UART_A5B6C7D8-if00-port0 -> ../../ttyUSB1
```

### 3. Configure Ser2Net

```bash
# Create config directory
mkdir -p /etc/ser2net

# Create config file (replace device IDs with actual values from step 2)
cat > /etc/ser2net/ser2net.yaml <<'EOF'
connection: &core01_u1
  accepter: tcp,2001
  connector: serialdev,/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_XXXXXXXX-if00-port0,9600n81,local
  options:
    kickolduser: true

connection: &core01_u2
  accepter: tcp,2002
  connector: serialdev,/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_YYYYYYYY-if00-port0,9600n81,local
  options:
    kickolduser: true
EOF

# Enable and start service
systemctl enable --now ser2net

# Check status
systemctl status ser2net

# Make filesystem read-only
ro
```

### 4. Test Serial Console Access

```bash
# From workstation
telnet kvm01.in.homeops.ca 2001  # Core01-U1
telnet kvm01.in.homeops.ca 2002  # Core01-U2

# Should connect to switch serial console
# Press Enter to get prompt
```

### 5. (Optional) Enable PiKVM Web UI Access

```bash
# Edit override.yaml
rw
cat >> /etc/kvmd/override.yaml <<'EOF'

webterm:
  enabled: true

  terminals:
    core01-u1:
      device: /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_XXXXXXXX-if00-port0
      speed: 9600

    core01-u2:
      device: /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_YYYYYYYY-if00-port0
      speed: 9600
EOF

# Restart kvmd
systemctl restart kvmd
ro

# Access via web UI:
# https://kvm01.in.homeops.ca → Console tab → Select terminal
```

---

## Access Methods

### Before (ConsolePi)

```bash
# SSH to ConsolePi
ssh pi@192.168.42.22  # Core01-U1
ssh pi@192.168.42.23  # Core01-U2

# Connect to serial console
screen /dev/ttyUSB0 9600
```

### After (PiKVM + Ser2Net)

```bash
# Option 1: Telnet (network)
telnet kvm01.in.homeops.ca 2001  # Core01-U1
telnet kvm01.in.homeops.ca 2002  # Core01-U2

# Option 2: Web UI
# https://kvm01.in.homeops.ca → Console tab

# Option 3: SSH to PiKVM (direct)
ssh root@kvm01.in.homeops.ca
screen /dev/ttyUSB0 9600
```

---

## Rollback Plan

If serial console fails:

1. Unplug USB-to-serial adapters from PiKVM
2. Reconnect to pi02/pi03
3. Power on pi02/pi03
4. Serial console access restored

**Time to rollback:** 5 minutes

---

## Next Steps After Implementation

1. **Test for 1 week** - Ensure stability
2. **Update documentation:**
   - Edit `docs/OOB-MANAGEMENT.md` (serial console section)
   - Edit `README.md` (hardware table)
3. **Add monitoring:**
   - Gatus TCP checks for ports 2001/2002
   - Update `kubernetes/apps/observability/gatus/app/resources/config.yaml`
4. **Decommission pi02/pi03:**
   - Power off after 1 week of stable operation
   - Repurpose or retire hardware

---

## Troubleshooting

### Ser2Net not starting

```bash
# Check service status
systemctl status ser2net

# Check logs
journalctl -u ser2net -f

# Common issues:
# - Wrong device path in config (use /dev/serial/by-id/)
# - Port already in use (check with: netstat -tuln | grep 2001)
```

### USB-to-Serial adapter not detected

```bash
# Check USB devices
lsusb

# Check serial devices
ls -l /dev/ttyUSB*

# Check dmesg for errors
dmesg | tail -20

# Verify adapter is plugged in and working
# (try on different USB port)
```

### Cannot connect via Telnet

```bash
# Test port from PiKVM itself
telnet localhost 2001

# If works locally but not remotely, check firewall
# (Management VLAN 99 should allow all traffic to PiKVM)

# Test with netcat
nc -v kvm01.in.homeops.ca 2001
```

---

## Security Notes

**Ser2Net uses Telnet (plaintext protocol):**

- Only accessible on Management VLAN (99)
- NOT exposed to internet
- Consider SSH tunneling for extra security:

```bash
# SSH tunnel example
ssh -L 2001:localhost:2001 root@kvm01.in.homeops.ca
telnet localhost 2001  # Now encrypted via SSH
```

---

## Hardware Requirements

**Current Setup:**
- 2x Raspberry Pi 4B (pi02, pi03) running ConsolePi
- 2x USB-to-serial adapters (FTDI FT232RL recommended)

**After Consolidation:**
- USB-to-serial adapters moved to PiKVM
- pi02/pi03 can be repurposed or retired

**No new hardware needed** (reuse existing adapters)

---

## Summary

| Metric | Before | After |
|--------|--------|-------|
| Devices | 5 (PiKVM + 2 RPi + 2 PDU) | 3 (PiKVM + 2 PDU) |
| Serial Access | SSH to pi02/pi03 | Telnet/Web UI to PiKVM |
| Power Consumption | ~30W (3 RPi4) | ~20W (1 RPi4) |
| Management Overhead | 3 devices | 1 device |

**Result:** Simpler, more unified OOB management.

---

**See:** PIKVM-CONSOLIDATION-RESEARCH.md for full technical analysis, architecture details, and PDU integration discussion.
