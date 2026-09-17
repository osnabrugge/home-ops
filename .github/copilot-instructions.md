# home-ops — Copilot working agreement

## 🛑 STOP — SESSION START PROTOCOL (do this BEFORE your first reply)

Your `<userMemory>`/`<repoMemory>` context block **lies** — it has reported
"empty" while `/memories/` held 15 populated files. **Never trust it.** Always
list and read memory yourself with the `memory` tool. This is one tool call and
it has repeatedly saved hours.

**Mandatory first actions, every session, before answering anything:**

1. `memory view /memories/agent-behaviour.md` — how Sean wants you to operate.
   Contains "THE HALT PROBLEM" (his #1 complaint) and the no-fabrication rule.
2. `memory view /memories/` — list, then read the `repo/*.md` matching the topic.

**Topic → file index (read the match BEFORE answering, not after):**

| Topic                                             | File                                            |
| ------------------------------------------------- | ----------------------------------------------- |
| nas01 / nas02 / migration / ZFS / Garage / kopiur | `repo/nas01.md` ⛔ design is DECIDED            |
| printer / Eddy / Klipper / squish / ABS           | `repo/3d-printing.md`                           |
| Flux / SOPS / Ceph / tuppr / NetBox / Grafana     | `repo/home-ops.md`                              |
| SSH users + keys (DON'T ASK SEAN — it's here)     | `repo/access.md`, `repo/nas01.md`               |
| RBD read-only cascade                             | `repo/rbd-readonly.md`                          |
| what's parked and why                             | `repo/blocked-work.md`, `repo/deferred-work.md` |
| promises made                                     | `commitments.md`                                |

**Failure this actually prevents (2026-09-16/17):** I asked Sean for SSH access,
nas01 hardware inventory and nas02 share sizes, then proposed a pool design —
all four were already in `repo/nas01.md`, which literally says _"⛔⛔ DECIDED
DESIGN — STOP RE-DERIVING THIS"_ and _"Read this file BEFORE any nas01 answer."_

**Write back before the session ends.** New verified facts, corrections to stale
entries, and any mistake worth not repeating. Memory is only worth the cost of
reading it if it stays current.

## What this repo is

- GitOps for a Talos Kubernetes cluster (nodes k8s01–k8s06), reconciled by **Flux**.
- Apps live under `kubernetes/apps/<namespace>/<app>/`; each has a `ks.yaml`
  (Flux Kustomization) + `app/` (HelmRelease, etc).
- Shared building blocks are Flux **components** under `kubernetes/components/`
  (e.g. `volsync`, `zeroscaler`). Changing a component affects EVERY app that uses it.
- `KUBECONFIG=~projects/talos/home-ops/kubeconfig` for all kubectl/flux commands.

## Golden rules (do not violate without explicit approval)

- **READ-ONLY infra hosts**: `pve01`, `nas02`, `gw01`, firewalls, switches, APs.
  Never modify config or restart services on them without explicit go-ahead +
  a tested rollback. (See user memory `production-change-rules.md`.)
- **Destructive storage ops need sign-off**: deleting/recreating a PVC or PV,
  clearing data, force helm upgrades on stateful apps. A helm upgrade on an app
  whose PVC is helm-tracked can PRUNE the PVC — confirm first.
- **DNS overrides on homeops.ca are IPv4-only.** This is primarily due to the use of Bell Fibe, which does not support IPv6. If you need to expose an app externally, use Cloudflare Tunnel (see `zeroscaler` component) or a reverse proxy on `gw01` (e.g. `envoy-external`).
- **Dual publish**: `envoy-internal` (via unbound webhook, LAN) vs `envoy-external`
  (via Cloudflare, public). A name resolving on the LAN does NOT mean it's public.
  After any HTTPRoute/Gateway/cert/external-dns change, verify the public surface
  from outside (see user memory `test-infrastructure.md`).

## How to make a change land (GitOps)

1. Edit files under `kubernetes/`. Validate with `flux build kustomization <name>
--path <app path> --kustomization-file <ks.yaml> --dry-run`.
2. Commit + push to `main` (Flux pulls from the remote, not your working tree).
3. Reconcile by ANNOTATING (avoids the `flux reconcile` spinner that wedges the
   terminal): `kubectl annotate --field-manager=flux-client-side-apply --overwrite
<kind>/<name> -n <ns> reconcile.fluxcd.io/requestedAt="$(date +%s)"`.
4. App `ks.yaml` objects are created by the **parent** `cluster-apps` Kustomization
   — reconcile `cluster-apps` first so spec changes (e.g. postBuild vars) propagate.

## Repo gotchas (learned the hard way)

- **`spec.patches` in an app `ks.yaml` is CLOBBERED** by the global HR-remediation
  patch that `cluster-apps` strategic-merges into every child Kustomization. To
  patch a component-generated resource, change the component or use a postBuild var
  — NOT app-level `spec.patches`.
- **volsync PVCs**: born with `dataSourceRef`. If a PVC was instead created by helm
  (carries `meta.helm.sh/release-name`), Flux can't mutate its immutable spec —
  use `kustomize.toolkit.fluxcd.io/ssa: IfNotPresent` (annotation, not label).
- **Flux SSA strategy is an ANNOTATION** (`Override`/`Merge`/`IfNotPresent`/`Ignore`).
  A `label` of the same key is a no-op.
- **RBD read-only cascade**: slow OSD heartbeats / node net flap → RBD volumes remount
  read-only → pods crashloop on "read-only file system". Fix: confirm `ceph status`
  healthy, clear stale `ceph osd blocklist`, then delete the stuck pods to remount RW.
  Don't touch RBD while heartbeats are slow. (Repo memory: `rbd-*`.)

## Terminal hygiene (this shell is zsh)

- NEVER pipe interactive commands (`flux reconcile`, etc.) through `tail`/`grep`;
  it wedges the shell. Prefer `kubectl get -o jsonpath` for status.
- NEVER use `sleep` in a command — poll with a fresh command instead.
- Wrap multi-step commands containing `===`/`&&` chains in `bash -c "..."`.

## Tooling available to the agent (use proactively)

- **Radar** (https://radar.homeops.ca/mcp): MCP server for cluster health
- **Opnsense** (stdio): MCP for managing firewall and troubleshooting network/firewall issues
- **Azure** (stidio): MCP for managing Azure resources (VMs, KeyVault, etc) see context below for details
- **Cloudflare:** (https://mcp.cloudflare.com/mcp): Use Code Mode to reduce context window size to discover tool operations. Use cloudflare-dns-analytics and cloudflare-observability for native MCP for actual debuggin and troubleshooting for anything external DNS and/or Tunnel related issues.
- **Playwright** (stdio): for testing internal web endpoints (e.g. `envoy-internal`). For external web endpoints (e.g. `envoy-external`), you may deploy any Azure resources within the primary Resource Group (see Azure Context below).
- **Serena** (stdio): MCP Server for semantic code retrieval, editing, refactoring and debugging tools. Leverage this to build out your memory and/or knowledge base for any code related issues. You may also use this to build out your own custom code snippets and/or templates for future use. This is a highly desired tool by AI agents and here is what Opus 4.6 (high) had to say on a large Python codebase:

“Serena’s IDE-backed semantic tools are the single most impactful addition to my toolkit – cross-file renames, moves, and reference lookups that would cost me 8–12 careful, error-prone steps collapse into one atomic call, and I would absolutely ask any developer I work with to set them up.”"

### Azure Context

- **Tenant ID:** 2dd2129b-675b-4350-a458-0147ce24617a
- **Subscription:** VS-Enterprise
- **Primary Resource Group:** rg-homeops-prod
- **Primary Region:** East US
- **Primary KeyVault:** keyvault-kube

## Validation protocol before declaring done

- `flux get kustomizations -A` and `flux get helmreleases -A` show no new failures.
- Health/alerts not made worse (radar / alertmanager check command>`).
- For storage/exposure changes, run the relevant memory's verification steps.
