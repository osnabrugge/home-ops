# Identity & Auth Integration Matrix

## Current migration status (2026-11-12)

The approved target is **Authentik CE + authentik-operator for supported
OAuth2/proxy application resources + native blueprints for the remaining
identity/protocol objects**, with existing FreeRADIUS retained where needed.
See [the current architecture](./AUTH-ARCHITECTURE.md) and
[migration tracker #4738](https://github.com/osnabrugge/home-ops/issues/4738).

The application operator is deployed with a dedicated non-superuser reconciliation
identity. Its private OIDC canary passed normal authentication/consent, PKCE,
signed-token validation, userinfo, denied-principal policy evaluation and real
periodic drift repair. No existing human identity or grant was migrated by those
tests.

Unpackerr v1 is a new operator-managed proxy integration with a group-gated,
internal-only, read-only insights UI. Existing human consumer cutovers still
require account/role/MFA/recovery validation; a technical canary is not that proof.

| Consumer                                                    | Current source evidence                                                                                                                                                           | Migration gate                                                                                                                    |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Grafana                                                     | [Active OAuth configuration](../kubernetes/apps/observability/grafana-operator/instance/grafana.yaml) points to Authelia                                                          | First consumer canary; preserve user IDs, dashboard ownership and admin/editor/viewer mappings                                    |
| Proxmox                                                     | [Authelia client registration](../kubernetes/apps/auth/authelia/app/configmap.yaml) exists                                                                                        | Read-only verification of the actual realm, then a separate approved host-change window                                           |
| NetBox                                                      | [Current app configuration](../kubernetes/apps/observability/netbox/app/helmrelease.yaml) uses LLDAP                                                                              | Choose and verify the actual LDAP/OIDC migration; its Authelia registration is not proof of live OIDC use                         |
| Omada                                                       | [App-owned SAML blueprint](../kubernetes/apps/network/omada-controller/identity/blueprint.yaml) is applied                                                                        | Human SSO and physical access02 adoption are separate unverified gates                                                            |
| PrintStash                                                  | [App-owned native OIDC](../kubernetes/apps/printing/printstash/identity/application.yaml) and [app-only role scope](../kubernetes/apps/auth/authentik/blueprints/printstash.yaml) | Real human sign-in/library check; local recovery and original device ownership remain separate and preserved                      |
| Hubble, netboot.xyz, Prometheus, Alertmanager, VictoriaLogs | [Shared app-owned proxy component](../kubernetes/components/authentik-proxy/README.md), private routes and workload-scoped ingress policies                                       | Human first-use checks; preserve direct cluster Service clients and independent boot/syslog traffic                               |
| Unpackerr                                                   | [App-owned proxy application](../kubernetes/apps/default/unpackerr/identity/application.yaml) is reconciled by authentik-operator                                                 | HTTPS reaches the IdP, backend reads/denials/metrics/WebSocket and ingress policy are verified; human SSO remains to be exercised |
| Other LDAP/RADIUS/forward-auth clients                      | Historical list below is a discovery starting point only                                                                                                                          | Verify live consumers and machine API bypasses before retiring either Authelia or LLDAP                                           |

Grafana's live read-only inventory confirms an existing Generic OAuth account
and a separately verified local administrator recovery path. Preserve that
external account's identity and ownership during issuer migration; do not rely
on the currently enabled insecure email lookup to auto-link it to a new IdP.
Human mapping/login validation was unavailable during the operator rollout, so
the existing Authelia issuer and Grafana consumer configuration remain unchanged.

### Live surface review and remaining gates

The live review includes **81 HTTPRoute objects**, including Helm-generated
routes; the smaller set of explicit route files is not an estate inventory.
This is a staged migration, not a claim that every route or appliance now uses
Authentik.

- **Current Authentik consumers:** the five infrastructure UI proxies above,
  native PrintStash/PDM OIDC, existing Bifrost/Kritika/Radar/Unpackerr proxies,
  and Omada SAML. The existing Unpackerr binding now explicitly includes the
  infrastructure owner; no directory-group membership was added.
- **Legacy consumer cutovers:** Grafana and NetBox retain their current
  Authelia/LLDAP paths until actual identity/role/ownership and recovery checks
  pass. Do not adopt or recreate an existing manual provider without reviewing
  its identity and current owner.
- **Media application routes:** agregarr, autobrr, bazarr, dispatcharr, frigate,
  lidarr, prowlarr, qbittorrent, qui, radarr, seerr, sonarr, tautulli and thelounge
  remain unchanged pending app-specific user/role and API, webhook, stream and
  WebSocket contracts. Do not assume one product's "External" mode or a blanket
  `/api` exception is safe for the others.
- **Printer/camera clients:** Fluidd, Mainsail, Moonraker, camera routes, pgcode,
  PrintGuard and Spoolman retain their current client paths. A browser redirect
  cannot substitute for slicer/device API credentials or physical client
  acceptance. Native login/recovery planes, including LLDAP and the Ceph
  dashboard, also require a separate reviewed cutover.
- **Machine/public contracts:** MCP transports, Flux/Kritika webhooks, Atuin
  sync and Matter/Home Assistant integrations are not browser-only login
  surfaces. Preserve their native authentication. Public status/Kromgo/Echo,
  the public chart catalogue, and Plex's native identity remain intentional;
  Konflate's externally routed tool is unchanged pending its own contract review.
- **Protected appliances:** Proxmox hosts, OPNsense, NAS and network equipment
  retain their native recovery and machine credentials. An application-provider
  declaration is not approval for an appliance reconfiguration.

Anonymous redirects, provider Ready conditions and a technical policy evaluation
do not replace the real user's first login/MFA, resource visibility and recovery
checks. Authelia/LLDAP retirement and global MFA enforcement remain gated.

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

PrintStash's entry in that historical tier is superseded by its native OIDC
integration above. Do not place a browser-only proxy on its paired capture API.

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
