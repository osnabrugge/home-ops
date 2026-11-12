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
| Omada                                                       | [App-owned SAML blueprint](../kubernetes/apps/network/omada-controller/identity/blueprint.yaml) is applied                                                                        | SSO currently fails; confirm the controller's SAML group/role and application entitlement before claiming it commissioned         |
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

### Protected appliance handoff

An Authentik blueprint configures the identity-provider side, not the appliance.
Keep local recovery accounts and machine/API credentials; appliance changes need
an approved window, saved configuration and a checked rollback.

- **Synology DS1821+, DSM 7.4.1:** use native OIDC under **Control Panel >
  Domain/LDAP > SSO Client**. The app-owned provider needs RSA/RS256 signing,
  `openid profile email`, and `preferred_username` matching an existing DSM
  account exactly. DSM does not create that account. Confirm the canonical HTTPS
  origin before registering its strict redirect URI; do not append `#/signin`.
  A username override belongs in this application's profile mapping, not a
  global identity rename. See the [Synology integration guide](https://integrations.goauthentik.io/infrastructure/synology-dsm/).
- **TrueNAS Community Edition 25.10.8:** do not change directory services merely to add browser SSO.
  The [25.10 administrator guide](https://www.truenas.com/docs/scale/25.10/scaletutorials/credentials/adminroles/#allowing-directory-service-users-webui-access)
  documents directory WebUI access as Enterprise-only with AD privileges.
  Generic LDAP is not an AD/SMB replacement, and an Authentik reverse-proxy gate
  would not replace TrueNAS's own login. Any file-identity migration must
  preserve UID/GID/SID and dataset ACL mappings and first pass an isolated test.
- **OPNsense 26.7:** native LDAP authentication still needs local GUI privileges.
  Configure an encrypted LDAP server and trusted CA under **System > Access >
  Servers**, verify **Access > Tester**, then map only the intended local
  user/group privileges before changing the GUI authentication selection.
  Authentik's username attribute is `cn`, not the AD example's `sAMAccountName`.
  Retain Local Database recovery and existing VPN/RADIUS/API contracts.
  See the [OPNsense LDAP guide](https://docs.opnsense.org/manual/how-tos/user-ldap.html).

### NAS01 BMC LDAP prerequisites

NAS01's X11DPH-T BMC reports firmware 1.74. The existing
`ak-outpost-ldap.auth.svc.cluster.local` exposes LDAP/LDAPS inside the cluster
only. `ldap.homeops.ca` currently resolves to the HTTP gateway, with no working
LAN listener on port 636. Do not enter that address in the BMC and assume the
directory is commissioned.

The GitOps prerequisites are a private LDAPS endpoint and IPv4 DNS, a certificate
the BMC can validate, narrowly scoped network access, and a dedicated
provider/application plus bind identity. Give that identity only the required
provider-scoped directory-search permission; keep its credential out of Git.
Prefer direct bind for privileged hardware access rather than the existing
shared provider's cached-bind behavior.

For an approved dedicated provider, the following is a **proposed, not deployed**
DN layout rooted under the existing directory:

| BMC LDAP field   | Planned value                                                         |
| ---------------- | --------------------------------------------------------------------- |
| Authentication   | LDAP enabled, SSL enabled; not Active Directory                       |
| Server           | Dedicated private LDAPS endpoint, not the current HTTP-only address   |
| Port             | `636`                                                                 |
| Provider base DN | `OU=nas01-bmc,DC=ldap,DC=goauthentik,DC=io`                           |
| Bind DN          | `cn=svc-nas01-bmc,ou=users,OU=nas01-bmc,DC=ldap,DC=goauthentik,DC=io` |
| Bind password    | Dedicated credential provisioned securely; no API token               |
| Search base      | `ou=users,OU=nas01-bmc,DC=ldap,DC=goauthentik,DC=io`                  |

Confirm this firmware's CA, server-name/SNI and authorization behavior before
applying the settings. Test an allowed user, a denied user and the exact BMC
privilege, retaining native recovery and the exporter's separate local account.
The [X10/X11 manual, section 2-7-3](https://www.supermicro.com/manuals/other/IPMI_Users_Guide.pdf)
documents the LDAP/SSL, port, server, bind and search-base fields.

LDAP is not browser OIDC: passkeys do not authenticate a simple bind.
Authentik supports code-based MFA as `password;OTP` only with a compatible bind
flow; an app password does not automatically bypass that flow's MFA.
Do not disable global MFA to accommodate one appliance.

### Omada SAML remaining gate

The current directory-group mapping can produce an empty `usergroup_name` claim.
The [current Omada integration guide](https://integrations.goauthentik.io/networking/omada-controller/)
requires one case-sensitive Omada SAML user-group value, preferably represented
by an application-specific entitlement, plus the required profile/NameID mappings.
The shared [group blueprint](../kubernetes/apps/auth/authentik/blueprints/groups.yaml)
creates group objects only; it deliberately grants no memberships or admin roles.

Before changing authorization, obtain the existing controller **SAML User Group
Name**, assigned role/privileges and the failed login's launch context. The
controller MCP account was denied user/configuration access; do not bypass that
boundary through other credentials or its database. Compare the live connection
metadata before changing the existing provider, certificate, ACS, audience or
RelayState. The empty claim is a verified configuration gap, not proof that it is
the sole cause of the reported `-1001` response. No successful human SSO is claimed.

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
