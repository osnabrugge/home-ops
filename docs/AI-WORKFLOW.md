# AI workflow and escalation

Updated 2026-10-26. This is the reusable operating policy, not an incident journal.
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

## Optional runtime components

No local model endpoint, LiteLLM deployment or Foundry runtime is required for
these workflows. Their availability must be verified, not inferred from a GPU
or an old plan. LiteLLM is a model gateway/control plane, not the agent execution
runtime, and a Copilot subscription does not automatically expose its models as
a generic LiteLLM backend. Introduce those services only for a separately scoped
need, with secret handling, budgets and fallback behavior tested.
