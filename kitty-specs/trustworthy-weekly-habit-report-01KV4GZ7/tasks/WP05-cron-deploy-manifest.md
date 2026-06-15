---
work_package_id: "WP05"
title: "Cron reschedule via deploy manifest"
subtasks: ["T020", "T021"]
dependencies: ["WP04"]
planning_base_branch: "main"
merge_target_branch: "main"
branch_strategy: "lane-from-coord"
owned_files:
  - "deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml"
authoritative_surface: "deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml"
execution_mode: "code_change"
agent_profile: "implementer-ivan"
role: "implementer"
agent: "claude"
requirement_refs: ["FR-001", "C-006"]
history:
  - at: "2026-06-15T02:33:00Z"
    actor: "spec-kitty agent mission tasks"
    event: "WP created from /spec-kitty.tasks"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via `/ad-hoc-profile-load implementer-ivan`.

## Objective

Create the `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` manifest that the felix-deployer applier consumes to move the felix-admin-habits weekly cron from `0 22 * * 0` (Sunday 22:00 ET) to `0 6 * * 1` (Monday 06:00 ET) on office2.

## Context

Per kg-automation CLAUDE.md "Deploys to office2" section: every deploy flows through the manifest discipline at `deploys/queued/<name>.yaml`. The runbook at `docs/runbooks/deploy/discipline.md` documents the manifest schema and primitives. Felix-deployer applies queued manifests on office2.

The schedule string and TZ must agree with the AGENTS.md text edited in WP04. Both surfaces must say `0 6 * * 1` (or its UTC equivalent if the primitive doesn't support TZ declaration).

Read before starting:

- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/spec.md` (FR-001, C-006)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/plan.md` (IC-05)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/research.md` (R-01 TZ decision)
- `docs/runbooks/deploy/discipline.md` (manifest schema)
- `scripts/deploy/lib/` (the shared deploy primitives)
- Existing `deploys/queued/*.yaml` and `deploys/applied/*.yaml` entries for shape templates

## Subtasks

### T020 — Create the deploy manifest

File: `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` (NEW).

Manifest shape (template — exact field names confirmed by T021 inspection):

```yaml
# deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml
#
# Move felix-admin-habits weekly cron to Monday 06:00 ET so the report
# arrives after the reporting window has fully closed. See mission
# trustworthy-weekly-habit-report-01KV4GZ7 and issue #605.

name: reschedule-felix-admin-habits-weekly-cron
description: |
  Move the felix-admin-habits weekly cron tick from Sunday 22:00 ET
  (0 22 * * 0) to Monday 06:00 ET (0 6 * * 1) so the reporting window
  has fully closed before the helper runs. Companion change to the
  AGENTS.md edit in mission trustworthy-weekly-habit-report-01KV4GZ7.

operation: openclaw_cron_update
target:
  agent: felix-admin-habits
  tick: weekly  # or whatever the existing identifier is — verify in openclaw config
change:
  from:
    schedule: "0 22 * * 0"
    tz: America/New_York
  to:
    schedule: "0 6 * * 1"
    tz: America/New_York

mission_ref: trustworthy-weekly-habit-report-01KV4GZ7
issue_refs:
  - https://github.com/kentonium3/kg-automation/issues/605
```

Verify the manifest format against the existing applied manifests under `deploys/applied/` (e.g., `deploys/applied/0002-bootstrap-felix-deployer-v2.yaml`) — match the actual schema fields.

### T021 — Verify openclaw cron primitive TZ field

Read `scripts/deploy/lib/` cron-related helpers and confirm the field name and value semantics for declaring per-job timezone. Specifically:

```bash
grep -rE "(cron|schedule|timezone|tz)" scripts/deploy/lib/ | head -30
```

Possibilities:
- **Best case**: primitive accepts a `tz:` field with an IANA timezone string (e.g., `America/New_York`). Use it directly in the manifest.
- **Acceptable fallback**: primitive only accepts UTC schedule strings. In that case the manifest's `change.to.schedule` must be the UTC equivalent. For 06:00 ET that's `0 10 * * 1` in EDT (summer) or `0 11 * * 1` in EST (winter). This is unsatisfactory for DST — document the limitation in the manifest's `description` and file a follow-up issue.

Update the manifest in T020 to reflect what the primitive actually supports.

## Branch strategy

- Planning base branch: `main`
- Merge target branch: `main`
- This WP lands on its computed lane worktree.
- Depends on WP04 — schedule string must agree across both surfaces. If WP04 has already landed, copy its exact schedule string.

## Test strategy

The deploy manifest is consumed by felix-deployer post-mission-merge on office2; the actual cron-change effect is verified by the operator (Kent) per the quickstart's section 2 verification. There's no pytest target for this WP.

Local validation:

```bash
# Confirm the YAML parses cleanly
python3 -c "import yaml; yaml.safe_load(open('deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml'))"

# Confirm the schedule string matches AGENTS.md
grep -E "(0 6 \* \* 1|0 22 \* \* 0)" deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml
grep -E "(0 6 \* \* 1|0 22 \* \* 0)" scripts/openclaw/agents/felix-admin-habits/AGENTS.md
# Both should report "0 6 * * 1" and NOT "0 22 * * 0".
```

## Definition of Done

- [ ] `deploys/queued/reschedule-felix-admin-habits-weekly-cron.yaml` exists.
- [ ] Manifest parses as valid YAML.
- [ ] Schedule string in manifest matches the schedule string in AGENTS.md (WP04's deliverable).
- [ ] Manifest follows the schema used by other entries in `deploys/queued/` and `deploys/applied/`.
- [ ] If the openclaw cron primitive doesn't support per-job TZ, the manifest schedule is the UTC equivalent and the limitation is documented in `description`.
- [ ] `mission_ref` and `issue_refs` populated for audit trail.
- [ ] No edits outside the new manifest file.

## Risks

- **Schedule string drift with AGENTS.md (WP04)**: the strings MUST match. If WP04 is being authored concurrently, coordinate; review both diffs together.
- **TZ primitive uncertainty (R-01)**: until T021 inspection confirms the field name, the manifest is provisional. T021 is small but blocks T020 if the primitive's interface is unfamiliar.
- **Operator applies post-merge, not WP-time**: this manifest doesn't deploy itself. Kent will run felix-deployer (or it will pick up the manifest automatically per the runbook's pattern) post-merge. WP05's deliverable is the manifest FILE, not the deployed state.
- **Manifest naming convention**: existing `deploys/queued/` entries may use a numeric prefix (`0003-`, `0004-`, etc.). Verify the convention before naming — if there's a numbering scheme, use the next available number; if not, plain kebab-case is fine.

## Reviewer guidance

Reviewers verify:

1. Manifest follows the existing shape (compare with the latest `deploys/applied/*.yaml`).
2. Schedule string and TZ are correct and consistent with AGENTS.md (WP04).
3. `mission_ref` and `issue_refs` are populated.
4. YAML parses cleanly.
5. T021's primitive inspection notes are reflected in the manifest's actual field names.

If reviewer thinks the manifest names a tick identifier that doesn't exist in the openclaw config, request a revision — verify with `ssh office2-claude 'openclaw cron list --agent felix-admin-habits'` if needed.

## Implementation command

```bash
spec-kitty agent action implement WP05 --agent claude
```
