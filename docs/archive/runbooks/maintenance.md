---
id: maintenance
title: Maintenance & Housekeeping
doc_type: runbook
level: reference
status: superseded
owners: [kent@intentional.biz]
last_validated: 2025-10-15
last_updated: '2025-10-29'
revision: v1.0
audience: agents_and_humans
---
> **SUPERSEDED**: The dual branch ruleset model (dev-human / dev-agent)
> and GH Actions runner branch naming conventions were retired in April
> 2026. This file is retained as historical record. For current branch
> conventions, see `docs/runbooks/repo-governance.md`.

# Maintenance & Housekeeping

## Branch hygiene
- One PR per branch; merge, then delete. (Auto-delete merged branches: enabled in repo settings.)
- Naming: human = `feat/*`, `docs/*`, `chore/*`; agents = `auto/*`, `bot/*`.

## Rulesets
- **dev-human** (branches: `feat/*`, `docs/*`, `chore/*`): require `Docs CI / validate` only.
- **dev-agent** (branches: `auto/*`, `bot/*`): require `Docs CI / validate` **and** Code Owner review (optional now, can enable later).
- `main` ruleset: protect main; require up-to-date; required checks = `Docs CI / validate`.

## CI gotchas
- The required check name must match exactly; we stabilized it to **Docs CI / validate** (PR-only workflow).
- If the Rulesets UI doesn’t suggest it, open a tiny PR to trigger the check, refresh, then select the **GitHub Actions** suggestion.

## Runner policies (summary)
- Runner will not edit `.github/workflows/**` (denylist). Use human PRs for workflow changes.
- Runner won’t push to `main` (guard in workflow); use feature branches.
- Handoff requests live under `ai-agents/shared/handoffs/` and produce a `*-github-runner-response.json` on success.
