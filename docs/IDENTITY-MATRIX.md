# Identity & Auth Integration Matrix

## Current migration status (2026-10-26)

The approved target is **Authentik CE + authentik-operator for supported
OAuth2/proxy application resources + native blueprints for the remaining
identity/protocol objects**, with existing FreeRADIUS retained where needed.
See [the current architecture](./AUTH-ARCHITECTURE.md) and
[migration tracker #4738](https://github.com/osnabrugge/home-ops/issues/4738).

The operator and consumer cutovers are queued for a supervised session, not
deployed by this scheduling change. No date is booked. The deployed native
blueprint foundation does not prove a consumer's end-to-end login.

| Consumer                               | Current source evidence                                                                                                  | Migration gate                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Grafana                                | [Active OAuth configuration](../kubernetes/apps/observability/grafana-operator/instance/grafana.yaml) points to Authelia | First consumer canary; preserve user IDs, dashboard ownership and admin/editor/viewer mappings            |
| Proxmox                                | [Authelia client registration](../kubernetes/apps/auth/authelia/app/configmap.yaml) exists                               | Read-only verification of the actual realm, then a separate approved host-change window                   |
| NetBox                                 | [Current app configuration](../kubernetes/apps/observability/netbox/app/helmrelease.yaml) uses LLDAP                     | Choose and verify the actual LDAP/OIDC migration; its Authelia registration is not proof of live OIDC use |
| Omada                                  | [App-owned SAML blueprint](../kubernetes/apps/network/omada-controller/identity/blueprint.yaml) is applied               | Human SSO and physical access02 adoption are separate unverified gates                                    |
| Other LDAP/RADIUS/forward-auth clients | Historical list below is a discovery starting point only                                                                 | Verify live consumers and machine API bypasses before retiring either Authelia or LLDAP                   |

## Historical audit (2026-06-20; not current verification)

The following inventory predates the Authentik decision. Its "working" and
"deployed" labels are historical claims, not evidence that the planned
integrations were completed or still match live configuration. Do not create
new Authelia clients from this legacy plan.

## Legacy identity stack (`auth/`)

| Component      | Role                                                           | Backed by                | State       |
| -------------- | -------------------------------------------------------------- | ------------------------ | ----------- |
| **LLDAP**      | Directory / source of truth — `dc=homeops,dc=ca`, LDAP `:3890` | —                        | ✅ deployed |
| **Authelia**   | Forward-auth **+ OIDC provider** (`auth.homeops.ca`)           | LLDAP (`uid=authelia`)   | ✅ deployed |
| **FreeRADIUS** | RADIUS (`192.168.69.132:1812/1813`)                            | LLDAP (`uid=freeradius`) | ✅ deployed |

OIDC issuer endpoints: `https://auth.homeops.ca/api/oidc/{authorization,token,userinfo}`.
Service accounts already in LLDAP: `admin`, `authelia`, `freeradius`, `netbox`.
(Kanidm is **not** deployed — removed from the repo.)

## Already integrated & working (verified in repo)

| Target          | Method              | Account / client                             | Status                        |
| --------------- | ------------------- | -------------------------------------------- | ----------------------------- |
| NetBox          | native LDAP → LLDAP | `uid=netbox` bind, `cn=admins` superuser     | ✅                            |
| Grafana         | OIDC → Authelia     | client `grafana`, role from `groups`         | ✅                            |
| Proxmox         | OIDC → Authelia     | client `proxmox`, 2FA-external               | ⚠️ verify realm on pve01      |
| Frigate         | OIDC → Authelia     | client `frigate`                             | ⚠️ verify Frigate consumes it |
| OPNsense, Omada | RADIUS → FreeRADIUS | NAS clients `192.168.42.1`, `192.168.69.130` | ✅ defined; verify live auth  |

## Integration plan by tier

### Tier 1 — native OIDC → register Authelia client (preferred)

| App            | OIDC | Notes / issues                                                                               |
| -------------- | ---- | -------------------------------------------------------------------------------------------- |
| autobrr        | ✅   | native OIDC, straightforward                                                                 |
| qui            | ✅   | native OIDC (autobrr project)                                                                |
| seerr          | ⚠️   | fork-dependent (Jellyseerr has OIDC; else Plex login)                                        |
| LibreNMS       | ✅   | supports OIDC **or** LDAP **or** RADIUS — pick one                                           |
| home-assistant | ❌   | **no native OIDC** — needs community add-on / trusted-proxy; conflicts with HA auth. Low ROI |

### Tier 2 — native LDAP → bind to LLDAP (needs service account)

| App       | Service account to bootstrap |
| --------- | ---------------------------- |
| LibreNMS  | `uid=librenms`               |
| thelounge | `uid=thelounge`              |
| NetBox    | `uid=netbox` (exists)        |

### Tier 3 — no native auth → Authelia forward-auth at gateway (no per-app account)

sonarr, radarr, lidarr, bazarr, prowlarr, qbittorrent, sabnzbd, tautulli, mainsail, fluidd, spoolman, slskd, beets, atuin, printstash, netboot-xyz, omada-controller (UI), and similar.

> **Gotcha:** the *arr apps have an **"External" auth method** (trust the proxy) — use it. Forward-auth **must exempt `/api`** paths, or Prowlarr↔arr sync and download clients (API-key based) break.

### Tier 4 — RADIUS → FreeRADIUS (network gear, not pods)

OPNsense (VPN/admin/captive portal), Omada (WPA2-Enterprise WiFi + admin). Already NAS clients.

### No user auth needed

All of `kube-system`, `database`, `cert-manager`, `external-secrets`, `rook-ceph`, `openebs-system`, `volsync-system`, `flux-system`, every `*-exporter`, and operators.

### Special cases

- **Plex** — plex.tv auth only; leave as-is.
- **Mosquitto** — LDAP only via complex go-auth plugin; use static credentials.
- **netbox-diode** — self-contained Ory Hydra OAuth2; leave as-is.

## Next: LLDAP bootstrap framework

Declaratively manage in LLDAP (git + AKV-backed `ExternalSecret` passwords, rebuild-safe):

- **Humans** + group membership (`admins`, `users`).
- **Service-account binds**: existing (`authelia`, `freeradius`, `netbox`) + new (`librenms`, `thelounge`).
- **Groups** for RBAC mapping.

Then wire Tier 2 (LDAP) → Tier 1 (OIDC) → Tier 3 (forward-auth) → Omada/NetBox migrations.
