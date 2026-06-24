---
work_package_id: WP03
title: Agent cutover + office2 deploy
dependencies:
- WP01
requirement_refs:
- C-002
- FR-010
tracker_refs: []
planning_base_branch: feat/finalize-inbox-file
merge_target_branch: feat/finalize-inbox-file
branch_strategy: Planning artifacts for this mission were generated on feat/finalize-inbox-file. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/finalize-inbox-file unless the human explicitly redirects the landing branch.
subtasks:
- T013
- T014
- T015
phase: Phase 3 - Cutover & Deploy
assignee: ''
agent: claude
history:
- at: '2026-06-24T20:35:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: deploys/queued/finalize-inbox-file.yaml
create_intent:
- deploys/queued/finalize-inbox-file.yaml
execution_mode: code_change
model: ''
owned_files:
- deploys/queued/finalize-inbox-file.yaml
role: implementer
tags: []
task_type: implement
---

# Work Package Prompt: WP03 – Agent cutover + office2 deploy

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter (`implementer-ivan`), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `implementer-ivan`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match.

---

## Objectives & Success Criteria

Cut felix-admin-capture over to the helper and deliver the change to office2 via
the manifest pipeline (FR-010, C-002).

Done when:

- A `deploys/queued/finalize-inbox-file.yaml` manifest exists that (a) makes the
  helper present on office2 and (b) carries the felix-admin-capture standing-orders
  cutover, following the deploy discipline.
- The standing-orders text replaces the inline `Edit` + `Bash mv` finalize step
  with a single `python3 scripts/inbox/finalize_inbox_file.py <path> --routed-by
  felix-admin-capture` call and defines exit-code handling (0/1/2).
- Rollback + no-rebaseline rationale documented.

## Context & Constraints

- Spec FR-010, C-002; plan IC-03; research D-07.
- **Deploy discipline (read first)**: `docs/runbooks/deploy/discipline.md` and the
  shared lib at `scripts/deploy/lib/`. Every office2 deploy flows through
  `deploys/queued/<name>.yaml` consumed by felix-deployer. Study an existing
  applied manifest under `deploys/applied/` for the exact schema before authoring.
- Standing orders live on office2 at
  `/home/claude/.openclaw/agents/felix-admin-capture/AGENTS.md` (step-5 finalize).
  The manifest is the delivery mechanism — do not edit office2 out-of-band.
- **Rebaseline**: per the known directives-rebaseline gap, the security monitor
  does not hash agent `AGENTS.md` files, so this audited-surface touch needs **no
  rebaseline** — state that reasoning in the manifest/notes for the merge record.
- This is a planning + manifest authoring WP; the helper itself is WP01. Depends
  on WP01 (helper must exist and ship before the cutover references it).

## Branch Strategy

- **Strategy**: planning/base + merge target `feat/finalize-inbox-file`. Execution
  worktree allocated per lane at `/spec-kitty.implement`.

## Subtasks & Detailed Guidance

### T013 — Author standing-orders cutover
- **Purpose**: Replace the fragile inline finalize with one helper call (FR-010).
- **Steps**:
  1. Draft the replacement step-5 text: single `python3
     scripts/inbox/finalize_inbox_file.py <path> --routed-by felix-admin-capture`
     invocation.
  2. Define exit-code handling: `0` → record file complete; `1` → content/validation
     defect, do not retry, surface; `2` → environmental/filesystem, surface for
     operator, do not mark complete.
  3. Carry this text into the manifest payload (T014), not a direct office2 edit.
- **Files**: `deploys/queued/finalize-inbox-file.yaml` (payload) — and a repo-tracked
  copy of the standing-orders snippet if the deploy pattern keeps one.

### T014 — Author the deploy manifest
- **Purpose**: Make the helper present on office2 + apply the cutover (C-002).
- **Steps**:
  1. Create `deploys/queued/finalize-inbox-file.yaml` per the discipline schema
     (name, tier 3, file-presence/checks, the AGENTS.md payload, verification).
  2. Ensure the helper (`scripts/inbox/finalize_inbox_file.py`) is present on
     office2 before the standing-orders cutover takes effect (sequence within the
     manifest).
  3. Use the shared lib primitives (`scripts/deploy/lib/`) for any checks rather
     than ad-hoc shell.
- **Files**: `deploys/queued/finalize-inbox-file.yaml`.

### T015 — Document rollback + no-rebaseline rationale
- **Purpose**: C-002 rollback; #557 rebaseline record.
- **Steps**:
  1. Rollback = revert the standing-orders edit + delete the helper; no data state
     to undo.
  2. Record: only audited surface is felix-admin-capture `AGENTS.md`, which the
     security monitor does not hash → no rebaseline required.
- **Files**: `deploys/queued/finalize-inbox-file.yaml` (notes) / merge record.

## Definition of Done

- [ ] `deploys/queued/finalize-inbox-file.yaml` valid against deploy discipline.
- [ ] Standing-orders text is unambiguous on exit 0/1/2 handling.
- [ ] Helper-presence ordering guarantees the helper exists on office2 before cutover.
- [ ] Rollback + no-rebaseline rationale recorded.

## Risks

- Manifest schema drift — verify against a recent `deploys/applied/` example.
- Cutover sequencing (helper present before standing-orders reference it).

## Reviewer Guidance

- Confirm manifest matches the discipline schema and uses shared-lib checks.
- Confirm exit-code handling in the standing orders is unambiguous.
- Confirm the no-rebaseline rationale is correct (AGENTS.md unhashed).
