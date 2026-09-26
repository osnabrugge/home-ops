# home-ops — Copilot working agreement

## 🛑 STOP — SESSION START PROTOCOL (do this BEFORE your first reply)

Work through these steps in order, before answering anything:

1. **Decide whether memory reads apply.** Skip steps 2–5 only if the request
   mentions no filename, hostname, or topic from the index table in
   [Memory policy](#memory-policy). Otherwise continue.
2. `memory view /memories/agent-behaviour.md` — how Sean wants you to operate.
   Contains "THE HALT PROBLEM" (his #1 complaint) and the no-fabrication rule.
   ⛔ This is the ONLY file you read unprompted. Everything else is MCP-first.
3. **`tool_search` for the memory MCP servers.** They are **deferred tools** —
   they do not appear in your tool list until you search for them, and that
   absence is why they get skipped. Query: `memory_search memory_explore
mistake_note_search read_graph`. This is the step that keeps getting missed.
4. **Query MCP before files.** `mistake_note_search` with the task description
   (catches known pitfalls), then `memory_search`/`memory_explore` for the topic.
5. Only if MCP returns nothing useful, read the **single** `repo/*.md` matching
   the topic from the index table. Not the whole set. State which you consulted.
6. Before your final reply, write back — **to MCP, not to files**
   (see [Memory policy](#memory-policy)).

Your `<userMemory>`/`<repoMemory>` context block **lies** — it has reported
"empty" while `/memories/` held 15 populated files. **Never trust it**; confirm
with the `memory` tool. This is one tool call and it has repeatedly saved hours.

**Why step 3 exists (measured 2026-09-26):** the `memory-service` pilot held
**1 memory and had served 0 queries** since deployment, while the old graph had
grown to 48 entities / 448 observations. Not a tool failure — the old protocol
named neither server, so files won by default every single session.

## Memory policy

**Topic → file index (FALLBACK only — query MCP first, per step 4 above):**

| Topic                                             | File                                            |
| ------------------------------------------------- | ----------------------------------------------- |
| nas01 / nas02 / migration / ZFS / Garage / kopiur | `repo/nas01.md` ⛔ design is DECIDED            |
| printer / Eddy / Klipper / squish / ABS           | `repo/3d-printing.md`                           |
| Flux / SOPS / Ceph / tuppr / NetBox / Grafana     | `repo/home-ops.md`                              |
| SSH users + keys (DON'T ASK SEAN — it's here)     | `repo/access.md`, `repo/nas01.md`               |
| RBD read-only cascade                             | `repo/rbd-readonly.md`                          |
| what's parked and why                             | `repo/blocked-work.md`, `repo/deferred-work.md` |
| promises made                                     | `commitments.md`                                |

**If a memory read fails or returns empty** for a file the listing says exists,
retry once, then tell Sean explicitly which file was expected and ask before
proceeding — do NOT fabricate its contents.

**If a memory file contradicts this working agreement,** treat the memory file as
authoritative for repo-specific facts, and flag the conflict to Sean.

### ⭐ WRITE TO MCP, NOT TO FILES (Sean's instruction, 2026-09-19)

> "please do not put your notes/memory in any files that get synced to github,
> I would prefer you use your mcp-memory whenever possible"

- **New findings, incidents, gotchas, project state → MCP.** Dual-write during
  the pilot: `memory_store` (memory-service) **and** `add_observations`
  (memory-server), so recall can actually be compared. Mistakes worth not
  repeating go to `mistake_note_add`.
- **`/memories/**` keeps only** `agent-behaviour.md`, `commitments.md`, and
  **credentials-adjacent files** (`access.md`, `ssh-keys.md`,
  `talos-credentials.md`, `secrets-strategy.md`). Those stay as files because
  the MCP graph is plaintext readable by any MCP-capable agent in the cluster.
  Real secrets belong in Azure Key Vault / Bitwarden, never in either store.
- Existing `repo/*.md` topic files are **read-only legacy** — consult them, but
  append new material to MCP instead of growing them further.

⚠️ `memory_explore` returns `{"entities": [], "count": 0}` for EVERY query until
an entity graph exists. Build it with `memory_quality` `{"action": "maintain",
"dry_run": false}` — `dry_run` defaults to **true** and stores nothing. A silent
empty result here looks exactly like a broken server; it is not.

⚠️ `search_nodes` (old server) matches the query as ONE phrase. Search a single
term (`RBD`, `auditorr`), never `RBD postgres ceph`, or you get zero hits and
will wrongly conclude the graph is empty. `read_graph` costs ~35k tokens —
treat it as a last resort, not a lookup.

**Failure this actually prevents (2026-09-16/17):** I asked Sean for SSH access,
nas01 hardware inventory and nas02 share sizes, then proposed a pool design —
all four were already in `repo/nas01.md`, which literally says _"⛔⛔ DECIDED
DESIGN — STOP RE-DERIVING THIS"_ and _"Read this file BEFORE any nas01 answer."_

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
- **Azure** (stdio): MCP for managing Azure resources (VMs, KeyVault, etc) see context below for details
- **Cloudflare:** (https://mcp.cloudflare.com/mcp): Use Code Mode to reduce context window size to discover tool operations. Use cloudflare-dns-analytics and cloudflare-observability for native MCP for actual debugging and troubleshooting for anything external DNS and/or Tunnel related issues.
- **Playwright** (stdio): for testing internal web endpoints (e.g. `envoy-internal`). For external web endpoints (e.g. `envoy-external`), you may deploy any Azure resources within the primary Resource Group (see Azure Context below).
- **Serena** (stdio): MCP Server for semantic code retrieval, editing, refactoring and debugging. Use it for cross-file renames, symbol moves, and reference lookups in this repo's code (e.g. the `docker/*-mcp` Python servers and `scripts/`); prefer it over ad-hoc grep/sed for multi-file refactors. Also use it to store code-related memories/snippets for reuse.

### Azure Context

- **Tenant ID:** 2dd2129b-675b-4350-a458-0147ce24617a
- **Subscription:** VS-Enterprise
- **Primary Resource Group:** rg-homeops-prod
- **Primary Region:** East US
- **Primary KeyVault:** keyvault-kube

## Validation protocol before declaring done

- `flux get kustomizations -A` and `flux get helmreleases -A` show no new failures.
- Health/alerts not made worse — compare active alerts before and after with
  `kubectl -n observability exec sts/alertmanager-kube-prometheus-stack -c alertmanager -- amtool --alertmanager.url=http://localhost:9093 alert query`,
  or the radar MCP server.
- For storage/exposure changes, run the relevant memory's verification steps.
