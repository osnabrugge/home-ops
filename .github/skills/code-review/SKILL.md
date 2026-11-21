---
name: code-review
description: "Review Flux/Renovate Kubernetes pull requests: verify release paths, chart defaults, real consumers, storage risks and optional feature adoption."
---

# GitOps pull-request review

Use this for reviews, including native GitHub Copilot review requests. It
does not select the `gitops-upgrade` coding-agent profile, authorize a merge,
grant MCP access or make private cluster endpoints available to a cloud agent.

## Evidence

1. Pin the PR/head, state, changed files and exact old/new versions. For an
   already merged PR, distinguish its reviewed head from current deployment.
2. Read all intermediate upstream releases, including patch-release breaking
   changes. Take new configuration names from tagged source, not recollection.
3. Identify the chart's application/default images and this repository's
   overrides. A chart update need not update a custom-pinned application.
4. Trace producers/consumers of changed names, labels, ports, flags and CRDs.
   Include shared Flux components and persisted UI/native configuration when
   relevant. A repository search cannot certify a private application's state.
5. Use only available, authorized tools. GitHub MCP/`gh` can read upstream
   sources; `crane config` can inspect public OCI chart/image metadata.
   Never substitute credentials or bypass a private registry denial.
6. When installed, render the named HelmRelease with `flate`, from the
   namespace path; use `kubernetes/apps` when dependencies cross namespaces.
   A missing input on both base/head is a limitation, not a change-caused bug.
7. Record what was actually checked. Cloud access, tool availability and
   runtime verification are not implied by instructions or MCP registration.

Example offline render when `flate` is available:

```sh
flate diff hr RELEASE --base BASE_SHA --path kubernetes/apps/NAMESPACE --no-progress -o diff
```

Inspect only the relevant rendered identities, image defaults, RBAC, ports,
pod security and PVC ownership. CRDs and Secrets need separate source/schema
checks; an offline render is not full deployment acceptance.

## High-consequence changes

- Major PostgreSQL changes require compatible major-specific extensions,
  backup/restore testing, planned outage, archive separation and a supported
  rollback. Do not recommend a bare image-tag change as a complete migration.
- CNI, DNS, identity, control-plane and storage changes need supervised
  runtime checks and rollback. Never recommend PVC/PV deletion, force Helm,
  data clearing or node/host reboots without explicit approval.
- External exposure needs actual public-surface verification; LAN resolution
  alone does not prove public access.
- Preserve auth recovery, existing identities, source data and backup policy.

## Findings and plans

Report only high-confidence diff-caused defects, with changed-line anchors
and the dependent source. Do not request a change already present, convert an
unexecuted check into a finding, or report generic advice about unchanged
settings. Severity must match the evidenced consequence.

Separately list optional features with a concrete opt-in, prerequisites,
scope, safety gates, validation and rollback. Some upgrades expose a feature
automatically or contain only fixes; do not invent a feature PR for every bump.

Return: pinned scope/versions; verified findings; checked evidence;
unfinished checks; required actions; optional feature candidates. Publication
and implementation approval remain separate from a review request.
