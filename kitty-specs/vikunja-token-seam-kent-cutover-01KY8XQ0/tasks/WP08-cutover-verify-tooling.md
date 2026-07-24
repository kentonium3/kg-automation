---
work_package_id: WP08
title: Cutover verification tooling (deterministic FR-007 helper)
dependencies:
- WP01
requirement_refs:
- FR-007
tracker_refs: []
planning_base_branch: feat/vikunja-token-seam-kent-cutover
merge_target_branch: feat/vikunja-token-seam-kent-cutover
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-token-seam-kent-cutover. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-token-seam-kent-cutover unless the human explicitly redirects the landing branch.
subtasks:
- T019
- T020
phase: Phase 2 - Cutover tooling
history: []
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/
create_intent:
- scripts/vikunja/cutover_verify.py
- tests/vikunja/test_cutover_verify.py
execution_mode: code_change
owned_files:
- scripts/vikunja/cutover_verify.py
- tests/vikunja/test_cutover_verify.py
role: implementer
tags: []
agent: "claude"
shell_pid: "73940"
shell_pid_created_at: "1784864327.692636"
---

# Work Package Prompt: WP08 — Cutover verification tooling

## ⚡ Do This First: Load Agent Profile
Load your assigned agent profile (`agent_profile` frontmatter) via `/ad-hoc-profile-load` before anything else.

## Branch Strategy
- Planning/base + merge target: `feat/vikunja-token-seam-kent-cutover`. `/spec-kitty.implement` sets the worktree base.

## Objective
Provide a **deterministic** verification helper for the attended Tier-2 cutover (IC-07 / FR-007), so the
operator step is a repeatable, testable command rather than ad-hoc SSH (Directive 6). The cutover itself
(merge→office2 pull→verify) is an operator action; this WP builds the tool it runs.

## Subtasks

### T019 — `scripts/vikunja/cutover_verify.py`
Follow the repo helper-script conventions (`docs/design/helper-script-conventions.md`): stdlib-only, uses
`VikunjaClient` + `get_vikunja_token_path()`, `--json` output, non-zero exit on failure, no side effects.
Capabilities (each a subcommand or flag):
- **`--inverse-probe`**: list projects visible to the resolved (kent) token; assert the expected topic
  projects (16,17,18,19,20) **and** Inbox(1) + Habits(13) are present; fail loud if any expected project is
  missing (the #860 gap that the cutover closes). Accept `--expect-projects` to parameterize the id set.
- **`--connectivity`**: a lightweight read per Felix→Vikunja consumer surface (projects list, a task page,
  labels) confirming the resolved token authenticates and reads — the before/after connectivity check.
- **`--task-delta`**: count tasks the resolved token sees across the newly-visible projects (16–20) so the
  operator can size the first-observation burst sync will process post-cutover (the Codex MED cutover gate).
- Default output: a `--json` summary the operator captures BEFORE (still felix-bot on office2) and AFTER
  (kent) the flip. Read-only; never writes to Vikunja.

### T020 — `tests/vikunja/test_cutover_verify.py`
- Unit-test the logic with a mocked `VikunjaClient` (stdlib `unittest.mock`): inverse-probe passes when the
  expected projects are present and fails loud when one is missing; task-delta counts correctly;
  connectivity maps a client error to a non-zero result. No live network.

## Definition of Done
- `cutover_verify.py` exists, stdlib-only, `--json`, read-only, resolves the token via the seam; three
  capabilities work against a mocked client.
- `python3 -m pytest tests/vikunja/test_cutover_verify.py -q` green.

## Reviewer guidance
- Confirm it is strictly read-only (no writes to Vikunja) and fails loud on a missing expected project.
- Confirm it resolves the token via `get_vikunja_token_path()` (so BEFORE/AFTER is just the office2 file state / an env override), not a hardcoded path.

## Activity Log

- 2026-07-24T03:39:34Z – claude – shell_pid=73940 – Assigned agent via action command
