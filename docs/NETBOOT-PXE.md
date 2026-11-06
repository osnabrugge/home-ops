# PXE Boot Infrastructure — netboot.xyz

> **Deployment:** `kubernetes/apps/network/netboot-xyz/`
> **LoadBalancer IP:** 192.168.69.131 (TFTP + HTTP boot assets)
> **Web UI:** https://netboot-xyz.homeops.ca (internal only via envoy-internal)
> **NAS ISO store:** nas01.in.homeops.ca:/mnt/nfs/netboot → /assets in pod

---

## Overview

netboot.xyz provides a unified PXE boot menu supporting:

- **x86-64 UEFI** — servers, laptops, workstations (Talos, Proxmox, Ubuntu, Windows, OPNsense, etc.)
- **ARM64 UEFI** — Raspberry Pi 4/5 (with UEFI firmware), ARM servers
- **Troubleshooting tools** — memtest86+, SystemRescue, GParted, DBAN
- **Custom entries** — local ISOs on NAS, custom Talos images with SecureBoot

The TFTP service lives at **192.168.69.131:69/udp** and the HTTP asset server at **192.168.69.131:80/tcp**.
The admin UI runs at port 3000 and is accessible via envoy-internal only.

### Kubernetes TFTP transport

The integrated dnsmasq server must use `tftp-single-port`: the LoadBalancer exposes
UDP 69, not dynamically allocated TFTP transfer ports. Without this option the
server can log a file as sent while the client fails during the data/ACK exchange.
The `netboot-xyz-tftp` ConfigMap supplies this option without changing DHCP on gw01.

Bootloaders and menus live in `/config/menus`, the daemon's actual TFTP root.
`/assets` is a separate HTTP/NFS store; an empty asset directory does not prevent
using the remote netboot.xyz menus.

---

## Prerequisites

Use the existing NAS asset share for custom ISOs. Do not change NAS exports or
permissions to troubleshoot firmware/DHCP/TFTP without the required approval.

---

## dnsmasq / DHCP Configuration (gw01)

> **Warning:** These changes must be applied to gw01 (OPNsense). Follow the production safety rules
> in [defaults.instructions.md](../.github/instructions/defaults.instructions.md) — do NOT restart
> services without explicit approval. Test with `drill` after each change.

The following are raw dnsmasq examples, not instructions to replace the gateway's
managed configuration. Use OPNsense's **Services → Dnsmasq DNS & DHCP** boot/tag
settings and preserve the existing DHCP ranges. Keep both the managed Servername
and Server address fields populated with the boot VIP; omitting the address can
make clients request TFTP from the gateway instead.

```conf
# ── netboot.xyz PXE Boot ──────────────────────────────────────────────────────
# LoadBalancer IP for the netboot.xyz TFTP+HTTP service
# Update this value if the IP changes (check kubernetes/apps/network/netboot-xyz/app/helmrelease.yaml)

# UEFI-only deployment — legacy BIOS devices are not expected in this environment.
# The line below serves undionly.kpxe for any legacy/unknown arch devices as a fallback;
# remove it entirely if you want strict UEFI-only behaviour.
dhcp-boot=tag:!uefi,undionly.kpxe,,192.168.69.131

# x86-64 UEFI — standard EFI boot
dhcp-match=set:efi-x86_64,option:client-arch,7
dhcp-match=set:efi-x86_64,option:client-arch,9
dhcp-boot=tag:efi-x86_64,netboot.xyz.efi,,192.168.69.131

# ARM64 UEFI — Raspberry Pi 4/5 with UEFI firmware, ARM servers
dhcp-match=set:efi-arm64,option:client-arch,11
dhcp-boot=tag:efi-arm64,netboot.xyz-arm64.efi,,192.168.69.131

# Secure Boot / HTTPS boot variant (optional — requires CA trust in firmware)
# dhcp-match=set:efi-x86_64-http,option:client-arch,16
# dhcp-boot=tag:efi-x86_64-http,http://192.168.69.131/netboot.xyz.efi

# ── Optional: tag specific MAC ranges for different behavior ──────────────────
# Example: always boot Talos nodes to iPXE (override with Talos image URL)
# dhcp-mac=set:talos-nodes,38:ea:a7:*:*:*
# dhcp-mac=set:talos-nodes,8c:dc:d4:*:*:*
# dhcp-mac=set:talos-nodes,00:11:0a:*:*:*
# dhcp-boot=tag:talos-nodes,netboot.xyz.efi,,192.168.69.131
```

### VLAN-specific considerations

If nodes are on multiple VLANs, the DHCP configuration may need to be per-interface.
OPNsense's DHCP service runs per-interface, so add the boot options to each VLAN
where PXE booting is required (e.g., Server VLAN 42, Management VLAN 99).

---

## Raspberry Pi PXE Booting

Pi 4's EEPROM network boot is not the same as ARM64 UEFI PXE. Its first stage
requests Raspberry Pi firmware files; it cannot directly execute
`netboot.xyz-arm64.efi`. A UEFI firmware stage is required before using that EFI
loader. Restrict any unattended lab-install policy to the four lab devices, never
to the production Talos nodes.

### Enable network boot on Pi

```bash
# On the Pi (Raspberry Pi OS):
sudo raspi-config
# Advanced Options → Boot Order → Network Boot
# Or directly:
sudo rpi-eeprom-config --edit
# BOOT_ORDER is read right to left:
# 0xf142 tries network, USB mass storage, SD, then repeats.
# 0xf21 tries SD, network, then repeats; it does NOT include USB boot.
```

If network boot is not already enabled, this is a one-time EEPROM provisioning
step using a working OS or recovery medium. Network boot can avoid SD-card
interaction for subsequent installations; it cannot remotely change the boot
order of an unpowered board that never attempts network boot.

### Raspberry Pi firmware PXE files

Raspberry Pi firmware requires specific files to be present on the TFTP server.
For headless native network boot, stage the complete appropriate firmware package
in `/config/menus` at 192.168.69.131, rather than only an EFI executable. Pi 4 uses
its EEPROM instead of Pi 3's `bootcode.bin`. Required files depend on the selected
native Talos overlay or UEFI package.

The default `TFTP_PREFIX=0` uses an eight-character serial-number directory and
falls back to the root when firmware is absent there. `TFTP_PREFIX=2` uses a
hyphenated MAC directory such as `dc-a6-32-01-36-c2/`; it is not a colonless MAC
directory by default.

For the UEFI path, use the complete [Pi 4 UEFI firmware](https://github.com/pftf/RPi4)
package, including its Raspberry Pi firmware and `RPI_EFI.fd`. Once the firmware
stage runs, UEFI can load `netboot.xyz-arm64.efi` using the ARM64 DHCP class.
The firmware's default 3 GB RAM limit and USB/DMA compatibility also need validation
before promising a Talos USB-SSD installation.

For native Talos Pi images, use the `rpi_generic` overlay described in the
[Talos boot-assets guide](https://docs.siderolabs.com/talos/v1.14/platform-specific-installations/boot-assets).
Do not substitute a generic ARM64 image for the board-specific firmware stage.

### Isolated four-Pi playground

The reproducible preparation tool is `labs/raspberry-pi/lab.py`. This directory is
**outside production Flux discovery**. It does not import production Talos secrets,
bootstrap production workloads, change gateway DHCP, or write any disk. The native
boot route uses complete Raspberry Pi firmware, an ARM64 Linux kernel and initramfs;
it does not require the separate pftf UEFI stage.

Pinned boot recipe: **Talos v1.14.5**, Image Factory `rpi_generic`, and the matching
**sbc-raspberrypi v0.2.2** overlay. The newer overlay release must not be substituted
without consulting the Talos release's `ghcr.io/siderolabs/overlays` manifest.
The tool checks the ARM64 kernel header, pins the firmware OCI digest, and records
checksums for all boot files. Talos v1.14's `kernel-arm64` is an EFI zboot wrapper,
not a ROM-loadable kernel: the tool reads its Linux zboot header and uses `zstd`
to extract and verify the actual native ARM64 `Image`. It never hands the EFI
wrapper to the Pi ROM. Install prerequisites are Python 3.11+, `curl`, `crane`,
`zstd`, `kubectl` and the matching `talosctl`.

Run commands from the repository root:

```bash
python3 -m unittest discover -s labs/raspberry-pi -p 'test_*.py'
python3 labs/raspberry-pi/lab.py assets
python3 labs/raspberry-pi/lab.py configs
```

All downloaded assets, node inventory, disk/EEPROM evidence, **PKI and rendered
configuration** stay in ignored `labs/raspberry-pi/.state/` (directory mode 0700,
secret files 0600). Back up the private lab PKI through the approved secret backup
mechanism before relying on the cluster. Never commit it, upload it to general
memory, or copy it to a TFTP/HTTP root.

Create `.state/inventory.json` privately from the exact NetBox/DHCP records:
four keys `pi01`–`pi04`, each with `ip` and wired `mac`. Only the four reserved
addresses are accepted. Optional `serial` is the **measured board serial**, never
derived from its MAC. The preparation tool deliberately does not publish this
private identity inventory.

```bash
# Use only an already-established SSH identity; do not guess usernames/passwords.
python3 labs/raspberry-pi/lab.py inspect pi04 --user '<known-user>'
# Upload only new, allowlisted MAC/verified-serial directories to the existing PVC.
KUBECONFIG=./kubeconfig python3 labs/raspberry-pi/lab.py stage
python3 labs/raspberry-pi/lab.py verify
```

`stage` preserves the existing menus, daemon configuration, image, PVC and VIP, and
refuses to overwrite any existing board directory. No root-level `start4.elf`,
`config.txt`, default iPXE policy, DHCP override or auto-install config is created.
The existing daemon's `tftp-single-port` setting remains required. Firmware and
maintenance-mode Talos are available only under the allowlisted board prefixes.
A failed/partial upload requires inspection of those exact directories before
retrying; never delete the whole menu tree.

For MAC directories, EEPROM must already include network boot and `TFTP_PREFIX=2`.
Alternatively, a **verified** serial directory supports `TFTP_PREFIX=0`. With
neither a running OS nor network-enabled EEPROM, a one-time attended recovery/OS
boot is still necessary. Do not change switch/PoE state or gateway DHCP to work
around that gate. An SSH host-key change is also a gate: independently verify the
new key rather than disabling strict checking or deleting the old trust record.
For blank-SSD installation followed by normal local boot, `BOOT_ORDER=0xf124`
tries **USB, network, SD, repeat**. Leaving network first (`0xf142`) creates an
unnecessary boot-server dependency after installation; confirm the intended
post-install USB-first order on each board.

The standalone lab identity is `pi-playground`, with planned control planes
`pi01`–`pi03`, worker `pi04`, API `https://192.168.42.21:6443`, pod network
`10.142.0.0/16`, service network `10.143.0.0/16`, and domain `lab.cluster.local`.
Talos v1.14 typed configuration documents are used; legacy `machine.network` and
`cluster.network` patches conflict with generated v1.14 defaults.
Cluster discovery is disabled. Templates intentionally name the impossible
`/dev/LAB_DISK_NOT_VERIFIED` target. RAM capacity/topology and USB compatibility
must be measured before installation.

After read-only inspection, `configure NODE --disk-serial '<measured-serial>'`
creates a node-specific config **only** for a blank, unmounted, unpartitioned
240 GB-class USB disk with a successful empty `wipefs --no-act` report. Old disk
evidence, mounted OS disks, unknown serials, existing signatures and production
addresses are rejected. This is not permission to clear existing data.

Before any `talosctl apply-config --insecure`, verify the maintenance API's board
MAC and disk serial against that evidence. Apply only the corresponding private
node config, with explicit node/endpoint and the private lab `talosconfig`.
Bootstrap **pi01 once**, obtain the kubeconfig into `.state/`, then verify API
`/readyz`, all intended nodes Ready and three healthy etcd members. Do not install
pi04 until an independently booted replacement/control-plane path is verified;
its current desktop OS is the bootstrap lifeline. No production kubeconfig,
Talos client context, nodes, NAS disks or production Flux bootstrap belong here.

---

## Custom Boot Menus

netboot.xyz supports fully custom iPXE menus. Custom menus are stored in the config PVC
at `/config/menus/` and mounted in the container.

### Adding a custom Talos PXE menu

Custom Talos boot assets are available from the [Talos Image Factory](https://factory.talos.dev/).
The kernel/initrd example below is not proof of a Secure Boot chain. A signed
installer on disk does not sign an unsigned iPXE loader. Do not disable production
Secure Boot to make a lab menu work. Upstream netboot.xyz's signed-shim support is
distribution-specific; verify the entire selected chain separately.

```
# Example non-Secure-Boot local.ipxe entry
# Store this in the netboot.xyz web UI under "Custom Options"

:talos_custom
echo Booting Talos Linux...
# Replace <SCHEMATIC_ID> with your Image Factory schematic and <TALOS_VERSION>
# with the version defined in talos/machineconfig.yaml.j2 (e.g. v1.13.0)
# See: https://factory.talos.dev
set base-url https://factory.talos.dev/image/<SCHEMATIC_ID>/<TALOS_VERSION>
kernel ${base-url}/kernel-amd64 talos.platform=metal
initrd ${base-url}/initramfs-amd64.xz
boot
```

### Adding local ISOs (NAS-hosted)

Large ISOs (Windows, Proxmox, etc.) should be stored on the NAS:

```bash
# Copy to NAS netboot share
rsync -avh WindowsServer2022.iso nas02.in.homeops.ca:/volume1/netboot/isos/
rsync -avh proxmox-ve_8.x-1.iso nas02.in.homeops.ca:/volume1/netboot/isos/
```

In the netboot.xyz web UI, add a custom entry pointing to the local HTTP server:

```
# ISO served via HTTP from pod's /assets (NAS NFS mount)
set iso-base http://192.168.69.131/assets/isos
```

---

## SecureBoot Compatibility

netboot.xyz supports SecureBoot-aware booting:

- **x86-64 UEFI with SecureBoot:** Use `netboot.xyz-snp-efi` (signed by known CAs)
- **Custom Secure Boot keys:** Future work — generate custom PK/KEK/db keys and enroll in firmware
- **Talos with SecureBoot:** The Talos Image Factory can produce SecureBoot-signed images;
  chain-load from netboot.xyz to the signed kernel/initrd

### Current Talos nodes (SecureBoot status)

The Talos nodes (k8s01-06) should maintain SecureBoot functionality during re-imaging.
When re-imaging via PXE:

1. Boot the node to netboot.xyz (via the dnsmasq config above)
2. Select **Talos Linux → Custom Talos** from the menu
3. Use the Talos Image Factory URL for the specific schematic that includes SecureBoot signing
4. After booting, apply the rendered config: `just talos apply`

---

## Re-imaging Workflow (PXE)

### Re-imaging a Talos control plane node

1. **Wipe the node first** (if running):

    ```bash
    talosctl reset --graceful=false --wipe-mode=all --reboot \
      --nodes <ip> --endpoints <ip>
    ```

2. **Node reboots and network-boots** → netboot.xyz menu appears

3. **Select the Talos boot option** from the menu (or use a pre-configured local.ipxe entry)

4. **Wait for maintenance mode:**

    ```bash
    timeout 3 bash -c "echo >/dev/tcp/<ip>/50000" && echo "READY"
    ```

5. **Apply config:**
    ```bash
    just talos apply
    ```

### Re-imaging a worker node

Same steps, but use the worker-specific config. Worker nodes do NOT need `talosctl bootstrap`.

---

## Supported OS/Distros via netboot.xyz

netboot.xyz includes built-in entries for:

| OS              | UEFI x86-64               | ARM64      |
| --------------- | ------------------------- | ---------- |
| Talos Linux     | ✓ (via custom entry)      | ✓          |
| Proxmox VE      | ✓                         | —          |
| Ubuntu (LTS)    | ✓                         | ✓          |
| Debian          | ✓                         | ✓          |
| Fedora / RHEL   | ✓                         | ✓          |
| OPNsense        | ✓ (use local ISO)         | —          |
| Windows         | ✓ (via Wimboot/local ISO) | —          |
| Raspberry Pi OS | —                         | ✓ (custom) |
| memtest86+      | ✓                         | —          |
| SystemRescue    | ✓                         | ✓          |
| GParted Live    | ✓                         | —          |

---

## Future Considerations

- **Custom Secure Boot keys:** Generate PK/KEK/db with openssl, enroll in firmware, sign custom
  kernels/bootloaders. Use `sbsign`, `pesign`, and `efitools`.
- **Disk encryption:** Integrate with Clevis/Tang or TPM2-based auto-unlock after PXE boot.
- **Kea DHCP:** If migrating from dnsmasq to Kea, the PXE options map to:
    - `next-server: 192.168.69.131` (siaddr)
    - `boot-file-name: netboot.xyz.efi` (option 67)
    - Option 93 (client-system-architecture) handling for multi-arch
- **Pi-hole / alternative dnsmasq:** All dnsmasq options above are standard; minimal adaptation needed.
- **BIND:** Use `allow-query` + TSIG zones; PXE handled via DHCP server (separate from BIND).

---

## Troubleshooting

### Node doesn't PXE boot

1. Verify DHCP server is serving boot options:

    ```bash
    # From fw01:
    tcpdump -i <interface> port 67 or port 68
    ```

2. Verify TFTP is reachable:

    ```bash
    # From any host on the same VLAN:
    tftp 192.168.69.131 -c get netboot.xyz.efi
    ```

3. Check the netboot.xyz pod logs:

    ```bash
    kubectl -n network logs -l app.kubernetes.io/name=netboot-xyz
    ```

4. Verify the LoadBalancer IP is assigned:
    ```bash
    kubectl -n network get svc netboot-xyz-boot
    ```

### TFTP timeout / no response

- Ensure `externalTrafficPolicy: Local` is set (it is) — verify the pod is scheduled on a node
  that is reachable from the booting client
- Check Cilium BGP is advertising `192.168.69.131/32` to the router:
    ```bash
    kubectl -n kube-system exec -it ds/cilium -- cilium bgp routes advertised ipv4 unicast
    ```

### ARM64 / Raspberry Pi not booting

- The ARM64 DHCP match (`option:client-arch,11`) applies **after UEFI**, not to the
  Pi's initial EEPROM/firmware exchange.
- For native Pi 4 boot, verify network-enabled EEPROM and the actual
  `TFTP_PREFIX` value. Firmware-specific files belong under
  `/config/menus/<hyphenated-mac>/` or the measured eight-character serial prefix.
- Confirm target MACs in current DHCP/ARP and switch MAC tables. NetBox cable
  records and switch port labels can be stale; neither proves live board identity.
- A powered PoE HAT is not proof of network boot. Link-down, missing DHCP and no
  firmware requests require board/cable/EEPROM diagnosis, not a global PXE override.

### SecureBoot rejection

- If the firmware rejects the netboot.xyz EFI binary, enroll the netboot.xyz CA certificate
  in the UEFI firmware's `db` key database
- Or use `netboot.xyz-snp-efi` which is signed by a known CA
