---
applyTo: "kubernetes/**/*.yaml,kubernetes/**/*.yml"
excludeAgent: "cloud-agent"
description: "GitOps guidance for native Copilot PR reviews, including mobile requests."
---

When reviewing these files, use `.github/skills/code-review/SKILL.md` if skills
are available. This is review guidance, not authorization to merge or deploy.

- Flux deploys changes from `main`. Trace actual consumers and shared
  components; a shared component can affect every app using it.
- Read the exact reviewed head and complete old-to-new release path. Separate
  chart versions, bundled application defaults and explicit image pins.
- Report concrete regressions introduced by the diff, not unchanged choices,
  generic hardening advice or missing verification alone. Anchor findings to
  changed lines and explain the unchanged dependent configuration.
- A value already present in the head is not a missing update.
- PostgreSQL major image changes can trigger offline in-place upgrades.
  Check major-specific extension images/library paths, backup/restore,
  archive boundaries and rollback before recommending a merge.
- Treat cluster/CNI/Ceph/shared-storage/database/DNS/gateway/identity changes
  as supervised. Do not infer permission to restart, migrate or prune storage.
- Rendering, CI success and Ready pods prove different things. Runtime
  protocol, client and persisted-state checks require their own evidence.
- If release, registry, render or runtime evidence is inaccessible, disclose
  that limitation. Never claim a check ran or suggest an unverified tag as a
  ready-to-apply fix.
- Keep optional feature adoption separate from defects. State its exact
  configuration, prerequisites, consumer impact, verification and rollback.
- Do not include secrets, signed URLs, private reports or personal data.
