# ============================================================================
# MikroTik CRS305-1G-4S+IN Switch Configuration — home-ops (sw01)
# ============================================================================
# Hardware: CRS305-1G-4S+IN — 1× GbE (ether1) + 4× SFP+ ports
# Role:     WAN-side switch — bridges ISP XPS-PON to firewall
#
# Port Assignments:
#   ether1           → VLAN99 (Management) — untagged access port
#   sfp-sfpplus1     → 10G SFP+ to pve01 (VLAN99 tagged — management only)
#   sfp-sfpplus2     → 1G SFP to fw01 (VLAN99 + VLAN4000 tagged)
#   sfp-sfpplus3     → Unused (cooling gap — leave empty)
#   sfp-sfpplus4     → XPS-PON module (ISP WAN uplink, VLAN4000 untagged)
#
# VLAN Layout (WAN-side only — NO internal VLANs on this switch):
#   VLAN 99   — 192.168.99.0/24  — Management (switch + pve01 OOB access)
#   VLAN 4000 — WAN Transit       — XPS-PON ↔ fw01 PPPoE
#
# SECURITY: Internal VLANs (1, 10, 42, 50, 70) are NOT configured here.
#           This switch sits between ISP and firewall — only management and
#           WAN transit VLANs are permitted.
#
# Usage: Paste into MikroTik terminal (System > Terminal) or import via file.
# ============================================================================

# --- Reset to clean slate (uncomment if starting fresh) ---
# /system reset-configuration no-defaults=yes skip-backup=yes

# --- System Identity ---
/system identity set name="ext01"

# --- Disable unused services for security ---
/ip service
set telnet disabled=yes
set ftp disabled=yes
set www disabled=yes
set api disabled=yes
set api-ssl disabled=yes
set winbox disabled=no
set ssh disabled=no

# --- Set SSH to key-only auth (add your key after) ---
/ip ssh set strong-crypto=yes always-allow-password-login=no

# --- Create bridge with VLAN filtering ---
/interface bridge
add name=bridge1 vlan-filtering=no protocol-mode=none

# NOTE: We create the bridge with vlan-filtering=no FIRST, add all ports
# and VLAN config, then enable filtering at the end. Enabling filtering
# before config is complete will lock you out!

# --- Bridge ports — only ports in use ---
# NOTE: sfp-sfpplus3 intentionally left out (cooling gap)
/interface bridge port
add bridge=bridge1 interface=ether1 pvid=99
add bridge=bridge1 interface=sfp-sfpplus1
add bridge=bridge1 interface=sfp-sfpplus2
add bridge=bridge1 interface=sfp-sfpplus4 pvid=4000

# --- VLAN definitions on the bridge ---
# SECURITY: Only management and WAN transit VLANs are configured.
# No internal VLANs (1, 10, 42, 50, 70) exist on this WAN-side switch.
/interface bridge vlan

# VLAN 99 — Management (switch mgmt + pve01 OOB)
add bridge=bridge1 vlan-ids=99 \
    tagged=bridge1 \
    untagged=ether1

# VLAN 4000 — WAN Transit (XPS-PON ↔ fw01 PPPoE)
add bridge=bridge1 vlan-ids=4000 \
    tagged=sfp-sfpplus2 \
    untagged=sfp-sfpplus4

# --- Management IP on VLAN99 ---
/interface vlan
add interface=bridge1 name=vlan99-mgmt vlan-id=99

/ip address
add address=192.168.99.24/24 interface=vlan99-mgmt

# --- Default gateway (fw01) ---
/ip route
add dst-address=0.0.0.0/0 gateway=192.168.99.4

# --- DNS ---
/ip dns
set servers=192.168.99.1

# --- NTP ---
/system ntp client
set enabled=yes

/system ntp client servers
add address=ntp.in.homeops.ca

# --- Disable discovery on non-management ports ---
/ip neighbor discovery-settings
set discover-interface-list=none

# --- Logging ---
/system logging
add topics=critical action=memory
add topics=error action=memory

# ============================================================================
# ENABLE VLAN FILTERING — DO THIS LAST!
# After pasting everything above, paste this line to activate VLAN filtering.
# WARNING: If your console is not on ether1 (VLAN99), you will lose access!
# ============================================================================
/interface bridge set bridge1 vlan-filtering=yes

# --- Verify ---
# /interface bridge vlan print
# /interface bridge port print
# /ping 192.168.99.4
