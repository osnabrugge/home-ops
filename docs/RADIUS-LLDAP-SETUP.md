# RADIUS / LLDAP Integration Guide — OPNsense, Omada, Synology

How to point network infrastructure at the home-ops identity stack so users log in
with their **LLDAP** credentials. This document is **configuration only** — apply the
changes to each device yourself (production infra, no automated changes).

---

## 1. Architecture & account model

```
            ┌─────────────┐   RADIUS (UDP 1812/1813)   ┌──────────────┐
  OPNsense ─┤             ├───────────────────────────►│              │
  Omada   ──┤  device     │                            │ FreeRADIUS   │── LDAP ──┐
  Synology ─┤  (NAS)      │                            │ 192.168.69.132│         │
            └─────────────┘                            └──────────────┘         ▼
                                                                          ┌────────────┐
                                                                          │   LLDAP    │
                                                                          │ dc=homeops │
                                                                          │   ,dc=ca   │
                                                                          └────────────┘
```

- **FreeRADIUS is the integration hub.** It is the only identity service exposed on the
  LAN (`192.168.69.132`, UDP `1812` auth / `1813` accounting). It binds to LLDAP and
  validates user passwords + group membership.
- **LLDAP is NOT exposed off-cluster** (ClusterIP `3890`/`17170`). Devices must NOT try to
  bind LDAP directly unless you explicitly expose it (see §5 for Synology).
- **Only members of `radius-users` can authenticate via RADIUS** (WiFi, VPN, device login).

### Account convention (per request)

| Account      | Purpose            | LLDAP groups                                  |
|--------------|--------------------|-----------------------------------------------|
| `sean-admin` | All admin access   | `admins`, `lldap_admin`, `radius-users`, `users` |
| `sean`       | Regular user + WiFi| `users`, `radius-users`, `remote`             |

> ⚠️ **Action needed in LLDAP:** `sean` is currently **also** in `admins` and
> `lldap_admin`. To match "sean = regular user", remove `sean` from those two groups —
> **but first confirm you can log in as `sean-admin`** so you don't lock yourself out of
> admin UIs. Command to demote (run after verifying `sean-admin`):
>
> ```sh
> # port-forward LLDAP, login as admin, then removeUserFromGroup for groups 4 (admins) and 1 (lldap_admin)
> # See docs note in /memories/repo/device-inventory-identity.md for the GraphQL flow.
> ```

---

## 2. Shared secrets (where they live)

RADIUS shared secrets are **per-NAS** and stored in Azure Key Vault (`keyvault-kube`),
injected into FreeRADIUS via the `freeradius-secret` ExternalSecret:

| NAS       | clients.conf source IP | AKV secret key          |
|-----------|------------------------|-------------------------|
| OPNsense  | `192.168.42.1` (VLAN42 CARP VIP) | `NAS_SECRET_OPNSENSE` |
| Omada     | `192.168.69.130`       | `NAS_SECRET_OMADA`      |
| localhost | `127.0.0.1`            | `NAS_SECRET_LOCALHOST`  |

Retrieve a secret value to type into the device UI:

```sh
az keyvault secret show --vault-name keyvault-kube --name NAS_SECRET_OPNSENSE --query value -o tsv
```

> ⚠️ **Source-IP must match.** FreeRADIUS rejects requests whose source IP isn't a
> configured `client {}`. The OPNsense client is `192.168.42.1` (the **CARP VIP**). If
> gw01 sources RADIUS from its interface IP (`192.168.42.2`) instead of the VIP, either
> set OPNsense to source from the VIP, or update the `client opnsense` block in
> `kubernetes/apps/auth/freeradius/app/configmap.yaml` to the real source IP.

---

## 3. OPNsense (gw01) — admin login + VPN via RADIUS

1. **System → Access → Servers → Add**
   - Type: `RADIUS`
   - Hostname or IP: `192.168.69.132`
   - Shared Secret: value of `NAS_SECRET_OPNSENSE`
   - Services offered: `Authentication and Accounting`
   - Authentication port: `1812`, Accounting port: `1813`
   - Authentication protocol: `MSCHAPv2` (fallback `PAP` if MSCHAP fails — note PAP sends
     the password to FreeRADIUS, which is fine on the trusted Servers VLAN)
   - Timeout: `10`
2. **Test:** System → Access → Tester → pick the RADIUS server → log in as `sean-admin`.
3. **Group mapping (optional, for least-privilege):** OPNsense maps RADIUS users to local
   privileges via a matching local **Group** name or a returned `Class` attribute. Create a
   local group (e.g. `admins`) with the desired privileges; FreeRADIUS can return a `Class`
   reply attribute per LLDAP group if you want automatic mapping (add to the `default` site).
4. **Use it:** set the RADIUS server as an authentication source for the WebGUI
   (System → Settings → Administration → Authentication) and/or OpenVPN/IPsec.

> Keep at least one **local** OPNsense admin account as a break-glass fallback.

---

## 4. Omada (controller `192.168.69.130`) — WPA-Enterprise WiFi

1. **Settings → Authentication → RADIUS Profile → Create**
   - Name: `lldap-radius`
   - Auth server IP: `192.168.69.132`, Port: `1812`
   - Auth password (shared secret): value of `NAS_SECRET_OMADA`
   - Accounting server IP: `192.168.69.132`, Port: `1813` (enable accounting)
2. **Settings → Wireless Networks → (SSID) → Security:**
   - Security: `WPA2-Enterprise` (or `WPA2/WPA3-Enterprise`)
   - RADIUS Profile: `lldap-radius`
3. Clients authenticate with their **LLDAP username + password** (must be in
   `radius-users`). `sean` can now join WiFi with his LLDAP creds.
4. **Controller admin via RADIUS** is limited in Omada; keep local Omada admin accounts.
   Use RADIUS primarily for WiFi (802.1X) and captive portal.

---

## 5. Synology — DSM / file shares

Synology DSM authenticates users via **LDAP** (or AD), not RADIUS, for DSM login and file
permissions. Because LLDAP is ClusterIP-only, choose one:

### Option A (recommended for VPN only): RADIUS
If you only need RADIUS for the Synology **VPN Server** or other RADIUS-capable features,
add a NAS client first:

1. Add to `kubernetes/apps/auth/freeradius/app/configmap.yaml` `clients.conf`:
   ```
   client synology {
     ipaddr    = <synology-ip>
     secret    = "$ENV{NAS_SECRET_SYNOLOGY}"
     shortname = synology
     nastype   = other
   }
   ```
2. Add `NAS_SECRET_SYNOLOGY` to AKV `keyvault-kube` and map it in the `freeradius-secret`
   ExternalSecret + `envFrom` in the FreeRADIUS HelmRelease.
3. Point the Synology feature at `192.168.69.132:1812` with that secret.

### Option B (DSM login + SMB users): expose LLDAP via LoadBalancer LDAP
DSM needs to bind LDAP. Expose LLDAP on the LAN with a dedicated LoadBalancer service
(cluster-side, safe — does **not** touch the firewall):

```yaml
# kubernetes/apps/auth/lldap/app/service-lb.yaml (NEW — review before applying)
apiVersion: v1
kind: Service
metadata:
  name: lldap-ldap-lb
  namespace: auth
  annotations:
    lbipam.cilium.io/ips: "192.168.69.133"   # pick a free LB IP
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: lldap
  ports:
    - name: ldap
      port: 3890
      targetPort: 3890
      protocol: TCP
```

Then in DSM: **Control Panel → Domain/LDAP → LDAP**
- Server Address: `192.168.69.133`
- Encryption: `None` (LLDAP serves plain LDAP on 3890 on the trusted Servers VLAN) — or
  enable StartTLS if configured.
- Base DN: `dc=homeops,dc=ca`
- Bind DN: `uid=sean-admin,ou=people,dc=homeops,dc=ca` (or a dedicated read-only service
  account)

> ⚠️ Synology expects POSIX-style schema (`posixAccount`/`posixGroup`, uid/gid numbers).
> LLDAP advertises a compatible schema, but verify users/groups appear under
> **Control Panel → User/LDAP** before relying on it for file permissions. If POSIX
> attributes are missing, keep DSM on local accounts and use RADIUS (Option A) only.

---

## 6. Verification checklist

- [ ] `az keyvault secret show` returns the expected NAS secret.
- [ ] FreeRADIUS reachable: `nc -u -z 192.168.69.132 1812` from the device's VLAN.
- [ ] Test auth: OPNsense Tester / Omada client join / Synology bind succeeds for
      `sean-admin` and `sean`.
- [ ] User is in `radius-users` (already true for `sean` and `sean-admin`).
- [ ] Break-glass local admin retained on every device.
