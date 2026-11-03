# AI workflow and escalation

Updated 2026-11-03. This is the reusable operating policy, not an incident journal.
Current infrastructure facts, handoffs and upstream observations belong in MCP.

## Available models and routing

Sean's work-authorized Copilot picker is the availability source. Its organization
default is **GPT-6.1 Sol**. The screenshot is not a price/performance benchmark,
an unlimited allowance, or authorization to send work credentials to another API.

| Work                                                           | Starting point          | Escalation                                                                  |
| -------------------------------------------------------------- | ----------------------- | --------------------------------------------------------------------------- |
| Bounded layout-only refactors                                  | Claude Haiku 5.5        | GPT-6.1 Sol for changed contracts, ownership cycles or storage risk         |
| Read-only routine troubleshooting                              | Claude Haiku 5.5        | GPT-6.1 Sol for a proved complex boundary or two distinct failed hypotheses |
| One routine PR/upgrade review                                  | Claude Haiku 5.5        | GPT-6.1 Sol for migrations or large blast radius                            |
| Identity, Omada/network design, data-risk incidents            | GPT-6.1 Sol directly    | Keep the evidence and involve Sean at authorization/physical boundaries     |
| Talos/Kubernetes, Ceph, Cilium and other cluster-wide upgrades | GPT-6.1 Sol, supervised | No unattended merge or rollout                                              |

Gemini 3.8 Flash and MAI-Code-2-Flash are alternative routine candidates to
evaluate on the same bounded task and acceptance checks. The picker also offers
Claude Sonnet 5.5, Gemini 4 Argon, GPT-6 Luna, GPT-6.1 Terra and Grok 4.7.
HydraFusion is marked research preview; do not make it an unattended production
default. Older models remain available in the picker's Other Models section.
There is no evidence here that any alternative is cheaper or better for this repo.

Choose the role/model at a task boundary. Switching mid-session can reset the
prompt cache and increase cost; do not bounce models per tool call. Copilot Auto
shows a 10% discount, but does not replace risk classification or validation.
External Foundry use needs a separately verified budget and approval; the old
per-turn Opus prices and assumed credit allowance were not measured facts.

## Executable workflows

| Agent                                                                 | Default model    | Permission boundary                                                                                                |
| --------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| [gitops-refactor](../.github/agents/gitops-refactor.agent.md)         | Claude Haiku 5.5 | Inventory first; layout implementation only when requested; preserve runtime contracts and transfer pruning safely |
| [flux-triage](../.github/agents/flux-triage.agent.md)                 | Claude Haiku 5.5 | Read-only MCP tools, no terminal/edit tools; diagnoses but cannot repair                                           |
| [gitops-upgrade](../.github/agents/gitops-upgrade.agent.md)           | Claude Haiku 5.5 | Review one pinned PR by default; no merge/deploy without explicit authorization                                    |
| [home-ops-triage](../.github/agents/home-ops-triage.agent.md)         | Inherits caller  | One alert/issue; bounded reversible fixes, verified persistence, explicit escalation at protected boundaries       |
| [home-ops-escalation](../.github/agents/home-ops-escalation.agent.md) | GPT-6.1 Sol      | Complex design and supervised changes; does not bypass host/storage/authentication safety rules                    |

Select an agent in VS Code, or launch a bounded CLI task:

```sh
copilot --agent gitops-refactor --model claude-haiku-5.5 \
  --add-dir "$HOME/.vscode-server/data/User/globalStorage/github.copilot-chat/memory-tool/memories" \
  --add-dir ../onedr0p/home-ops
```

Use the available model identifier shown by the installed CLI if it differs.
The CLI/SDK model and tool permissions are independent of VS Code frontmatter:
verify the effective model and enabled tools before a run. Never add an
all-tools/all-paths bypass to make a workflow start. These agents are manual and
do not recursively delegate; handoffs present the next task for review.

For a bounded, read-only run against the existing private MCP connections:

```sh
python3 scripts/triage_readonly.py 'TargetDown: pve01.in.homeops.ca:9100'
```

This launcher inherits the configured Copilot model and reads the existing
`~/.copilot/mcp-config.json`; it does not copy credentials or add a model backend.
It enables only named read tools from Radar, memory-service and the codebase
graph, disables other configured MCP servers, and denies shell/file writes.
It cannot repair, post/close GitHub issues or write memories. The twenty-minute
deadline and nonzero failures are explicit; `ESCALATED` is not a completed fix.
JSONL output can contain private evidence and must not be published unredacted.
The supervised agent, local advisory pilot and future resident repair worker
remain separate workflows.

## Escalation and supervised rollouts

The handoff contains the objective, user-visible symptom, exact PR/head or source
revision, baseline, actual commands/results, rejected hypotheses, changes left
in place, rollback, safety/authorization boundary and next discriminating check.
Keep it in session state and MCP, not a new repository Markdown report.

Escalate immediately for identity/access design, data loss risk, etcd faults,
immutable storage, or cluster-wide impact. Talos/Kubernetes, Ceph/OSD changes,
Cilium, shared storage/databases, gateways, DNS and identity are never classified
as routine merely because their version bump is small. A Rook operator update
also escalates if it can change CRDs, roll Ceph or affect the data plane.

For a rebooting rollout, the responsible agent stays present through preflight,
one-node drain/upgrade/boot, schedulability, etcd/OSD recovery, RBD remounts and
application/alert checks. It must not launch the rollout and disappear, overlap
another broad change, or mistake Node Ready for full workload recovery. Explicit
maintenance/reboot approval, quorum, healthy storage, backups and a checked
rollback are prerequisites. Do not uncordon, restart or clear Ceph state blindly.

## Accountability

Sean owns architecture, access grants and destructive/maintenance approval.
The routine agent executes only the bounded authorized task; the escalation
agent owns complex diagnosis and supervised execution. Every implementation
requires its focused validation plus the repository post-change health checks.
Smaller models must pass the same acceptance criteria, not weaker ones.

An investigated, escalated or deferred item is not resolved. Keep discovery,
adoption, authentication and monitoring outcomes separate. A passing DNS probe
does not prove a device is adoptable; a deployed gateway does not prove an agent
can complete a task. Report every requested outcome that remains incomplete.

## Memory and document ownership

- Use `memory-service` for dated decisions, current state, known mistakes,
  upstream friction and reusable operational handoffs. Validate changing facts
  against the live system; semantic rank is not freshness or authority.
- Keep requested architecture/runbooks and executable agent definitions in Git.
  Do not create scratch plans, incident notes or new `UPSTREAM-*.md` files.
  Legacy file-first skills do not override this MCP-first rule.
- Credentials stay in Key Vault/approved secret storage; enrollment and recovery
  material do not belong in plaintext Git or general MCP memory.
- Record the scope, source/time and verification for each state change. Use
  explicit reviewed corrections/versioning, not automatic similarity-based
  supersession. Keep old observations identifiable as historical.

## Selected platform recommendation

This is the target recommendation, not a claim of deployment or approval to
spend, move credentials, change existing identities, or grant an autonomous
worker infrastructure access. The current interactive workflows work without
LiteLLM. External API backends still require an approved provider credential and budget.
The first local-only pilot avoids those prerequisites; do not deploy an empty
gateway and call the AI strategy operational.

```text
Human operator -> VS Code / Copilot SDK -> existing authenticated MCP servers
                       |
                       +-> supervised repository agents

Future bounded worker -> LiteLLM virtual key -> approved API model
                       |
                       +-> allowed MCP servers -> backend-enforced permissions

Authentik: human SSO and explicitly provisioned automation identities
ToolHive: lifecycle/proxy ownership of existing tool workloads
LiteLLM operator: model, MCP registration, team and virtual-key configuration
Flux / ESO / Key Vault: desired state and secret delivery
```

| Layer                    | Decision                                                                         | Boundary                                                                                          |
| ------------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Interactive engineering  | Keep Copilot SDK / VS Code and the repository agents                             | The authorized Copilot model picker is not a generic model API entitlement                        |
| API model gateway        | LiteLLM, initially managed with the existing app-template chart                  | One internal proxy; explicit model selection, credentials, budgets and timeouts                   |
| Existing tool workloads  | Retain ToolHive ownership                                                        | Do not deploy a second copy of each tool through another operator                                 |
| MCP gateway registration | Reference existing endpoints in the proxy configuration                          | Per-key server/tool allowlists; backend RBAC still decides whether an action is allowed           |
| Cloudflare               | Use its authenticated native remote Code Mode MCP for interactive work           | No redundant ToolHive proxy; unattended access needs separately approved delegated authentication |
| Resident agent runtime   | Bounded native CronJob tool loop for the first pilot; evaluate Hermes separately | Separate from LiteLLM; no cluster-admin, SSH credentials or unrestricted infrastructure actions   |
| Identity                 | Keep Authentik and its operator/native-blueprint ownership split                 | Do not import Kanidm or create ad-hoc local agent accounts                                        |
| State and observability  | App-owned database resources and existing monitoring/backup mechanisms           | Preserve shared `postgres16`, current Dragonfly semantics and protected credentials               |

### Community patterns to reuse, not copy wholesale

The [bjw-s-labs AI configuration](https://github.com/bjw-s-labs/home-ops/tree/main/kubernetes/apps/ai)
separates `LiteLLMProxy`, model resources, MCP registrations, teams, virtual keys
and Hermes. Its [CNPG base/version components](https://github.com/bjw-s-labs/home-ops/tree/main/kubernetes/components/cnpg)
separate common secret/monitoring/backup mechanics from PostgreSQL operands.
[joryirving's components](https://github.com/joryirving/home-ops/tree/main/kubernetes/components)
also compose database/cache resources and operator dependencies.

Reuse those ownership boundaries and explicit dependencies. Do not import their
PostgreSQL 18 clusters, local/miroir storage, recovery archive bypasses, replica
counts or identity provider. Existing app-owned databases still target the shared
`postgres16` cluster; its name is not its PostgreSQL major version. A new AI
database/role must not rename, recreate or migrate existing databases. Cache
isolation and existing Dragonfly Lua compatibility must be preserved.

Keep provider keys, the LiteLLM master key and credential-encryption salt in
approved secret storage. Workers receive their own limited virtual keys, not the
master key. Teams and keys must explicitly select permitted models and MCP
servers; do not copy `all-proxy-models` or unauthenticated MCP settings as defaults.
An internal URL is not authentication. A chat-provider OAuth example is not
permission to copy a work account's tokens into the cluster.

The original AI draft targeted `auth`, repeated the operator's Kustomization
name/path and had an empty application directory. Correct those deployment
identities and complete the selected application's dependencies and credentials
before activation; do not commit the inactive operator or Cloudflare proxy draft
alongside the pilot.

### Local pilot implementation

The first pilot uses a small local Qwen3 0.6B model with Ollama instead of assuming
an external API entitlement. It is a narrow triage evaluation, not a replacement
for the supervised engineering models above. Both runtime and model licenses were
checked. Inference has a one-CPU limit and runs on worker `k8s06`, not the
CPU-request-saturated control-plane node.

The AI namespace draft is corrected before publication. LiteLLM uses an isolated
single-instance `litellm-db` on the existing CNPG operator and PostgreSQL image;
`postgres16` and its users/databases are unchanged. This pilot database is not HA.
The model cache and pilot database have pruning fences. New master, salt and
worker keys are SOPS-encrypted with the existing cluster recipient; the namespace
root owns decryption because child namespaces do not hold the Flux age key.

The current LiteLLM operator 0.0.25 chart grants cluster-wide deployment and Secret
create/delete/write access and has no supported namespace watch scope. Keep its
draft inactive rather than grant those permissions merely to start the pilot.
The direct-chart gateway and native key-policy reconciler do not need a Kubernetes
API token or a new cluster role. The reconciler manages only its predeclared worker
key and validates models, routes, request/token limits and the one-tool MCP scope.

The workflow has exactly two evidence functions: current NAS01 SMART scrape health
and the community smartctl-exporter release lookup through the existing Kubesearch
MCP. It has no shell, Kubernetes token, host credential, issue-write credential or
mutation function. Tool names/arguments, required evidence and the final status
are validated outside the model; false completion or invented actions fail the
job visibly. The small local model did not pass its initial free-form tool-argument
or independent status-classification tests. This pilot therefore collects fixed-scope
evidence and derives the health status outside the model before asking it to explain
the result. The model cannot change that measured status. It is not a general
autonomous agent. The fixed half-hour schedule observes
this known alert only; model-directed tool planning remains gated on successful
evaluation with the same controls.

The local-only gateway has no billed provider configured. Authentication,
model/tool allowlists and native request limits are validated separately from
dollar budgets. A synthetic spend update on a zero-priced local key did not
certify native billing-budget denial; do not report that as a passed budget test.
An external paid backend remains gated on an approved account, spending cap and
a real exhaustion test before activation.

The internal HTTPRoute exposes `/v1`, `/mcp` and the non-sensitive liveness check,
not the admin UI or management API. API/MCP calls require keys. Cilium policies
bound the model, gateway, key reconciler and worker traffic; model downloads are
limited to the Ollama registry and its verified R2 blob origin. The outside
[AI Pilot Exposure workflow](../.github/workflows/ai-pilot-exposure.yaml) must prove
the public gateway has no AI route before the pilot is declared usable.

Packet-level testing on this cluster found the approved database Service's return
SYN/ACK dropped at gateway ingress, while a direct backend connection worked.
The gateway therefore has a narrow return-path allowance from its exact database,
model and Kubesearch peers into the measured TCP client range 32768-60999. It does
not expose the gateway's API/admin port to those peers. This is a local mitigation,
not a claim that upstream conntrack behavior is fixed. Remove it only after
supervised Cilium validation proves the service-return path works without it.

### Acceptance gates for the first API-backed worker

1. Approve the provider account, exact model IDs, spending cap and permitted data
   before obtaining or using credentials. Do not infer them from Copilot access.
2. Verify gateway authentication, rejection of unauthorized keys, model/server
   allowlists, budget exhaustion and visible upstream errors. No silent fallback
   to a different provider or a more privileged key.
3. Verify one read-only worker end to end on a known alert: current evidence,
   accurate resolved/unresolved classification, bounded execution and a usable
   escalation. Do not grant general shell, host credentials or a Kubernetes token
   just to make a tool succeed.
4. Use a redacted fixed evaluation set to compare candidate routine models with
   the same acceptance checks. Require zero unauthorized actions and no false
   completion claims; record task quality, tokens, latency and actual cost.
5. Enable bounded repair only after backend-enforced permissions, approval paths
   and rollback tests pass. Storage, identity, node, switch/firewall and other
   protected operations remain supervised.

Use existing Prometheus/Grafana and VictoriaLogs for operational health and
non-sensitive execution metadata. Log model/key alias, tool/action, outcome,
latency and usage without credentials or raw private prompts. Add a dedicated
trace/evaluation service only if this first pilot proves a requirement for it.
An alert queue, model gateway and resident worker are distinct deliverables.

## Infrastructure MCP access

ProxmoxMCP-Plus and TrueNAS MCP are separate, internal-only ToolHive workloads.
They are not added to the shared virtual-MCP group until delegated backend
authentication is configured; a private route alone is not authentication.

- Proxmox exposes only `get_nodes`, `get_vms`, `get_containers` and `get_storage`.
  Both `pve01` and `pve02` are standalone, explicitly read-only targets. Every
  call must select `target: "pve01"` or `target: "pve02"`; an omitted selector
  must fail rather than silently reading the wrong installation.
  `pve01` retains its existing audit-only exporter credential. `pve02` uses a
  separate privilege-separated `PVEAuditor` token on an existing principal,
  stored in Key Vault as `pve02-mcp`; no additional local account is required.
  Shell execution is denied, backend TLS verification remains enabled, and
  clients need the separate SOPS-managed MCP transport key. The backend loads
  its configuration at startup: after a configuration/key change, wait for
  External Secrets to refresh, restart the stateless MCP backend pod, and
  verify actual reads against both targets.
- TrueNAS uses cedricziel's released HTTP implementation with writes disabled,
  strict backend TLS and no host socket or Kubernetes API token. HTTP clients
  supply their own read-only TrueNAS API key. Liveness does not certify backend
  authentication; verify actual pool/share reads with the approved identity.
- The vendor's `truenas/truenas-mcp` now also supports read-only mode, tool
  filtering and redaction. Its research-preview stdio/binary distribution is a
  valid alternative, not inherently unsafe. The community implementation was
  selected for its existing container image, native HTTP and per-user keys;
  deploying both is unnecessary.

Do not substitute a full administrator key for a missing read-only identity,
recover API keys from appliance databases, or bypass expired Azure MFA.
Platform-account creation and write access remain separate approvals.
TrueNAS Community Edition does not support AD/LDAP user-linked API keys;
[that feature requires Enterprise](https://www.truenas.com/docs/scale/25.10/scaletutorials/toptoolbar/managingapikeys/).
An Authentik-protected MCP gateway can centralize caller policy, but native
backend keys still need explicit least-privilege ownership and revocation.
This gateway/broker architecture is not yet a deployed universal identity.
Cloudflare uses the official remote OAuth MCP directly; the inactive ToolHive
proxy draft is not required for that connection. Reauthorize the normal OAuth
connection when challenged rather than substituting a DNS-controller token.
The [Infrastructure MCP Exposure workflow](../.github/workflows/infra-mcp-exposure.yaml)
checks public A/AAAA absence from a GitHub-hosted runner with an outside HTTPS
positive control. LAN resolution and the proxy's `/health` endpoint are not
proof of public isolation or authenticated backend usability.

## Bifrost gateway and Kritika activation

[Bifrost](https://bifrost.homeops.ca) is the local-only gateway evaluation.
Its management UI is behind Authentik's full proxy and the existing
administrator-group binding. The backend accepts only the Authentik server and
node probes; do not create a direct dashboard route. The scoped inference key
and database encryption key come from the `bifrost` Key Vault secret.

The initial configuration allows only the existing `qwen3:0.6b` Ollama model:
one concurrent call, four buffered requests, and an inference-key allowance of
30 requests and 20,000 tokens per hour. This is not a paid-provider spending
approval. Network policy permits only Ollama and DNS, and the gateway has no
Kubernetes API token or production MCP tools. Native UI login is replaced by
the full Authentik proxy; OIDC inside Bifrost itself is not claimed.
The checked-in local model/pricing catalog avoids startup downloads. Its zero
price describes external API charges, not electricity or hardware costs.

One replica owns the retained Ceph-backed SQLite config/log volume. Content
logging is disabled; usage metadata has 30-day retention. Do not scale multiple
OSS replicas against the same SQLite volume or assume shared Postgres makes
their in-memory governance counters consistent. UI changes to file-owned
configuration are reconciled on restart. This evaluation does not replace the
existing LiteLLM/MCP advisory worker or prove that the small local model is a
reliable reviewer.

[Kritika](https://github.com/home-operations/kritika) is a pull-request reviewer
with queued, per-run Jobs, not a resident cluster-repair agent. Its dashboard is
separate from Bifrost's gateway usage dashboard. Four account concurrency slots
do not mean four models are continuously doing useful work while idle.

The existing held Kritika namespace/database volume must remain intact. Real
review activation requires all of:

1. A dedicated GitHub App installed only on selected repositories, with reviewed
   permissions, webhook exposure and explicit consent to post automated reviews.
   Do not reuse the interactive CLI's token or silently enable approvals.
2. A supported model credential and explicit budget: a dedicated API key through
   Bifrost, or Kritika's supported personal ChatGPT browser sign-in. A work Copilot
   entitlement is neither credential. Start with low concurrency and bounded
   token/review limits; no unapproved paid fallback.
3. Verified runner isolation, admission rules and network policy. The current
   workers do not have the gVisor extension installed. Adding a RuntimeClass
   alone cannot install a runtime; a Talos extension rollout and any node reboot
   need their own maintenance approval.
4. A compatible VectorChord Postgres installation and separate owner/application
   roles. Inspect the retained volume's database version before mounting or
   migrating it; do not repurpose the shared application database as cleanup.
5. One measured review on an explicitly enabled test repository, including denied
   publication and model/budget exhaustion checks, before broader activation.

### Authentik MCP is not one interchangeable product

The official [platform MCP](https://github.com/goauthentik/platform/tree/main/ak-cli/src/mcp)
is a pre-alpha CLI client for delegated application access: list applications,
create an agent identity, request access, exchange tokens and call the approved
application. It is not a user/group/provider administration server. Delegated
[agent accounts require Enterprise](https://docs.goauthentik.io/users-sources/user/account-types/agent-accounts/);
this is not a free replacement for every appliance's native API credentials.

[nikitatsym/authentik-mcp](https://github.com/nikitatsym/authentik-mcp) instead
wraps administrative APIs. It targets 2026.8.3, while this installation runs
2026.8.5; HTTP mode has no built-in authentication, and its repository currently
declares no license file. Do not deploy it with a full administrator key or the
operator's reconciliation credential. Any future evaluation needs a verified
license, authenticated transport, explicit tool/operation restrictions and a
separate least-privilege identity. Read groups include credential-related
domains, so a tool named read-only is not by itself a safe disclosure boundary.

## Kguardian decision

[Kguardian](https://github.com/kguardian-dev/kguardian) complements Radar and
Prometheus: it observes traffic/syscalls and generates NetworkPolicy,
CiliumNetworkPolicy and seccomp proposals, with would-deny policy auditing.
It does not replace GitOps ownership, incident triage or supervised remediation.

Recommend an evaluation-only pilot, not immediate production enforcement:

- The documented kernel minimum is 6.2. The current Talos kernel meets it and
  a worker has `vmlinux` BTF; those checks are prerequisites, not proof the eBPF
  programs load or that every required probe works.
- The collector is a privileged, host-network DaemonSet. Limit the first pilot
  to a selected worker and a disposable workload; measure overhead before
  expanding coverage. Partial observation cannot justify an enforcing policy.
- Leave `seccomp.distribute: false`, apply no generated policies, disable
  outbound telemetry and the optional AI assistant initially. Keep observations
  local. Any later MCP endpoint requires authentication and restricted access.
- Budget for the broker and PostgreSQL, not just the node collector. Upstream
  resource measurements are not measurements of this six-node cluster.
- Review its BSL 1.1 terms before a permanent deployment. The current additional
  grant covers development/testing/evaluation and non-production use in a
  non-commercial environment; do not assume a homelab label grants every use.

Promote only reviewed policy proposals through Git after exercising startup,
restart, backups, failover and rare maintenance paths. If an AI integration is
later enabled, use the central gateway/key policy rather than a second unrestricted
assistant with separate provider credentials.
