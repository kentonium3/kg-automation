---
id: GOV-REPO-PROTECTION
title: Repository Governance — Branch Protection & PR Policy
doc_type: governance
level: reference
status: approved
owners: [kent@intentional.biz]
last_validated: 2025-10-12
revision: 1.0
---

This page defines how changes land in `kg-automation`, for both humans and AI agents. It complements the CI, handoff protocol, and system/runbook governance.

## Branching model
- **Default branch:** `main` (protected)
- **Contribution branches:** short‑lived, task‑scoped. Examples:
  - `handoff/0002-agent-handbook-checklist`
  - `ci/docs-ci-initial`
  - `feat/<capability>-<short-desc>`
  - `docs/<area>-<short-desc>`

## Protection rules for `main` (recommended)
Enable in *Settings → Branches → Add rule → Branch name pattern: `main`*

**Pull requests**
- Require a pull request before merging
- Require approvals: **1**
- Dismiss stale approvals on new commits
- Require conversation resolution
- (Optional) Require review from Code Owners

**Status checks**
- Require status checks to pass before merging
  - Select **Docs CI**
- Require branches to be up to date before merging

**Push restrictions**
- Restrict who can push: allow **owner only** (agents use PRs)

**History & safety**
- Prevent force pushes
- Prevent branch deletions
- (Optional) Require linear history (squash/merge)

**Administrators**
- Leave “Include administrators” **off** initially (emergency bypass)

## Pull request policy
- Pull before working; keep PRs small and focused.
- Commit messages use conventional prefixes: `feat:`, `fix:`, `docs:`, `ci:`, `chore:`
- Handoff threads use: `handoff: request <id> …` / `handoff: response <id> …`
- Resolve all comments; CI must pass.

## Continuous Integration (Docs CI)
The workflow enforces:
1. Front‑matter on all `.md` (`id, doc_type, level, status, owners, last_validated, revision`)
2. Workflow schema checks (if schema present)
3. Runbook front‑matter extras (`audience, severity, last_tested`)
4. AI handoff JSON validation + filename convention
5. Registry + doc graph rebuild
6. No hand edits to generated files
7. Clean working tree after generators
8. Quick relative link check

See `docs/handbooks/ci-handbook.md` for how to pass locally.

## AI agent rules
- **No direct pushes to `main`.** Open PRs from a task branch.
- Use `ai-agents/shared/handoffs/` with the contract `ai-agents/shared/contracts/ai-handoff.schema.json`.
- Filename format: `YYYYMMDD-HHMMSS-<id>-<from>-to-<to>-<type>.json`.
- Reference all outputs (paths, PR links) in the response JSON.

## Secrets & sensitive data
- Do not commit secrets. Use references (e.g., `secrets:<alias>`) or external secret stores.
- CI runs a basic pattern scan; violations block merges.

## Emergencies (hotfixes)
- Owner may push/merge to `main` if needed. Record a short post‑merge note in the PR or an ADR explaining the exception.

## CODEOWNERS (optional but recommended)
Add `.github/CODEOWNERS` to enforce reviews for critical areas. Example:

```
# Require owner review for governance and CI
docs/governance/*   @kentonium3
.github/*           @kentonium3
# Require review for registries/scripts
tooling/scripts/*   @kentonium3
```

## Onboarding checklist
- Enable branch protection for `main` using the settings above.
- Merge CI PR (#2).
- Communicate to agents: PR‑only flow, CI must pass, use handoff protocol.
- Create teams/permissions if collaborators join later.
