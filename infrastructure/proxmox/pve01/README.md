# pve01 host networking

`interfaces` is a verbatim copy of `/etc/network/interfaces` on **pve01**,
captured 2026-09-23.

## Why this file exists

The 2026-09-22 outage was caused by a change to pve01's host networking (the
OVS -> Linux bond migration). Nothing in this repo captured the before state, so
there was no diff to look at and no known-good config to restore. This copy
closes that gap.

## pve01 is READ-ONLY infrastructure

Do not push this file back to the host, and do not edit pve01's networking,
without explicit sign-off from Sean and a tested rollback. A bad
`/etc/network/interfaces` plus `ifreload -a` will drop the management link and
require physical or IPMI access to recover.

This is a **reference copy for diffing and disaster recovery**, not a source of
truth that anything reconciles from.

## Shape of the config (2026-09-23)

| Interface         | Role                                                                                                                                    |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `bond1`           | 802.3ad over `enlan2` + `enlan3`, static `192.168.99.40/24`, gw `192.168.99.4` — management, and the only link that carries the host IP |
| `vmbr0`           | bridge over `enwan0` (ext01 sfp-sfpplus1) — WAN                                                                                         |
| `vmbr2`           | bridge over `enlan4` (fw01-igb3) — pfsync                                                                                               |
| `bond0` / `vmbr1` | commented out; the Mellanox ports `enp15s0f0np0` / `enp15s0f1np1` are passed through to a guest                                         |

`/etc/network/interfaces.d/sdn` is sourced but was **empty** at capture time, so
it is not tracked here.

## Observation worth chasing (not actioned)

At capture, `enlan4` was `DOWN` / `NO-CARRIER`, so **vmbr2 (pfsync) has no link**.
That is the interface OPNsense HA would sync over — see
`docs/OPNSENSE-HA-GW02.md`. Flagged, not fixed: pve01 is read-only and this may
simply be because gw02 does not exist yet.

## Re-capture

```sh
ssh sean-admin@pve01 'cat /etc/network/interfaces' \
  > infrastructure/proxmox/pve01/interfaces
```

Run this after any deliberate pve01 network change, and commit the diff.
