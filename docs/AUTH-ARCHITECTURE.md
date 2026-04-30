# Centralized Authentication Architecture

## Overview

This document describes the centralized identity and authentication stack for
the homeops.ca infrastructure.  It replaces per-device local accounts with a
single source of truth (LLDAP) fronted by a modern SSO/MFA layer (Authelia)
and a RADIUS backend (FreeRADIUS) for network-level authentication.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Cluster (auth namespace)                    │
│                                                                      │
│  ┌──────────────┐    LDAP/3890    ┌────────────────────────────────┐ │
│  │    LLDAP     │◄───────────────►│  Authelia (SSO/OIDC/MFA)      │ │
│  │  User Dir    │                 │  auth.homeops.ca               │ │
│  │ lldap.homeops│                 │  - TOTP / WebAuthn / Passkeys  │ │
│  └──────┬───────┘                 │  - OIDC provider for apps      │ │
│         │ LDAP/3890               │  - Forward-auth middleware      │ │
│         │                         └────────────────┬───────────────┘ │
│  ┌──────▼───────┐                                  │ OIDC            │
│  │ FreeRADIUS   │                                  │                 │
│  │ 192.168.69.124│                                 ▼                 │
│  │  :1812/:1813  │            Proxmox / Grafana / NetBox / other     │
│  └──────────────┘                                                    │
└──────────────────────────────────────────────────────────────────────┘
        │                         │
        │ RADIUS                  │ LDAP (read-only)
        ▼                         ▼
  OPNsense fw01           Linux / Synology DSM
  Omada WiFi AP
```

---

## Components

### 1. LLDAP — Lightweight LDAP Directory

| Property | Value |
|---|---|
| **URL** | https://lldap.homeops.ca |
| **LDAP** | ldap://lldap.auth.svc.cluster.local:3890 |
| **Base DN** | `dc=homeops,dc=ca` |
| **Admin DN** | `uid=admin,ou=people,dc=homeops,dc=ca` |
| **Namespace** | `auth` |

LLDAP is a small, purpose-built LDAP server with a friendly web UI.  It stores
users and groups in a SQLite database (backed by Ceph block storage via
VolSync).  Services authenticate against it over plain LDAP inside the cluster
(network-isolated; TLS not required on the cluster-internal path but can be
enabled).

**Required service accounts (create in LLDAP web UI after first deploy):**

| Account | Purpose |
|---|---|
| `uid=authelia,ou=people` | Authelia LDAP bind (read-only, group `lldap_strict_readonly`) |
| `uid=freeradius,ou=people` | FreeRADIUS LDAP bind (read-only) |

**Required groups:**

| Group | Members | Purpose |
|---|---|---|
| `admins` | All administrators | Full 2FA policy in Authelia |
| `users` | Regular users | 1FA policy in Authelia |
| `radius-users` | WiFi/VPN users | Permitted RADIUS access |
| `lldap_admin` | Admin accounts | LLDAP management |
| `lldap_strict_readonly` | `authelia`, `freeradius` | Service-account read access |

---

### 2. Authelia — SSO / MFA / OIDC Provider

| Property | Value |
|---|---|
| **URL** | https://auth.homeops.ca |
| **Namespace** | `auth` |
| **Replicas** | 2 (HA) |
| **Session store** | Dragonfly (Redis-compatible), DB index 3 |
| **Persistent storage** | PostgreSQL (`authelia` DB in CNPG `postgres16`) |

Authelia provides:

- **Forward-auth** middleware — Envoy Gateway can redirect unauthenticated
  requests to auth.homeops.ca before forwarding to the backend.  Configure per
  HTTPRoute using `extensionRef` to an `AuthPolicy`.
- **OIDC** — acts as an OpenID Connect Identity Provider for apps that support
  OAuth2/OIDC (Proxmox, Grafana, NetBox, etc.).
- **MFA** — supports TOTP, WebAuthn/FIDO2 passkeys, and Duo Push.

#### OIDC Client Registration

Pre-registered clients (secrets stored in Azure Key Vault under the `authelia`
secret key):

| Client ID | App | Policy | Redirect URI |
|---|---|---|---|
| `proxmox` | Proxmox VE | two_factor | `https://proxmox.homeops.ca` |
| `grafana` | Grafana | one_factor | `https://grafana.homeops.ca/login/generic_oauth` |
| `netbox` | NetBox IPAM | one_factor | `https://netbox.homeops.ca/oidc/callback/` |

Add new clients by editing
`kubernetes/apps/auth/authelia/app/configmap.yaml` and adding the client secret
to the `authelia` AKV secret.

#### Proxmox OIDC Setup

In Proxmox **Datacenter → Realms → Add → OpenID Connect**:

| Field | Value |
|---|---|
| Realm | `authelia` |
| Issuer URL | `https://auth.homeops.ca` |
| Client ID | `proxmox` |
| Client Key | `<AUTHELIA_OIDC_CLIENT_PROXMOX_SECRET from AKV>` |
| Username Claim | `preferred_username` |
| Default Groups | (map via group-sync or set manually) |
| Autocreate Users | enabled (first login) |

#### Grafana OIDC Setup

In Grafana `grafana.ini` / `[auth.generic_oauth]`:

```ini
[auth.generic_oauth]
enabled           = true
name              = Authelia
icon              = signin
client_id         = grafana
client_secret     = ${AUTHELIA_OIDC_CLIENT_GRAFANA_SECRET}
scopes            = openid profile email groups
auth_url          = https://auth.homeops.ca/api/oidc/authorization
token_url         = https://auth.homeops.ca/api/oidc/token
api_url           = https://auth.homeops.ca/api/oidc/userinfo
role_attribute_path = contains(groups[*], 'admins') && 'Admin' || 'Viewer'
```

#### Synology DSM OIDC Setup

DSM 7.1+ supports OIDC natively under **Control Panel → Domain/LDAP → SSO Client**:

| Field | Value |
|---|---|
| Profile | OpenID Connect |
| Account type | domain/local |
| Name | homeops Authelia |
| Well-Known URL | `https://auth.homeops.ca/.well-known/openid-configuration` |
| Application ID | (new client — register in configmap.yaml) |
| Application Secret | (from AKV) |

---

### 3. FreeRADIUS — RADIUS for Network Devices

| Property | Value |
|---|---|
| **LoadBalancer IP** | 192.168.69.124 |
| **Auth port** | 1812/UDP |
| **Acct port** | 1813/UDP |
| **Backend** | LLDAP via LDAP |
| **Namespace** | `auth` |

FreeRADIUS enables:

- **OPNsense admin auth** — validate firewall admin logins against LLDAP
- **Omada WPA-Enterprise (802.1X)** — per-user WiFi passwords; no shared PSK
- **VLAN assignment** — return `Tunnel-Private-Group-Id` attributes to put users
  on the correct VLAN

#### OPNsense RADIUS Setup

1. **System → Access → Servers → Add**
   - Type: `RADIUS`
   - Hostname: `192.168.69.124`
   - Auth Port: `1812`
   - Shared Secret: `<FREERADIUS_NAS_SECRET_OPNSENSE from AKV>`
   - Services: Authentication
2. **System → Access → Users** — Set the default auth source to RADIUS.

#### Omada WPA-Enterprise Setup

1. In Omada **Settings → Profiles → RADIUS Profile → Create**:
   - Auth Server IP: `192.168.69.124`
   - Auth Port: `1812`
   - Auth Password: `<FREERADIUS_NAS_SECRET_OMADA from AKV>`
2. Edit the secured SSID → **Security** → set to `WPA-Enterprise` and select
   the RADIUS profile above.
3. Users on the `radius-users` LLDAP group will be able to log in with their
   LLDAP username and password.

#### VLAN Assignment (optional)

Add RADIUS attributes to LLDAP user profiles or group-based policies in
`freeradius-config` to return `Tunnel-Type`, `Tunnel-Medium-Type`, and
`Tunnel-Private-Group-Id` for automatic VLAN placement.

---

## SSH Key Management

LLDAP stores the `sshPublicKey` attribute per user (OpenLDAP `ldapPublicKey`
schema).  Linux hosts can query LLDAP at login to fetch authorized keys using
`sss_ssh_authorizedkeys` (from `sssd`) or a small `AuthorizedKeysCommand`
script.

### SSSD integration (Talos nodes / Linux desktops)

```ini
# /etc/sssd/sssd.conf
[sssd]
services = nss, pam, ssh
domains  = homeops.ca

[domain/homeops.ca]
id_provider     = ldap
auth_provider   = ldap
ldap_uri        = ldap://lldap.auth.svc.cluster.local:3890
ldap_search_base = dc=homeops,dc=ca
ldap_user_search_base  = ou=people,dc=homeops,dc=ca
ldap_group_search_base = ou=groups,dc=homeops,dc=ca
ldap_default_bind_dn   = uid=sssd,ou=people,dc=homeops,dc=ca
ldap_default_authtok   = <service-account-password>
ldap_user_ssh_public_key = sshPublicKey

[ssh]
ssh_authorizedkeys_command = /usr/bin/sss_ssh_authorizedkeys
```

In `/etc/ssh/sshd_config`:

```
AuthorizedKeysCommand    /usr/bin/sss_ssh_authorizedkeys %u
AuthorizedKeysCommandUser nobody
```

---

## Guest WiFi

Two approaches; both can coexist:

### Option A — Omada Voucher Portal (current)

Keep the existing Omada captive portal voucher system for guests.  No changes
needed; RADIUS is only used for the secured employee/IoT SSIDs.

### Option B — Authelia Guest Accounts

Create a restricted LLDAP group `guests` and issue time-limited LLDAP accounts.
Authelia enforces `one_factor` for this group and the guest SSID uses
WPA-Enterprise pointing at FreeRADIUS.

**Recommendation:** Keep Option A for casual guests; use Option B for
contractors or temporary workers who need network + service access under their
own identity (audit trail).

---

## Remote Access (WireGuard + MFA)

WireGuard provides the VPN tunnel; Authelia adds MFA enforcement at the
application layer.

```
External User
  └─► WireGuard endpoint (fw01 or dedicated pod)
        └─► Cluster internal network
              └─► Application (protected by Authelia forward-auth)
```

### Option A — WireGuard on OPNsense fw01

- **WireGuard** plugin already supported by OPNsense.
- Each user gets a WireGuard keypair and a static IP in the VPN range.
- After connecting, HTTPS app access still goes through Authelia for MFA.
- **Pros:** Firewall-native; no extra cluster components.
- **Cons:** Keys managed manually on fw01; no LDAP integration for WireGuard
  itself (WireGuard is key-based, not password-based).

### Option B — WireGuard-as-Kubernetes-workload (wg-easy or Netbird)

Deploy a self-hosted WireGuard management UI (e.g., `wg-easy`) as a cluster
app behind Authelia forward-auth.  Users log in via Authelia (TOTP/passkey),
then receive their WireGuard config.

- **Pros:** Web-managed keys; OIDC login for self-service.
- **Cons:** Extra cluster component; needs a LoadBalancer IP for the WireGuard
  UDP port.

**Recommendation:** Start with Option A (fw01 WireGuard) since OPNsense support
is built-in and requires no new cluster services.  Migrate to Option B if
self-service key management becomes a requirement.

---

## Azure AD / M365 Considerations

Even though Azure AD is explicitly **not** the primary identity provider for
local infrastructure, there are valid integration points:

| Scenario | Approach |
|---|---|
| Azure Key Vault secrets | Already implemented — ExternalSecrets operator pulls from AKV |
| M365 SSO for web apps | Configure Authelia as SAML SP or use Entra External ID as an upstream OIDC provider to Authelia (Authelia → Entra OpenID Connect upstream) |
| Conditional Access | Keep Entra for M365/Azure-only workloads; don't route local-infra auth through cloud |
| Cold-tier backup auth | Use AKV for emergency break-glass credentials only |

To federate Authelia ↔ Entra ID (optional):

```yaml
# In authelia/app/configmap.yaml — add under identity_providers.oidc.cors
# or under a future "upstream" OIDC block (Authelia 4.39+)
identity_providers:
  oidc:
    # ... existing config
# Upstream / social login support requires Authelia 4.39+
# See: https://www.authelia.com/configuration/identity-providers/openid-connect/provider/
```

---

## Azure Key Vault — Required Secrets

All secrets are stored in the `keyvault-kube` AKV under two secret objects:
`lldap` and `authelia` and `freeradius`.

### `lldap` secret (JSON blob)

```json
{
  "LLDAP_LDAP_USER_PASS":    "<lldap admin password — 32+ char>",
  "LLDAP_JWT_SECRET":        "<random hex, 32+ bytes>",
  "LLDAP_KEY_SEED":          "<random hex, 32+ bytes>",
  "LLDAP_SMTP_PASSWORD":     "<smtp-relay password if required>"
}
```

### `authelia` secret (JSON blob)

```json
{
  "AUTHELIA_OIDC_HMAC_SECRET":              "<random hex, 32+ bytes>",
  "AUTHELIA_OIDC_ISSUER_PRIVATE_KEY":       "<RSA-4096 PEM private key>",
  "AUTHELIA_JWT_SECRET":                    "<random hex, 32+ bytes>",
  "AUTHELIA_SESSION_SECRET":                "<random hex, 32+ bytes>",
  "AUTHELIA_STORAGE_ENCRYPTION_KEY":        "<random hex, 32+ bytes>",
  "AUTHELIA_DB_PASSWORD":                   "<postgres authelia user password>",
  "AUTHELIA_LDAP_PASSWORD":                 "<authelia LLDAP service account password>",
  "AUTHELIA_SMTP_PASSWORD":                 "<smtp relay password if required>",
  "AUTHELIA_OIDC_CLIENT_PROXMOX_SECRET":    "<random hex, 32+ bytes>",
  "AUTHELIA_OIDC_CLIENT_GRAFANA_SECRET":    "<random hex, 32+ bytes>",
  "AUTHELIA_OIDC_CLIENT_NETBOX_SECRET":     "<random hex, 32+ bytes>"
}
```

### `freeradius` secret (JSON blob)

```json
{
  "FREERADIUS_LDAP_PASSWORD":      "<freeradius LLDAP service account password>",
  "FREERADIUS_NAS_SECRET_OPNSENSE": "<shared secret for OPNsense, 16+ chars>",
  "FREERADIUS_NAS_SECRET_OMADA":    "<shared secret for Omada, 16+ chars>"
}
```

### Generating secrets

```bash
# Random hex (32 bytes)
openssl rand -hex 32

# RSA-4096 key for OIDC
openssl genrsa -out oidc.key 4096
cat oidc.key  # paste as AUTHELIA_OIDC_ISSUER_PRIVATE_KEY

# Upload to AKV
az keyvault secret set \
  --vault-name keyvault-kube \
  --name lldap \
  --value "$(cat lldap.json)"
```

---

## First-Deploy Bootstrap Checklist

1. **Create AKV secrets** (see above) before Flux reconciles the manifests.
2. **Create PostgreSQL database** for Authelia:
   ```bash
   kubectl exec -n database \
     $(kubectl get pod -n database -l cnpg.io/cluster=postgres16,cnpg.io/instanceRole=primary -o name) \
     -- psql -U postgres -c "CREATE DATABASE authelia; CREATE USER authelia WITH PASSWORD '<AUTHELIA_DB_PASSWORD>'; GRANT ALL ON DATABASE authelia TO authelia;"
   ```
3. **Deploy LLDAP** first (authelia + freeradius depend on it).
4. **Create LLDAP service accounts** via the LLDAP web UI:
   - `authelia` (member of `lldap_strict_readonly`)
   - `freeradius` (member of `lldap_strict_readonly`)
   - `sssd` (member of `lldap_strict_readonly`, for Linux host integration)
5. **Create LLDAP groups**: `admins`, `users`, `radius-users`, `guests`.
6. **Deploy Authelia** — verify at https://auth.homeops.ca.
7. **Deploy FreeRADIUS** — test with:
   ```bash
   kubectl exec -n auth deploy/freeradius -- \
     radtest <lldap-username> <password> 127.0.0.1 0 <NAS_SECRET_OPNSENSE>
   ```
8. **Configure OPNsense** RADIUS server (see above).
9. **Configure Omada** WPA-Enterprise SSID (see above).
10. **Add Proxmox/Grafana/NetBox OIDC** realms (see above).
11. **Test SSH key auth** on a Linux host with SSSD.

---

## Related Issues / Tracking

- **Issue #3064** — Centralized auth for device access
- **Issue #3054** — VLAN interfaces (dependency for Talos→LLDAP connectivity)
- `docs/OOB-MANAGEMENT.md` — references Authelia/LLDAP for PiKVM SSO
