---
work_package_id: WP07
title: Doctrinal anchor (charter, runbook, CLAUDE.md, issue templates)
dependencies: []
requirement_refs:
- FR-010
- FR-011
- FR-012
- FR-014
- FR-018
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T030
- T031
- T032
- T033
- T034
- T035
- T036
agent: claude
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: docs/runbooks/deploy/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- .kittify/charter/charter.md
- docs/runbooks/deploy/discipline.md
- docs/runbooks/deployment.md
- CLAUDE.md
- .github/ISSUE_TEMPLATE/feature.md
- .github/ISSUE_TEMPLATE/infra.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else.

## Objective

Land the **doctrinal layer** that makes the deploy discipline visible to future agents. This is what causes a spec-kitty specify/plan agent on a new feature/infra issue to *automatically* incorporate the manifest discipline into its plan without operator prompting.

## Context

The mechanism (library, applier, manifest schema) is half the value. The other half is *agentic discoverability* — making sure future agents working on this codebase encounter the discipline through their normal context-loading paths. The discoverability surfaces are:

| Surface | Role |
|---|---|
| `kg-automation/CLAUDE.md` | Read every session start by Claude; highest-leverage agent surface |
| `.kittify/charter/charter.md` Deployment Constraints rule | Loaded via `spec-kitty charter context` on every mission action |
| `docs/runbooks/deploy/discipline.md` (new) | The canonical operational runbook everything else references |
| `docs/runbooks/deployment.md` (existing) | Rewritten to point at the new discipline runbook |
| `.github/ISSUE_TEMPLATE/feature.md` and `infra.md` | "Deploy required?" prompt at issue-creation time |

Per the kg-automation CLAUDE.md, the project charter is the single source of truth for governance and edits to it ARE the documented amendment workflow — this is the legitimate path to modifying `.kittify/charter/charter.md`.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T030 — Charter Deployment Constraints rewrite

Open `.kittify/charter/charter.md` and locate the **Deployment Constraints** section (currently around line 86). Replace the bullet that begins:

> **Every feature that deploys code, agents, skills, or scheduled services to office2 must include a deploy script** at `scripts/deploy/deploy-f{NNN}.sh` (or mission-slug equivalent). See `docs/runbooks/deployment.md` for the established pattern.

with:

> **Every deploy to office2 flows through the manifest discipline.** Create a deploy entry at `deploys/queued/<name>.yaml` referencing a script that uses the shared library at `scripts/deploy/lib/`. The `felix-deployer` applier on office2 picks up the manifest within 5 minutes of merge, applies the deploy through `lib.apply.dry_run_then_apply_gate`, and records the outcome under `deploys/applied/`. Tier 0 deploys are never executed via this pipeline — they remain manual via `ssh office2-kgale`. See `docs/runbooks/deploy/discipline.md` for the operational pattern, `scripts/deploy/lib/README.md` for the library API, and `deploys/schema/manifest-v1.schema.json` for the manifest schema. The grandfathered scripts in `scripts/deploy/deploy-{028,149,f013,f014,f026,felix-admin-calendar,restore-whatsapp-dm-reply-delivery}.sh` continue to work; sibling issue #548 handles their cleanup post-merge.

Preserve the surrounding bullets (Production services run on office2, Target Linux, Tailscale-only, strict-order safe-deploy, no system crontab, deploy targets match real paths, Tier 2 Restic ≤24h) — they remain in force.

### T031 — Charter sync

After the rewrite, run:

```bash
spec-kitty charter sync
```

This propagates the amendment to any derived doctrine artifacts (under `.kittify/doctrine/`). Commit the synced changes alongside the charter edit. If `charter sync` surfaces the known tool-registry mismatch (per memory `project_charter_tool_registry_mismatch`), proceed anyway — that diagnostic is unrelated noise.

### T032 — `docs/runbooks/deploy/discipline.md`

Create the directory `docs/runbooks/deploy/` and write `discipline.md`. This is the canonical operational runbook everything else links to. Structure:

1. **Purpose** — one paragraph: "Every deploy to office2 flows through this discipline. This runbook is the canonical reference."
2. **The shape** — what `deploys/queued/<name>.yaml` looks like (mirror quickstart.md from the planning artifacts)
3. **The library** — pointer to `scripts/deploy/lib/README.md` with a one-line summary of each module
4. **The applier** — pointer to `scripts/deploy/felix-deployer/` with operational notes (systemd timer, log location at `/data/services/felix-deployer/logs/<YYYY-MM-DD>.jsonl`, status via `systemctl --user status felix-deployer.timer`)
5. **Tier policy** — Tier 0 is manual; Tier 1/2 require a `verification:` block; Tier 3/4 require only the script
6. **Failure handling** — what the operator sees on the WhatsApp DM; how to fix and re-attempt; how to cancel
7. **Bootstrap** — pointer to `scripts/deploy/deploy-felix-deployer-bootstrap.sh` as the canonical one-shot example (for reference; not for general use)
8. **Rebaseline obligation (FR-018)** — any deploy touching audited surfaces must record `Rebaseline: completed at <ts>` in the merge commit per `docs/runbooks/security-baseline-ops.md`
9. **Reference index** — links to charter rule, library README, manifest schema, signal-to-doc-map deploy classes, this mission's contracts

Target 200–300 lines.

### T033 — Rewrite `docs/runbooks/deployment.md`

The existing runbook is the pre-mission canonical "how to deploy" doc. Rewrite it as a forwarding page:

```markdown
---
title: Deployment
---

# Deployment

**This page has moved.** The canonical deploy discipline is now documented at
[`docs/runbooks/deploy/discipline.md`](deploy/discipline.md).

(...preserve any structural information about grandfathered scripts and route to discipline.md for everything else...)
```

Keep any structural information about the existing `scripts/deploy/deploy-{028,149,...}.sh` scripts because they're still in use. Route every conceptual question to discipline.md.

### T034 — `CLAUDE.md` (project root) "Deploys to office2" section

Add a section to `/Users/kentgale/repos/kg-automation/CLAUDE.md` (NOT the global ~/.claude/CLAUDE.md). Insert it logically near the existing "Architecture documentation" / "Change Control Guardrails" sections.

```markdown
## Deploys to office2

Every deploy to office2 flows through the **manifest discipline** at
`deploys/queued/<name>.yaml` consumed by the `felix-deployer` applier on office2.
The shared library at `scripts/deploy/lib/` provides vetted primitives for cron
management (OpenClaw only — never system crontab), backup verification,
file-presence checks, and tier guard.

When planning any feature/infra issue that involves deploying to office2, your
plan MUST include a `deploys/queued/<name>.yaml` manifest entry. See
[`docs/runbooks/deploy/discipline.md`](docs/runbooks/deploy/discipline.md)
for the operational pattern and worked examples.

The 7 pre-discipline scripts at `scripts/deploy/deploy-*.sh` are grandfathered
and remain in use; sibling issue #548 handles their cleanup post-merge.
```

5-15 lines. Concise; cross-link to the runbook does the heavy lifting.

### T035 — `feature.md` issue template

Add a "Deploy required?" section to `.github/ISSUE_TEMPLATE/feature.md`. Insert logically near "Out of scope" or before "References".

```markdown
## Deploy required?

- [ ] This feature requires a deploy to office2
- If yes: the plan MUST include a `deploys/queued/<name>.yaml` manifest entry per [`docs/runbooks/deploy/discipline.md`](../../docs/runbooks/deploy/discipline.md)
```

### T036 — `infra.md` issue template

Same as T035 but for `.github/ISSUE_TEMPLATE/infra.md`. Infra issues are MORE likely to need deploys; phrase accordingly:

```markdown
## Deploy required?

- [ ] This change requires a deploy to office2 (most infra changes do)
- If yes: the plan MUST include a `deploys/queued/<name>.yaml` manifest entry per [`docs/runbooks/deploy/discipline.md`](../../docs/runbooks/deploy/discipline.md)
```

## Test strategy

This WP has no executable tests — verification is via cross-link integrity (WP06).

- `spec-kitty charter sync` exits 0 (tool-registry mismatch warning OK)
- `pytest tests/deploy/test_cross_link.py` passes (after WP06 implements it; until then, run a simple grep:
  `grep -l "docs/runbooks/deploy/discipline.md" CLAUDE.md .kittify/charter/charter.md docs/runbooks/deployment.md`
  must return all 3 files)
- Manual review: discipline runbook is 200–300 lines, accurate, links resolve

## Definition of Done

- 6 owned files modified or created
- Charter Deployment Constraints rule replaced (not appended)
- `discipline.md` exists at `docs/runbooks/deploy/discipline.md`
- `deployment.md` rewritten as forwarding page (preserves grandfathered-script info)
- CLAUDE.md has a "Deploys to office2" section linking to discipline.md
- Both issue templates have "Deploy required?" with link to discipline.md
- Every cross-link in WP06's test graph resolves correctly

## Risks

- **`.kittify/` is workflow-owned in general** but the charter is the documented amendment surface per global CLAUDE.md. The amendment IS the legitimate workflow.
- **Charter sync diagnostics**: known tool-registry mismatch may produce diagnostic output. Per memory `project_charter_tool_registry_mismatch`, this is unrelated noise; do not edit `.kittify/` to silence it.
- **discipline.md size creep**: 200–300 lines is the target. If it grows past 500, split into sub-runbooks under `docs/runbooks/deploy/` and link from the main one.
- **CLAUDE.md edit conflicts**: the project CLAUDE.md is edited in many missions. Be additive; insert at a logical heading boundary; preserve all surrounding sections.
- **Issue template indentation**: GitHub renders the templates literally; preserve YAML frontmatter at the top.

## Reviewer guidance

1. Confirm the charter rule REPLACES (not appends to) the old per-script rule.
2. Confirm `charter sync` was run after the edit (commit log should show the sync's commits).
3. Run the cross-link grep:
   `grep -l "docs/runbooks/deploy/discipline.md" CLAUDE.md .kittify/charter/charter.md docs/runbooks/deployment.md .github/ISSUE_TEMPLATE/feature.md .github/ISSUE_TEMPLATE/infra.md` — should return all 5.
4. Confirm discipline.md is between 150 and 400 lines.
5. Confirm CLAUDE.md edit preserves all pre-existing sections.
