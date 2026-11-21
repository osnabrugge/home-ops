# Mobile GitOps reviews

The pull request's **Request Copilot review** button starts GitHub Copilot
code review, not the repository's `gitops-upgrade` cloud coding-agent profile
and not Kritika. Their reviews/statuses are independent.

Native code review can use repository instructions, review-focused skills
and configured MCP context. The Kubernetes instruction file and
`.github/skills/code-review/SKILL.md` provide GitOps guidance without requiring
a mobile custom-agent picker or granting cloud access to the cluster.

GitHub's current documentation says PR review reads this context from the
**head branch**. Re-request review after pushing these files or rebasing a
reviewed branch onto them; already completed reviews do not change
retroactively. Check review-session/tool attributions before assuming a skill,
registry lookup or runtime test was used.

Review effort is a separate choice. Balanced is the default; Max uses more
reasoning/models and more AI credits. Do not enable expensive automatic
reviews or change approval policy merely to make an agent accessible.

For implementation, use a cloud-agent task/profile selection where that UI is
available, or **Fix with Copilot** on a review suggestion. Give a bounded PR,
exact head and explicit implementation/rollback scope. A review request is
not permission to merge, deploy or migrate storage.

Kritika requires its own native/manual review request. A failed historical
Kritika status is not replaced by a new GitHub Copilot review.

Sources:

- [Using Copilot code review](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-code-review?tool=webui)
- [Repository/path-specific instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)
