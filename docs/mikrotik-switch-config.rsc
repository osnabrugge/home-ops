# ============================================================================
# MikroTik CRS3xx Switch Configuration — home-ops
# ============================================================================
# Port Assignments:
#   ether1           → VLAN99 (Management) — untagged access port
#   ether2-ether8    → Available for access/trunk ports (adjust as needed)
#   sfp-sfpplus1     → 10G SFP+ trunk to pve01 (all VLANs tagged)
#   sfp-sfpplus2     → 1G SFP trunk to fw01 (all VLANs tagged + WAN transit)
#   sfp-sfpplus3     → Unused (cooling gap)
#   sfp-sfpplus4     → XPS-PON module (ISP WAN uplink)
#
# VLAN Layout (matches fw01 OPNsense):
#   VLAN 1   — 192.168.0.0/24   — Default/Guest
#   VLAN 10  — 192.168.10.0/24  — User Devices
#   VLAN 42  — 192.168.42.0/24  — Servers/Cluster
#   VLAN 50  — 192.168.50.0/24  — Home LAN
#   VLAN 70  — 192.168.70.0/24  — IoT
#   VLAN 99  — 192.168.99.0/24  — Management
#   VLAN 4000 — WAN Transit      — XPS-PON ↔ fw01 PPPoE
#
# Usage: Paste into MikroTik terminal (System > Terminal) or import via file.
# ============================================================================

# --- Reset to clean slate (uncomment if starting fresh) ---
# /system reset-configuration no-defaults=yes skip-backup=yes

# --- System Identity ---
/system identity set name="sw01"

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

# --- Bridge ports — add all physical interfaces ---
/interface bridge port
add bridge=bridge1 interface=ether1 pvid=99
add bridge=bridge1 interface=ether2 pvid=50
add bridge=bridge1 interface=ether3 pvid=50
add bridge=bridge1 interface=ether4 pvid=50
add bridge=bridge1 interface=ether5 pvid=42
add bridge=bridge1 interface=ether6 pvid=42
add bridge=bridge1 interface=ether7 pvid=42
add bridge=bridge1 interface=ether8 pvid=42
add bridge=bridge1 interface=sfp-sfpplus1
add bridge=bridge1 interface=sfp-sfpplus2
add bridge=bridge1 interface=sfp-sfpplus4 pvid=4000

# --- VLAN definitions on the bridge ---
# Each VLAN lists its tagged (trunk) and untagged (access) ports.
/interface bridge vlan

# VLAN 1 — Default/Guest
add bridge=bridge1 vlan-ids=1 \
    tagged=sfp-sfpplus1,sfp-sfpplus2

# VLAN 10 — User Devices
add bridge=bridge1 vlan-ids=10 \
    tagged=sfp-sfpplus1,sfp-sfpplus2

# VLAN 42 — Servers/Cluster
add bridge=bridge1 vlan-ids=42 \
    tagged=sfp-sfpplus1,sfp-sfpplus2 \
    untagged=ether5,ether6,ether7,ether8

# VLAN 50 — Home LAN
add bridge=bridge1 vlan-ids=50 \
    tagged=sfp-sfpplus1,sfp-sfpplus2 \
    untagged=ether2,ether3,ether4

# VLAN 70 — IoT
add bridge=bridge1 vlan-ids=70 \
    tagged=sfp-sfpplus1,sfp-sfpplus2

# VLAN 99 — Management (switch management access)
add bridge=bridge1 vlan-ids=99 \
    tagged=sfp-sfpplus1,sfp-sfpplus2,bridge1 \
    untagged=ether1

# VLAN 4000 — WAN Transit (XPS-PON ↔ fw01)
add bridge=bridge1 vlan-ids=4000 \
    tagged=sfp-sfpplus2 \
    untagged=sfp-sfpplus4

# --- Management IP on VLAN99 ---
/interface vlan
add interface=bridge1 name=vlan99-mgmt vlan-id=99

/ip address
add address=192.168.99.2/24 interface=vlan99-mgmt

# --- Default gateway (fw01) ---
/ip route
add dst-address=0.0.0.0/0 gateway=192.168.99.1

# --- DNS ---
/ip dns
set servers=192.168.42.1

# --- NTP ---
/system ntp client
set enabled=yes

/system ntp client servers
add address=time.cloudflare.com

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
# /ping 192.168.99.1
